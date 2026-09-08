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

        if auth_type != "CERTIFICATE":
            raise CommandError(
                "Este pacote está configurado para autenticação municipal por certificado A1. "
                f"O Asaas retornou {auth_type!r}; revise antes de aplicar."
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
