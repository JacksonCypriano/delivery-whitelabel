"""Offline 99Food callback contract checklist, not a webhook handler.

No signature algorithms or payload fields are invented: a message must remain
untrusted until an official contract supplies and verifies those details.
"""
import hashlib
import json

MAX_BODY_BYTES = 131072


def inspect_untrusted_event(body, *, authenticated=False, contract_approved=False):
    """Inspect payload shape without storing/returning customer PII or ACKing.

    No event can ever be accepted by this offline preflight. In particular,
    callers cannot set flags to bypass the missing actual signature verifier.
    """
    if not isinstance(body, (bytes, bytearray)):
        return {'accepted': False, 'reason': 'INVALID_BODY'}
    if len(body) > MAX_BODY_BYTES:
        return {'accepted': False, 'reason': 'BODY_TOO_LARGE'}
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return {'accepted': False, 'reason': 'INVALID_JSON'}
    if not isinstance(payload, dict):
        return {'accepted': False, 'reason': 'INVALID_ENVELOPE'}
    return {
        'accepted': False,
        'reason': 'CONTRACT_NOT_VERIFIED',
        'byte_length': len(body),
        'sha256': hashlib.sha256(body).hexdigest(),
        'field_count': len(payload),
        'verification_performed': False,
        'persisted': False,
        'acknowledged': False,
    }
