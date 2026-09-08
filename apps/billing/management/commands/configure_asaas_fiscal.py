import getpass
import os
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.billing.models import FiscalSettings
from apps.billing.provider import Asaas, environment, configured


class Command(BaseCommand):
    help = (
        "Valida e, com --apply, cria/atualiza as informações fiscais da conta "
        "Asaas do ambiente atual. Não emite NFS-e."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Envia a configuração fiscal para o Asaas. Sem esta opção, apenas valida.",
        )
        parser.add_argument(
            "--certificate-file",
            default=os.getenv("ASAAS_FISCAL_CERT_PATH", ""),
            help="Caminho do certificado A1 .pfx/.p12 dentro do container.",
        )
        parser.add_argument(
            "--confirm-production",
            action="store_true",
            help="Confirma explicitamente uma atualização fiscal na conta Asaas de produção.",
        )

    @staticmethod
    def _multipart_value(value):
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def handle(self, *args, **options):
        env = environment()
        config = FiscalSettings.objects.filter(environment=env).first()
        if not config:
            raise CommandError(
                f"Crie primeiro a Configuração de NFS-e do ambiente {env} no superadmin."
            )
        if not configured():
            raise CommandError(
                "O módulo Asaas não está configurado neste ambiente. Confira BILLING_ENABLED, API key e token do webhook."
            )

        try:
            # A mesma validação usada pelo Superadmin também protege o caminho
            # por CLI, evitando que dados inseridos por script/importação sejam
            # enviados ao Asaas sem validação.
            config.full_clean()
            payload = config.fiscal_account_payload()
        except ValidationError as exc:
            messages = []
            if hasattr(exc, "message_dict"):
                for values in exc.message_dict.values():
                    messages.extend(values)
            else:
                messages.extend(exc.messages)
            raise CommandError(" ".join(messages)) from exc

        if bool(config.service_id) == bool(config.service_code):
            raise CommandError(
                "Informe exatamente um identificador do serviço na Configuração de NFS-e. "
                "Quando a lista do Asaas estiver vazia, use somente Código do serviço."
            )

        api = Asaas()
        municipal = api.request("GET", "/fiscalInfo/municipalOptions")
        auth_type = municipal.get("authenticationType")
        self.stdout.write(f"Ambiente Asaas: {env}")
        self.stdout.write(f"Autenticação municipal: {auth_type or 'não informada'}")
        self.stdout.write(
            "Lista municipal de serviços: "
            + ("usa item de lista" if municipal.get("usesServiceListItem") else "sem item de lista obrigatório")
        )
        self.stdout.write(
            "NBS: " + ("exigido pela configuração municipal" if municipal.get("usesNbs") else "não indicado como obrigatório")
        )

        supported_auth_types = {"CERTIFICATE", "USER_AND_PASSWORD", "TOKEN"}
        if auth_type not in supported_auth_types:
            raise CommandError(
                "O Asaas retornou um método de autenticação municipal não suportado: "
                f"{auth_type!r}. Não aplique até atualizar a integração."
            )
        if municipal.get("usesServiceListItem"):
            raise CommandError(
                "O município passou a exigir serviceListItem. Atualize o pacote antes de sincronizar."
            )
        if municipal.get("usesNbs") and not config.nbs_code:
            raise CommandError("O município exige NBS e o campo Código NBS está vazio.")

        if municipal.get("usesNbs"):
            nbs_result = api.request(
                "GET",
                "/fiscalInfo/nbsCodes",
                params={"codeDescription": config.nbs_code, "limit": 100},
            )
            nbs_rows = nbs_result.get("data", []) if isinstance(nbs_result, dict) else []
            exact_nbs = next(
                (
                    row
                    for row in nbs_rows
                    if isinstance(row, dict)
                    and str(row.get("nbsCode") or "").strip() == config.nbs_code
                ),
                None,
            )
            if not exact_nbs:
                raise CommandError(
                    "O NBS informado não foi reconhecido pelo Asaas. "
                    f"Valor consultado: {config.nbs_code}. "
                    "Consulte /fiscalInfo/nbsCodes antes de aplicar."
                )
            self.stdout.write(
                "NBS validado no Asaas: "
                + str(exact_nbs.get("codeDescription") or config.nbs_code)
            )

        self.stdout.write("\nResumo local que será enviado (sem certificado/senha):")
        for key, value in payload.items():
            self.stdout.write(f" - {key}: {value}")
        self.stdout.write(f" - municipalServiceCode (usado na emissão): {config.service_code or '-'}")

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING(
                    "Validação concluída. Nada foi alterado no Asaas. Use --apply somente após conferir os dados acima."
                )
            )
            return

        if env == "production" and not options["confirm_production"]:
            raise CommandError(
                "Produção exige confirmação explícita. Rode novamente com --confirm-production somente após homologação aprovada."
            )

        if auth_type == "CERTIFICATE":
            certificate_path = Path(options["certificate_file"] or "")
            if not certificate_path.is_file():
                raise CommandError(
                    "Informe um certificado A1 existente com --certificate-file ou ASAAS_FISCAL_CERT_PATH."
                )
            if certificate_path.suffix.lower() not in (".pfx", ".p12"):
                raise CommandError("O certificado deve ser um arquivo .pfx ou .p12.")
            if certificate_path.stat().st_size > 10 * 1024 * 1024:
                raise CommandError("Certificado maior que 10 MB; revise o arquivo antes de enviar.")

            certificate_password = os.getenv("ASAAS_FISCAL_CERT_PASSWORD", "")
            if not certificate_password:
                certificate_password = getpass.getpass("Senha do certificado A1: ")
            if not certificate_password:
                raise CommandError("A senha do certificado A1 é obrigatória.")

            data = {key: self._multipart_value(value) for key, value in payload.items()}
            data["certificatePassword"] = certificate_password
            try:
                with certificate_path.open("rb") as certificate:
                    response = api.request(
                        "POST",
                        "/fiscalInfo/",
                        data=data,
                        files={
                            "certificateFile": (
                                certificate_path.name,
                                certificate,
                                "application/x-pkcs12",
                            )
                        },
                    )
            finally:
                certificate_password = None
                data.pop("certificatePassword", None)

        elif auth_type == "USER_AND_PASSWORD":
            username = os.getenv("ASAAS_FISCAL_USERNAME", "").strip()
            municipal_password = os.getenv("ASAAS_FISCAL_PASSWORD", "")
            if not username or not municipal_password:
                raise CommandError(
                    "A prefeitura exige usuário e senha. Configure "
                    "ASAAS_FISCAL_USERNAME e ASAAS_FISCAL_PASSWORD no ambiente "
                    "antes de usar --apply."
                )

            data = dict(payload)
            data["username"] = username
            data["password"] = municipal_password
            try:
                response = api.request("POST", "/fiscalInfo/", json=data)
            finally:
                municipal_password = None
                data.pop("password", None)
                data.pop("username", None)

        else:  # TOKEN
            municipal_access_token = os.getenv(
                "ASAAS_FISCAL_ACCESS_TOKEN", ""
            )
            if not municipal_access_token:
                raise CommandError(
                    "A prefeitura exige token. Configure ASAAS_FISCAL_ACCESS_TOKEN "
                    "no ambiente antes de usar --apply."
                )

            data = dict(payload)
            data["accessToken"] = municipal_access_token
            try:
                response = api.request("POST", "/fiscalInfo/", json=data)
            finally:
                municipal_access_token = None
                data.pop("accessToken", None)

        current = api.request("GET", "/fiscalInfo/")
        self.stdout.write(self.style.SUCCESS("Configuração fiscal aceita pelo Asaas."))
        self.stdout.write(
            "Confirmação remota: "
            f"simplesNacional={current.get('simplesNacional')}, "
            f"municipalInscription={current.get('municipalInscription')}, "
            f"cnae={current.get('cnae')}, rpsSerie={current.get('rpsSerie')}, "
            f"rpsNumber={current.get('rpsNumber')}."
        )
        if isinstance(response, dict) and response.get("status"):
            self.stdout.write(f"Status informado pelo Asaas: {response.get('status')}")
