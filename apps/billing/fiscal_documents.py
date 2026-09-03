"""Arquivo privado no banco, download autenticado e caixa de saída fiscal."""

import hashlib
import ipaddress
import socket
import ssl
import time
from urllib.parse import urlsplit
from xml.etree import ElementTree
import urllib3
from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.validators import validate_email
from django.db import transaction
from django.http import Http404, HttpResponse
from django.utils import timezone
from .models import FiscalInvoice, BillingCustomer, FiscalSettings
from .provider import configured, environment

LIMIT = 5 * 1024 * 1024


def download_document(url, kind):
    parsed = urlsplit(url)
    allowed = getattr(
        settings,
        "NFSE_DOCUMENT_HOSTS",
        ("asaas.com", "www.asaas.com", "sandbox.asaas.com"),
    )
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or any(c.isspace() for c in url)
    ):
        raise ValueError("Destino do documento não autorizado.")
    addresses = {
        row[4][0]
        for row in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    }
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError("Destino privado bloqueado.")
    # IP fixado após resolução: evita DNS rebinding. SNI e certificado continuam
    # validados pelo hostname original. Sem redirects, proxies, cookies ou token.
    pool = urllib3.HTTPSConnectionPool(
        sorted(addresses)[0],
        port=443,
        server_hostname=parsed.hostname,
        assert_hostname=parsed.hostname,
        ssl_context=ssl.create_default_context(),
        timeout=urllib3.Timeout(connect=4, read=12),
        retries=False,
    )
    response = None
    try:
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        response = pool.urlopen(
            "GET",
            target,
            headers={"Host": parsed.hostname, "Accept-Encoding": "identity"},
            redirect=False,
            preload_content=False,
            retries=False,
        )
        if response.status != 200:
            raise ValueError("Documento indisponível.")
        body = bytearray()
        started = time.monotonic()
        for chunk in response.stream(65536, decode_content=False):
            body.extend(chunk)
            if len(body) > LIMIT or time.monotonic() - started > 30:
                raise ValueError("Documento excede o limite.")
        content = bytes(body)
        if kind == "pdf" and not content.startswith(b"%PDF-"):
            raise ValueError("Resposta não é PDF.")
        if kind == "xml":
            if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
                raise ValueError("XML com entidades não permitido.")
            # Rejeita codificações com NUL, evitando DTD oculto em UTF-16/32.
            if b"\x00" in content:
                raise ValueError("Codificação XML não suportada.")
            ElementTree.fromstring(content)
        return content
    finally:
        if response is not None:
            response.close()
        pool.close()


def attachment_response(content, digest, filename, mime):
    if not content:
        raise Http404
    body = bytes(content)
    if hashlib.sha256(body).hexdigest() != digest:
        raise Http404("Documento indisponível para verificação de integridade.")
    response = HttpResponse(body, content_type=mime)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def deliver_documents(note_id):
    if not configured():
        return
    if not FiscalSettings.objects.filter(
        environment=environment(), enabled=True
    ).exists():
        return
    try:
        with transaction.atomic():
            note = FiscalInvoice.objects.select_for_update().get(pk=note_id)
            if note.status != "AUTHORIZED" or note.invoice.environment != environment():
                return
            note.delivery_checked_at = timezone.now()
            for kind in ("pdf", "xml"):
                url = getattr(note, kind + "_url")
                if not getattr(note, kind + "_content") and url:
                    content = download_document(url, kind)
                    setattr(note, kind + "_content", content)
                    setattr(note, kind + "_sha256", hashlib.sha256(content).hexdigest())
            note.save()
            if not note.pdf_content:
                note.delivery_notice = "PDF ainda indisponível; arquivamento e e-mail aguardam o documento do Asaas."
                note.save(update_fields=["delivery_notice"])
                return
            if note.delivery_status != "PENDING":
                return
            if note.invoice.environment == "sandbox" and not getattr(
                settings, "NFSE_SANDBOX_EMAIL_ENABLED", False
            ):
                note.delivery_notice = (
                    "Documentos arquivados. Envio de e-mail em sandbox desabilitado."
                )
                note.save(update_fields=["delivery_notice"])
                return
            if not note.delivery_email:
                customer = BillingCustomer.objects.filter(
                    tenant_id=note.invoice.tenant_id,
                    environment=note.invoice.environment,
                    provider_id=note.invoice.customer_id_external,
                ).first()
                if not customer:
                    raise ValueError("Pagador não localizado.")
                validate_email(customer.email)
                note.delivery_email = customer.email
            note.delivery_status = "SENDING"
            note.delivery_notice = (
                "Envio iniciado. Se interrompido, confira o provedor antes de reenviar."
            )
            note.save()
        # Intenção persistida ANTES do SMTP. Um crash após aceitação não provoca
        # reenvio automático duplicado. SMTP não garante entrega na caixa postal.
        note.refresh_from_db()
        if note.status != "AUTHORIZED":
            FiscalInvoice.objects.filter(pk=note_id).update(
                delivery_status="UNCERTAIN",
                delivery_notice="Situação fiscal alterada antes do envio; revisar.",
            )
            return
        prefix = (
            "[TESTE SEM VALIDADE FISCAL] "
            if note.invoice.environment == "sandbox"
            else ""
        )
        message = EmailMessage(
            subject=f"{prefix}VemDeDelivery — sua nota fiscal",
            body=f"Olá!\n\nA nota fiscal nº {note.number or note.provider_id} da assinatura {note.invoice.plan_name} foi autorizada. Segue o PDF em anexo e o XML, quando disponibilizado pelo emissor.\n\nUma cópia permanece disponível no painel da sua loja, em Minha assinatura → Histórico de cobranças → Nota fiscal.\n\nVemDeDelivery — COBRADEV SOLUTIONS",
            to=[note.delivery_email],
            headers={
                "Message-ID": f"<nfse-{note.invoice.environment}-{note.invoice_id}@vemdedelivery.com.br>"
            },
        )
        message.attach(
            f"nfse-{note.pk}.pdf", bytes(note.pdf_content), "application/pdf"
        )
        if note.xml_content:
            message.attach(
                f"nfse-{note.pk}.xml", bytes(note.xml_content), "application/xml"
            )
        try:
            message.connection = get_connection(timeout=20)
            if message.send(fail_silently=False) != 1:
                raise ValueError("Envio não confirmado.")
        except Exception:
            FiscalInvoice.objects.filter(pk=note_id).update(
                delivery_status="UNCERTAIN",
                delivery_notice="Resultado do envio incerto. Confira o SMTP antes de solicitar reenvio manual.",
            )
            return
        FiscalInvoice.objects.filter(pk=note_id).update(
            delivery_status="SENT",
            delivery_at=timezone.now(),
            delivery_notice="Mensagem aceita pelo servidor SMTP. Acompanhe rejeições e entrega no provedor.",
        )
    except Exception:
        FiscalInvoice.objects.filter(pk=note_id).update(
            delivery_checked_at=timezone.now(),
            delivery_notice="Não foi possível arquivar/enviar. Confira os hosts permitidos, os documentos e o e-mail financeiro do pagador. Nova tentativa periódica.",
        )
