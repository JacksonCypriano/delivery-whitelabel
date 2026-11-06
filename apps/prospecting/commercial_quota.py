"""Atomic Gemini request quota shared by commercial workers using the same Redis.

The counter reserves budget BEFORE calling Google. Failure to obtain a counter
fails closed, so it can never silently exceed the configured limit.
"""
import hashlib
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from django.conf import settings
from redis import Redis, RedisError


SCRIPT = """
local cooldown = tonumber(redis.call('GET', KEYS[3]) or '0')
if cooldown > tonumber(ARGV[1]) then
  return {0, cooldown - tonumber(ARGV[1]), -1, -1}
end
local m = tonumber(redis.call('GET', KEYS[1]) or '0')
local d = tonumber(redis.call('GET', KEYS[2]) or '0')
if m >= tonumber(ARGV[2]) then
  return {0, tonumber(ARGV[3]), m, d}
end
if d >= tonumber(ARGV[4]) then
  return {0, tonumber(ARGV[5]), m, d}
end
m = redis.call('INCR', KEYS[1])
if m == 1 then redis.call('EXPIRE', KEYS[1], 120) end
d = redis.call('INCR', KEYS[2])
if d == 1 then redis.call('EXPIRE', KEYS[2], 172800) end
return {1, 0, m, d}
"""


class CommercialQuotaDeferred(Exception):
    def __init__(self, seconds, reason):
        super().__init__(reason)
        self.seconds = max(5, int(seconds))
        self.reason = reason


def _redis():
    location = settings.CACHES['default']['LOCATION']
    if not isinstance(location, str) or urlsplit(location).scheme not in ('redis', 'rediss'):
        raise RuntimeError('commercial_quota_redis_required')
    return Redis.from_url(location, decode_responses=True, socket_connect_timeout=2, socket_timeout=3)


def _key_root(model):
    # One Redis shared by all commercial workers in a deployment. When the same
    # Google project is used by multiple environments they must share the same
    # quota Redis / prefix to have a truly cross-environment global limit.
    namespace = getattr(settings, 'COMMERCIAL_GEMINI_QUOTA_NAMESPACE', 'vdd-commercial')
    if not namespace or any(ch not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.' for ch in namespace):
        raise RuntimeError('invalid_commercial_quota_namespace')
    model_hash = hashlib.sha256(model.encode()).hexdigest()[:20]
    return f'{namespace}:gemini:{model_hash}'


def reserve(model, *, now=None):
    rpm = int(getattr(settings, 'COMMERCIAL_GEMINI_RPM', 8))
    rpd = int(getattr(settings, 'COMMERCIAL_GEMINI_RPD', 350))
    if not 1 <= rpm <= 500 or not 1 <= rpd <= 100000:
        raise CommercialQuotaDeferred(60, 'commercial_quota_invalid_config')
    now = float(time.time() if now is None else now)
    minute = int(now // 60)
    day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
    next_minute = (minute + 1) * 60 - int(now) + 2
    next_day = int((datetime.combine(datetime.fromtimestamp(now, timezone.utc).date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)).timestamp()) - int(now) + 3
    root = _key_root(model)
    keys = [f'{root}:minute:{minute}', f'{root}:day:{day}', f'{root}:cooldown']
    try:
        allowed, delay, _, _ = _redis().eval(SCRIPT, len(keys), *keys, int(now), rpm, next_minute, rpd, max(5, next_day))
    except (RedisError, OSError, RuntimeError) as exc:
        raise CommercialQuotaDeferred(60, 'commercial_quota_redis_unavailable') from exc
    if not allowed:
        raise CommercialQuotaDeferred(delay, 'commercial_quota_wait')


def cooldown(model, seconds=65):
    root = _key_root(model)
    until = int(time.time() + max(5, min(int(seconds), 3600)))
    try:
        conn = _redis()
        key = f'{root}:cooldown'
        # SET only if larger than current cooldown. Lua prevents smaller
        # overlapping workers from shortening the provider-imposed wait.
        conn.eval("local old=tonumber(redis.call('GET',KEYS[1]) or '0'); if tonumber(ARGV[1]) > old then redis.call('SET',KEYS[1],ARGV[1],'EX',3600) end; return 1", 1, key, until)
    except (RedisError, OSError) as exc:
        raise CommercialQuotaDeferred(60, 'commercial_quota_redis_unavailable') from exc
    return seconds
