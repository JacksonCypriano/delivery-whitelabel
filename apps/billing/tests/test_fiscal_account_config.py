import os
import tempfile
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.billing.models import FiscalSettings


BASE = dict(
    BILLING_ENABLED=True,
    ASAAS_API_KEY="test-only",
    ASAAS_WEBHOOK_TOKEN="testing-token-longer-than-thirty-two-characters",
)


def fiscal_settings(environment="sandbox"):
    return FiscalSettings.objects.create(
        environment=environment,
        service_code="02800",
        fiscal_email="fiscal@example.com",
        municipal_inscription="1.673.942-6",
        simples_nacional=True,
        cultural_projects_promoter=False,
        cnae="6202300",
        special_tax_regime="0",
        national_portal_tax_calculation_regime="1",
        nbs_code="1.1103.22.00",
        rps_serie="1",
        rps_number=1,
    )


@override_settings(ASAAS_ENVIRONMENT="sandbox", **BASE)
class FiscalAccountConfigTests(TestCase):
    def test_payload_contains_confirmed_non_secret_fields(self):
        config = fiscal_settings()
        payload = config.fiscal_account_payload()
        self.assertEqual(payload["municipalInscription"], "16739426")
        self.assertEqual(payload["cnae"], "6202300")
        self.assertEqual(payload["specialTaxRegime"], "0")
        self.assertEqual(payload["nationalPortalTaxCalculationRegime"], "1")
        self.assertEqual(payload["nbsCode"], "1.1103.22.00")
        self.assertNotIn("certificatePassword", payload)
        self.assertNotIn("certificateFile", payload)

    def test_dry_run_never_posts(self):
        fiscal_settings()
        api = Mock()
        api.request.side_effect = [
            {
                "authenticationType": "CERTIFICATE",
                "usesServiceListItem": False,
                "usesNbs": True,
            },
            {
                "data": [
                    {
                        "nbsCode": "1.1103.22.00",
                        "codeDescription": (
                            "1.1103.22.00 - Licenciamento de direitos de uso de "
                            "programas de computador (software)"
                        ),
                    }
                ]
            },
        ]
        out = StringIO()
        with patch(
            "apps.billing.management.commands.configure_asaas_fiscal.Asaas",
            return_value=api,
        ):
            call_command("configure_asaas_fiscal", stdout=out)
        self.assertEqual(api.request.call_count, 2)
        self.assertEqual(
            api.request.call_args_list[0].args[:2],
            ("GET", "/fiscalInfo/municipalOptions"),
        )
        self.assertEqual(
            api.request.call_args_list[1].args[:2],
            ("GET", "/fiscalInfo/nbsCodes"),
        )
        self.assertIn("NBS validado no Asaas", out.getvalue())
        self.assertIn("Nada foi alterado", out.getvalue())

    def test_apply_posts_certificate_without_logging_password(self):
        fiscal_settings()
        api = Mock()
        sent = {}

        def request(method, path, **kwargs):
            if (method, path) == ("GET", "/fiscalInfo/municipalOptions"):
                return {
                    "authenticationType": "CERTIFICATE",
                    "usesServiceListItem": False,
                    "usesNbs": True,
                }
            if (method, path) == ("GET", "/fiscalInfo/nbsCodes"):
                return {
                    "data": [
                        {
                            "nbsCode": "1.1103.22.00",
                            "codeDescription": (
                                "1.1103.22.00 - Licenciamento de direitos de uso de "
                                "programas de computador (software)"
                            ),
                        }
                    ]
                }
            if (method, path) == ("POST", "/fiscalInfo/"):
                sent["data"] = dict(kwargs["data"])
                sent["has_certificate"] = "certificateFile" in kwargs["files"]
                return {"status": "CONFIGURED"}
            return {
                "simplesNacional": True,
                "municipalInscription": "1.673.942-6",
                "cnae": "6202300",
                "rpsSerie": "1",
                "rpsNumber": 1,
            }

        api.request.side_effect = request
        out = StringIO()
        with tempfile.NamedTemporaryFile(suffix=".pfx") as cert, patch.dict(
            os.environ, {"ASAAS_FISCAL_CERT_PASSWORD": "super-secret"}
        ), patch(
            "apps.billing.management.commands.configure_asaas_fiscal.Asaas",
            return_value=api,
        ):
            cert.write(b"fake-certificate")
            cert.flush()
            call_command(
                "configure_asaas_fiscal",
                "--apply",
                "--certificate-file",
                cert.name,
                stdout=out,
            )
        post = next(
            call
            for call in api.request.call_args_list
            if call.args[:2] == ("POST", "/fiscalInfo/")
        )
        self.assertEqual(post.args[:2], ("POST", "/fiscalInfo/"))
        self.assertEqual(sent["data"]["certificatePassword"], "super-secret")
        self.assertTrue(sent["has_certificate"])
        self.assertNotIn("super-secret", out.getvalue())
        self.assertIn("Configuração fiscal aceita", out.getvalue())

    def test_apply_posts_user_and_password_without_logging_secrets(self):
        fiscal_settings()
        api = Mock()
        sent = {}

        def request(method, path, **kwargs):
            if (method, path) == ("GET", "/fiscalInfo/municipalOptions"):
                return {
                    "authenticationType": "USER_AND_PASSWORD",
                    "usesServiceListItem": False,
                    "usesNbs": True,
                }
            if (method, path) == ("GET", "/fiscalInfo/nbsCodes"):
                return {
                    "data": [
                        {
                            "nbsCode": "1.1103.22.00",
                            "codeDescription": "1.1103.22.00 - Software",
                        }
                    ]
                }
            if (method, path) == ("POST", "/fiscalInfo/"):
                sent.update(kwargs["json"])
                return {"status": "CONFIGURED"}
            return {
                "simplesNacional": True,
                "municipalInscription": "16739426",
                "cnae": "6202300",
                "rpsSerie": "1",
                "rpsNumber": 1,
            }

        api.request.side_effect = request
        out = StringIO()
        with patch.dict(
            os.environ,
            {
                "ASAAS_FISCAL_USERNAME": "prefeitura-user",
                "ASAAS_FISCAL_PASSWORD": "prefeitura-secret",
            },
        ), patch(
            "apps.billing.management.commands.configure_asaas_fiscal.Asaas",
            return_value=api,
        ):
            call_command("configure_asaas_fiscal", "--apply", stdout=out)

        self.assertEqual(sent["municipalInscription"], "16739426")
        self.assertEqual(sent["username"], "prefeitura-user")
        self.assertEqual(sent["password"], "prefeitura-secret")
        self.assertNotIn("certificateFile", sent)
        self.assertNotIn("certificatePassword", sent)
        self.assertNotIn("prefeitura-secret", out.getvalue())
        self.assertIn("Configuração fiscal aceita", out.getvalue())

    def test_user_and_password_dry_run_does_not_require_secrets(self):
        fiscal_settings()
        api = Mock()
        api.request.side_effect = [
            {
                "authenticationType": "USER_AND_PASSWORD",
                "usesServiceListItem": False,
                "usesNbs": True,
            },
            {
                "data": [
                    {
                        "nbsCode": "1.1103.22.00",
                        "codeDescription": "1.1103.22.00 - Software",
                    }
                ]
            },
        ]
        out = StringIO()
        with patch.dict(
            os.environ,
            {
                "ASAAS_FISCAL_USERNAME": "",
                "ASAAS_FISCAL_PASSWORD": "",
            },
        ), patch(
            "apps.billing.management.commands.configure_asaas_fiscal.Asaas",
            return_value=api,
        ):
            call_command("configure_asaas_fiscal", stdout=out)
        self.assertIn("Nada foi alterado", out.getvalue())

    def test_apply_posts_token_without_logging_secret(self):
        fiscal_settings()
        api = Mock()
        sent = {}

        def request(method, path, **kwargs):
            if (method, path) == ("GET", "/fiscalInfo/municipalOptions"):
                return {
                    "authenticationType": "TOKEN",
                    "usesServiceListItem": False,
                    "usesNbs": True,
                }
            if (method, path) == ("GET", "/fiscalInfo/nbsCodes"):
                return {
                    "data": [
                        {
                            "nbsCode": "1.1103.22.00",
                            "codeDescription": "1.1103.22.00 - Software",
                        }
                    ]
                }
            if (method, path) == ("POST", "/fiscalInfo/"):
                sent.update(kwargs["json"])
                return {"status": "CONFIGURED"}
            return {
                "simplesNacional": True,
                "municipalInscription": "16739426",
                "cnae": "6202300",
                "rpsSerie": "1",
                "rpsNumber": 1,
            }

        api.request.side_effect = request
        out = StringIO()
        with patch.dict(
            os.environ,
            {"ASAAS_FISCAL_ACCESS_TOKEN": "municipal-token-secret"},
        ), patch(
            "apps.billing.management.commands.configure_asaas_fiscal.Asaas",
            return_value=api,
        ):
            call_command("configure_asaas_fiscal", "--apply", stdout=out)

        self.assertEqual(sent["accessToken"], "municipal-token-secret")
        self.assertNotIn("municipal-token-secret", out.getvalue())
        self.assertIn("Configuração fiscal aceita", out.getvalue())

    def test_nbs_digits_are_normalized_to_official_asaas_format(self):
        config = fiscal_settings()
        config.nbs_code = "111032200"
        config.full_clean()
        self.assertEqual(config.nbs_code, "1.1103.22.00")
        self.assertEqual(config.fiscal_account_payload()["nbsCode"], "1.1103.22.00")

    def test_command_rejects_nbs_not_returned_by_asaas_before_post(self):
        fiscal_settings()
        api = Mock()

        def request(method, path, **kwargs):
            if (method, path) == ("GET", "/fiscalInfo/municipalOptions"):
                return {
                    "authenticationType": "CERTIFICATE",
                    "usesServiceListItem": False,
                    "usesNbs": True,
                }
            if (method, path) == ("GET", "/fiscalInfo/nbsCodes"):
                return {"data": []}
            raise AssertionError(f"Chamada inesperada: {method} {path}")

        api.request.side_effect = request
        with patch(
            "apps.billing.management.commands.configure_asaas_fiscal.Asaas",
            return_value=api,
        ), self.assertRaisesMessage(CommandError, "não foi reconhecido pelo Asaas"):
            call_command("configure_asaas_fiscal")
        self.assertFalse(
            any(
                call.args[:2] == ("POST", "/fiscalInfo/")
                for call in api.request.call_args_list
            )
        )

    def test_sp_ccm_is_normalized_and_missing_digit_is_rejected(self):
        config = fiscal_settings()
        config.municipal_inscription = "16739426"
        config.full_clean()
        self.assertEqual(config.municipal_inscription, "1.673.942-6")

        config.municipal_inscription = "673.942-6"
        with self.assertRaisesMessage(ValidationError, "8 dígitos"):
            config.full_clean()

    def test_command_rejects_invalid_sp_ccm_before_calling_asaas(self):
        config = fiscal_settings()
        config.municipal_inscription = "673.942-6"
        config.save(update_fields=["municipal_inscription"])
        api = Mock()
        with patch(
            "apps.billing.management.commands.configure_asaas_fiscal.Asaas",
            return_value=api,
        ), self.assertRaisesMessage(CommandError, "8 dígitos"):
            call_command("configure_asaas_fiscal")
        api.request.assert_not_called()

    def test_service_id_and_code_together_are_rejected(self):
        config = fiscal_settings()
        config.service_id = "srv_123"
        config.save(update_fields=["service_id"])
        api = Mock()
        with patch(
            "apps.billing.management.commands.configure_asaas_fiscal.Asaas",
            return_value=api,
        ), self.assertRaises(CommandError):
            call_command("configure_asaas_fiscal")
        api.request.assert_not_called()


@override_settings(ASAAS_ENVIRONMENT="production", **BASE)
class FiscalAccountProductionGuardTests(TestCase):
    def test_production_apply_requires_explicit_confirmation(self):
        fiscal_settings("production")
        api = Mock()
        api.request.side_effect = [
            {
                "authenticationType": "CERTIFICATE",
                "usesServiceListItem": False,
                "usesNbs": True,
            },
            {
                "data": [
                    {
                        "nbsCode": "1.1103.22.00",
                        "codeDescription": "1.1103.22.00 - Software",
                    }
                ]
            },
        ]
        with tempfile.NamedTemporaryFile(suffix=".pfx") as cert, patch(
            "apps.billing.management.commands.configure_asaas_fiscal.Asaas",
            return_value=api,
        ), self.assertRaises(CommandError):
            call_command(
                "configure_asaas_fiscal",
                "--apply",
                "--certificate-file",
                cert.name,
            )
        self.assertEqual(api.request.call_count, 2)
        self.assertEqual(
            api.request.call_args_list[0].args[:2],
            ("GET", "/fiscalInfo/municipalOptions"),
        )
        self.assertEqual(
            api.request.call_args_list[1].args[:2],
            ("GET", "/fiscalInfo/nbsCodes"),
        )
