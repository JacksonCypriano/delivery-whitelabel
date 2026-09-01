"""Allowlisted audit fields. Never serialize requests, credentials or exceptions."""
import logging
import re
import uuid
from contextvars import ContextVar
from functools import wraps
from inspect import signature

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.deprecation import MiddlewareMixin
from django.views.decorators.debug import sensitive_variables

from apps.core.rate_limit import get_client_ip
from .models import PendingContactChange, PendingRegistration, SecurityEvent

logger = logging.getLogger("vemdedelivery.audit")
_current_request = ContextVar("security_audit_request", default=None)
_SAFE_NAME = re.compile(r"[A-Za-z0-9_.:\-]{1,120}\Z")


class AuditContextMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request._security_audit_context = _current_request.set(request)

    def process_response(self, request, response):
        token = getattr(request, "_security_audit_context", None)
        if token is not None:
            _current_request.reset(token)
        return response


def _fingerprint(identifier):
    if not identifier:
        return ""
    return salted_hmac("security-audit-identifier", str(identifier).strip().casefold(), algorithm="sha256").hexdigest()


def record_event(event, *, scope="auth", reason="", user_id=None, request=None,
                 channel="", reference=None, identifier="", ip=None):
    """Persist after domain commit. An audit failure must not break authentication.

    A fixed error is emitted if persistence fails, without exception details.
    Caller can only supply named, allowlisted values; no free-form metadata.
    """
    try:
        if event not in SecurityEvent.Event.values:
            raise ValueError("Invalid audit event")
        req = request if request is not None else _current_request.get()
        actor = getattr(req, "user", None)
        actor_id = actor.pk if actor is not None and actor.is_authenticated else None
        resolver = getattr(req, "resolver_match", None)
        route = getattr(resolver, "view_name", "") or ""
        request_id = getattr(req, "request_id", "") or ""
        address = get_client_ip(req) if req is not None else ip
        import ipaddress
        try:
            address = str(ipaddress.ip_address(address))
        except (ValueError, TypeError):
            address = None
        data = dict(
            created_at=timezone.now(), event=event,
            scope=scope if scope in {"auth", "account", "registration", "contact", "dashboard"} else "auth",
            reason=reason if reason in SecurityEvent.Reason.values else "rejected",
            user_id=user_id, actor_id=actor_id,
            channel=channel if channel in {"email", "whatsapp"} else "",
            ip_address=address, request_id=request_id if len(request_id) <= 64 and _SAFE_NAME.fullmatch(request_id) else "",
            route=route if _SAFE_NAME.fullmatch(route) else "",
            reference=uuid.UUID(str(reference)) if reference else None,
            identifier_hash=_fingerprint(identifier),
        )
        def persist():
            try:
                # Savepoint isolates failed audit inserts from caller transactions.
                with transaction.atomic():
                    SecurityEvent.objects.create(**data)
            except Exception:
                logger.error("Falha ao persistir evento de segurança; auditoria incompleta.")
        transaction.on_commit(persist)
    except Exception:
        logger.error("Falha ao preparar evento de segurança; auditoria incompleta.")


def login_rejected(request, identifier, reason="invalid_input"):
    # authenticate() already emits user_login_failed for invalid credentials.
    if not getattr(request, "_security_login_failure_recorded", False):
        record_event("login_failed", request=request, identifier=identifier, reason=reason)


def audited_otp(scope, operation):
    """Instrument services, including shell/tasks, without receiving OTP in audit data."""
    def decorate(function):
        params = signature(function)
        @wraps(function)
        @sensitive_variables()
        def wrapper(*args, **kwargs):
            bound = params.bind(*args, **kwargs).arguments
            pending_id = bound.get("pending_id")
            owner = bound.get("user_id")
            channel = bound.get("channel", "")
            identifier = ""
            # Snapshot before mutation; completed registrations erase secret material.
            try:
                model = PendingRegistration if scope == "registration" else PendingContactChange
                query = model.objects.filter(pk=pending_id)
                if scope == "contact":
                    query = query.filter(user_id=owner)
                pending = query.first()
                if pending:
                    channel = pending.channel if scope == "contact" else channel
                    identifier = (pending.destination if scope == "contact" else
                                  pending.email if channel == "email" else pending.phone)
            except Exception:
                pending = None
            try:
                result = function(*args, **kwargs)
            except Exception as exc:
                reason = getattr(exc, "reason", "unexpected")
                event = ("rate_limited" if reason in {"rate_limit", "cooldown", "attempts"} else
                         "otp_delivery_failed" if reason == "delivery" else "otp_rejected")
                record_event(event, scope=scope, reason=reason, user_id=owner,
                             channel=channel, reference=pending_id, identifier=identifier, ip=bound.get("ip"))
                raise
            else:
                if scope == "registration" and operation == "verify" and result is not None:
                    owner = result.pk
                event = {"send": "otp_sent", "verify": "otp_confirmed", "cancel": "contact_cancelled"}[operation]
                record_event(event, scope=scope, user_id=owner, channel=channel,
                             reference=pending_id, identifier=identifier, ip=bound.get("ip"))
                return result
        return wrapper
    return decorate
