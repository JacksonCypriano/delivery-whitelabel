import json
import logging
import re
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

from django.utils.deprecation import MiddlewareMixin


_request_id = ContextVar("request_id", default="-")
_tenant_slug = ContextVar("tenant_slug", default="-")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def get_request_id():
    return _request_id.get()


def get_tenant_slug():
    return _tenant_slug.get()


def set_tenant_slug(slug):
    _tenant_slug.set(str(slug or "-"))


class RequestContextFilter(logging.Filter):
    def filter(self, record):
        record.request_id = get_request_id()
        record.tenant = get_tenant_slug()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "tenant": getattr(record, "tenant", "-"),
        }

        for field in ("status_code", "method", "path", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


class RequestContextMiddleware(MiddlewareMixin):
    """Adds a safe request id to logs/responses and request context to log records.

    Request bodies, cookies, authorization headers and query strings are never logged here.
    """

    def process_request(self, request):
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if _REQUEST_ID_RE.fullmatch(incoming) else uuid.uuid4().hex
        request._observability_started_at = time.monotonic()
        request._request_id_token = _request_id.set(request_id)
        request._tenant_token = _tenant_slug.set("-")
        request.request_id = request_id

    def process_response(self, request, response):
        tenant = getattr(request, "tenant", None)
        if tenant is not None:
            _tenant_slug.set(getattr(tenant, "slug", "-") or "-")

        response["X-Request-ID"] = getattr(request, "request_id", get_request_id())

        started = getattr(request, "_observability_started_at", None)
        if started is not None:
            duration_ms = round((time.monotonic() - started) * 1000, 2)
            if duration_ms >= 2000:
                logger = logging.getLogger("vemdedelivery.slow_request")
                logger.warning(
                    "Slow request",
                    extra={
                        "method": request.method,
                        "path": request.path,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                    },
                )

        tenant_token = getattr(request, "_tenant_token", None)
        request_token = getattr(request, "_request_id_token", None)
        if tenant_token is not None:
            _tenant_slug.reset(tenant_token)
        if request_token is not None:
            _request_id.reset(request_token)

        return response
