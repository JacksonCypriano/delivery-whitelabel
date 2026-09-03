import logging
import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

from .client import EvolutionClient, EvolutionError
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WhatsAppCheckResult:
    available: bool
    exists: bool | None
    number: str
    jid: str | None = None


class WhatsAppService(Protocol):
    def check_number(self, phone: str) -> WhatsAppCheckResult: ...


def normalize_br_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if len(digits) not in (10, 11):
        raise ValueError("Informe um telefone válido com DDD.")
    return f"55{digits}"


class DisabledWhatsAppService:
    def check_number(self, phone: str) -> WhatsAppCheckResult:
        number = normalize_br_phone(phone)
        return WhatsAppCheckResult(available=False, exists=None, number=number)


class EvolutionWhatsAppService:
    def __init__(self):
        self.base_url = settings.EVOLUTION_API_URL.rstrip("/")
        self.api_key = settings.EVOLUTION_API_KEY
        self.instance = settings.EVOLUTION_INSTANCE
        self.timeout = settings.EVOLUTION_API_TIMEOUT
        self.cache_seconds = settings.EVOLUTION_CHECK_CACHE_SECONDS

    def check_number(self, phone: str) -> WhatsAppCheckResult:
        number = normalize_br_phone(phone)
        scope = hashlib.sha256(
            f"{self.base_url}\0{self.instance}".encode()
        ).hexdigest()[:20]
        cache_key = f"whatsapp:check:{scope}:{number}"
        cached = cache.get(cache_key)
        if cached is not None:
            return WhatsAppCheckResult(**cached)

        if not self.base_url or not self.api_key or not self.instance:
            logger.warning(
                "Evolution API validation enabled but configuration is incomplete"
            )
            return WhatsAppCheckResult(available=False, exists=None, number=number)

        try:
            payload = EvolutionClient().request(
                "POST", "chat/whatsappNumbers", {"numbers": [number]}
            )
            item = self._extract_result(payload, number)
            if item is None:
                logger.warning(
                    "Unexpected Evolution API response while validating phone"
                )
                return WhatsAppCheckResult(available=False, exists=None, number=number)

            result = WhatsAppCheckResult(
                available=True,
                exists=bool(item.get("exists", item.get("IsInWhatsapp", False))),
                number=number,
                jid=item.get("jid") or item.get("JID") or item.get("RemoteJID"),
            )
            cache.set(cache_key, result.__dict__, timeout=self.cache_seconds)
            return result
        except (EvolutionError, ValueError, TypeError) as exc:
            logger.warning(
                "Evolution API unavailable while validating phone: %s",
                exc.__class__.__name__,
            )
            return WhatsAppCheckResult(available=False, exists=None, number=number)

    @staticmethod
    def _extract_result(payload, number):
        items = payload if isinstance(payload, list) else None
        if items is None and isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("Users") or data.get("users")
            else:
                items = payload.get("Users") or payload.get("users")
        if not isinstance(items, list):
            return None
        for item in items:
            if not isinstance(item, dict):
                continue
            candidate = str(item.get("number") or item.get("Query") or "").replace(
                "+", ""
            )
            if candidate == number or len(items) == 1:
                return item
        return None


def get_whatsapp_service() -> WhatsAppService:
    if not settings.EVOLUTION_WHATSAPP_VALIDATION_ENABLED:
        return DisabledWhatsAppService()
    return EvolutionWhatsAppService()
