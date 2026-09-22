import base64
import binascii
import hashlib
import re

from django.core.cache import cache


_PHONE_RE = re.compile(r"\D+")


def normalize_event_name(value):
    return str(value or "").strip().lower().replace("_", ".")


def extract_qr(payload):
    candidates = []
    if isinstance(payload, dict):
        candidates.append(payload.get("base64"))
        qr = payload.get("qrcode")
        if isinstance(qr, dict):
            candidates.append(qr.get("base64"))
        data = payload.get("data")
        if isinstance(data, dict):
            candidates.append(data.get("base64"))
            qr = data.get("qrcode")
            if isinstance(qr, dict):
                candidates.append(qr.get("base64"))

    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate:
            continue
        if len(candidate) > 350_000:
            continue
        if candidate.startswith("data:image/png;base64,"):
            encoded = candidate.split(",", 1)[1]
        else:
            encoded = candidate
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            continue
        if raw.startswith(b"\x89PNG\r\n\x1a\n"):
            return f"data:image/png;base64,{encoded}"
    return None


def extract_text(data):
    if not isinstance(data, dict):
        return ""
    message = data.get("message")
    if not isinstance(message, dict):
        return ""
    candidates = [message.get("conversation")]
    extended = message.get("extendedTextMessage")
    if isinstance(extended, dict):
        candidates.append(extended.get("text"))
    image = message.get("imageMessage")
    if isinstance(image, dict):
        candidates.append(image.get("caption"))
    video = message.get("videoMessage")
    if isinstance(video, dict):
        candidates.append(video.get("caption"))
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()[:4000]
    return ""


def extract_message(data):
    if not isinstance(data, dict):
        return None
    key = data.get("key")
    if not isinstance(key, dict):
        return None
    remote_jid = str(key.get("remoteJid") or "")
    remote_alt = str(key.get("remoteJidAlt") or "")
    # LID-only identifiers are not guaranteed to be routable phone numbers.
    # Use the alternate JID when Evolution provides it; otherwise fail closed.
    if remote_jid.endswith("@lid") and not remote_alt:
        return None
    remote = remote_alt or remote_jid
    if not remote or remote == "status@broadcast" or remote.endswith("@g.us"):
        return None
    text = extract_text(data)
    if not text:
        return None
    message_id = str(key.get("id") or "")[:160]
    if not message_id:
        return None
    phone = remote.split("@", 1)[0]
    phone = _PHONE_RE.sub("", phone)
    if not (10 <= len(phone) <= 15):
        return None
    return {
        "message_id": message_id,
        "phone": phone,
        "text": text,
        "from_me": bool(key.get("fromMe")),
    }


def incoming_once(instance_name, message_id):
    digest = hashlib.sha256(f"{instance_name}\0{message_id}".encode()).hexdigest()
    return cache.add(f"wa-agent:incoming:{digest}", 1, timeout=86400)


def _text_digest(instance_name, phone, text):
    return hashlib.sha256(
        f"{instance_name}\0{phone}\0{text.strip()}".encode()
    ).hexdigest()


def mark_outbound_pending(instance_name, phone, text):
    cache.set(
        f"wa-agent:out-text:{_text_digest(instance_name, phone, text)}",
        1,
        timeout=180,
    )


def mark_outbound_message(instance_name, message_id):
    digest = hashlib.sha256(f"{instance_name}\0{message_id}".encode()).hexdigest()
    cache.set(f"wa-agent:out-id:{digest}", 1, timeout=600)


def is_agent_outbound(instance_name, phone, message_id, text):
    id_digest = hashlib.sha256(f"{instance_name}\0{message_id}".encode()).hexdigest()
    if cache.get(f"wa-agent:out-id:{id_digest}"):
        return True
    return bool(
        cache.get(f"wa-agent:out-text:{_text_digest(instance_name, phone, text)}")
    )
