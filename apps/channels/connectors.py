"""Official iFood Food centralized adapter; 99Food network operations fail closed.

See docs/INTEGRACOES-MARKETPLACES.md for source URLs and contract limitations.
The simulator consumes our internal normalized contract, never a fabricated 99 API.
"""
from datetime import timedelta
from typing import Protocol
import hashlib
import hmac
import re
from urllib.parse import quote
import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.billing.secrets import encrypt_secret, decrypt_secret
from .models import AppToken

class ProviderError(Exception):
    def __init__(self, message='Falha na comunicação com a plataforma.', retryable=False, uncertain=False, status_code=None):
        super().__init__(message)
        self.retryable = retryable
        self.uncertain = uncertain
        self.status_code = status_code

class MarketplaceConnector(Protocol):
    """Provider-owned wire contracts terminate at this boundary."""
    mode: str
    def merchants(self) -> list: ...
    def poll(self, merchant_ids: list[str]) -> list: ...
    def acknowledge(self, ids: list[str]): ...
    def detail(self, order_id: str) -> dict: ...
    def normalize(self, data: dict) -> dict: ...
    def reasons(self, order_id: str) -> list: ...
    def command(self, external, target: str, payload: dict): ...

class BlockedConnector:
    def __init__(self, mode='test'): self.mode = mode
    def _blocked(self, *args, **kwargs):
        raise ProviderError('99Food: contrato oficial, credenciais e homologação pendentes. Conector real indisponível.')
    detail = normalize = command = reasons = poll = acknowledge = merchants = _blocked

class IFood:
    base = 'https://merchant-api.ifood.com.br'
    def __init__(self, mode='test'):
        self.mode = mode
    def credentials(self):
        if not settings.CHANNELS_NETWORK_ENABLED or self.mode == 'simulation':
            raise ProviderError('Comunicação externa desativada.')
        if self.mode == 'live' and not settings.CHANNELS_LIVE_ENABLED:
            raise ProviderError('Contas reais não foram liberadas.')
        prefix = 'IFOOD_LIVE' if self.mode == 'live' else 'IFOOD_TEST'
        key, secret = getattr(settings, prefix+'_CLIENT_ID'), getattr(settings, prefix+'_CLIENT_SECRET')
        if not key or not secret: raise ProviderError('Credenciais do aplicativo iFood não configuradas.')
        return key, secret
    @transaction.atomic
    def token(self, force=False):
        key, secret = self.credentials()
        AppToken.objects.get_or_create(key='ifood:'+self.mode)
        row = AppToken.objects.select_for_update().get(key='ifood:'+self.mode)
        if not force and row.expires_at and row.expires_at > timezone.now() and row.encrypted_token:
            return decrypt_secret(row.encrypted_token)
        data = self._http('POST','/authentication/v1.0/oauth/token', data={'grantType':'client_credentials','clientId':key,'clientSecret':secret})
        try:
            token, seconds = data['accessToken'], int(data['expiresIn'])
            if not token or seconds <= 0: raise ValueError
        except (KeyError, ValueError, TypeError): raise ProviderError('Resposta de autenticação inválida.') from None
        row.encrypted_token = encrypt_secret(token)
        row.expires_at = timezone.now()+timedelta(seconds=seconds)
        row.save(update_fields=['encrypted_token','expires_at'])
        return token
    def _http(self, method, path, **kwargs):
        try:
            r = requests.request(method,self.base+path,timeout=(5,20),allow_redirects=False,**kwargs)
        except requests.RequestException:
            raise ProviderError('iFood temporariamente indisponível.',retryable=method=='GET',uncertain=method=='POST') from None
        if r.status_code == 404:raise ProviderError('Pedido ou recurso ainda indisponível no iFood.',retryable=method=='GET',status_code=404)
        if r.status_code == 204 and path.endswith('/requestCancellation'):raise ProviderError('iFood: não há política de cancelamento disponível.')
        if r.status_code == 401: raise ProviderError('iFood: autorização expirada ou inválida.')
        if r.status_code == 429: raise ProviderError('iFood: limite de chamadas atingido.',retryable=True)
        if r.status_code >= 500: raise ProviderError('iFood temporariamente indisponível.',retryable=method=='GET',uncertain=method=='POST')
        if r.status_code not in (200,201,202,204):
            # Only machine-readable provider codes are shown. Never forward the
            # raw response body/message: they may contain confidential data.
            provider_code = ''
            try:
                error_data = r.json()
                if isinstance(error_data, dict):
                    candidate = error_data.get('code')
                    if isinstance(candidate, str) and re.fullmatch(r'[A-Za-z0-9_ .-]{1,80}', candidate):
                        provider_code = candidate
            except ValueError:
                pass
            operation = ('consulta de motivos de cancelamento' if path.endswith('/cancellationReasons')
                         else 'solicitação de cancelamento' if path.endswith('/requestCancellation')
                         else 'operação')
            detail = f'; código do iFood: {provider_code}' if provider_code else ''
            raise ProviderError(f'iFood recusou {operation} (HTTP {r.status_code}{detail}).', status_code=r.status_code)
        if not r.content: return None
        try: return r.json()
        except ValueError: raise ProviderError('iFood retornou uma resposta inválida.',uncertain=method=='POST') from None
    def request(self,method,path,**kwargs):
        token = self.token()
        extra_headers=kwargs.pop('headers',{})
        try: return self._http(method,path,headers={**extra_headers,'Authorization':'Bearer '+token},**kwargs)
        except ProviderError as exc:
            if str(exc)=='iFood: autorização expirada ou inválida.':
                return self._http(method,path,headers={**extra_headers,'Authorization':'Bearer '+self.token(force=True)},**kwargs)
            raise
    def poll(self, merchant_ids):
        data=self.request('GET','/events/v1.0/events:polling',headers={'x-polling-merchants':','.join(merchant_ids)})
        if data is None:return []
        if not isinstance(data,list):raise ProviderError('Formato de eventos incompatível com o contrato configurado.')
        return data
    def acknowledge(self,ids):
        return self.request('POST','/events/v1.0/events/acknowledgment',json=[{'id':i} for i in ids])
    def normalize(self,data):
        from .normalize import normalize_ifood
        return normalize_ifood(data)
    def detail(self,order_id):
        return self.request('GET','/order/v1.0/orders/'+quote(str(order_id),safe=''))
    def merchants(self):
        rows=[]
        for page in range(1,101):
            batch=self.request('GET','/merchant/v1.0/merchants',params={'page':page,'size':100})
            if not isinstance(batch,list):raise ProviderError('Lista de estabelecimentos inválida.')
            rows.extend(batch)
            if len(batch)<100:return rows
        raise ProviderError('Limite de paginação de estabelecimentos atingido.')
    def reasons(self,order_id):
        data=self.request('GET','/order/v1.0/orders/'+quote(str(order_id),safe='')+'/cancellationReasons')
        rows=data.get('reasons',[]) if isinstance(data,dict) else data or []
        if not isinstance(rows,list):raise ProviderError('Motivos de cancelamento inválidos.')
        normalized = []
        for r in rows:
            if not isinstance(r, dict):
                raise ProviderError('Motivo de cancelamento inválido no iFood.')
            # A API oficial documenta `code`; alguns contratos retornam `cancelCodeId`.
            raw_code = r.get('cancelCodeId') or r.get('code') or r.get('cancelCode')
            if raw_code is None or not str(raw_code).strip():
                raise ProviderError('iFood retornou motivo de cancelamento sem código válido.')
            normalized.append({'code': str(raw_code).strip(), 'description': str(r.get('description') or '')})
        return normalized
    def command(self,external,target,payload):
        paths={'confirmed':'confirm','preparing':'startPreparation','ready':'readyToPickup','ready_for_pickup':'readyToPickup','out_for_delivery':'dispatch','cancelled':'requestCancellation'}
        if target not in paths:raise ProviderError('Transição não suportada pelo iFood.')
        body={}
        if target=='cancelled':
            if payload.get('cancellationCode') not in [r['code'] for r in self.reasons(external.external_id)]:
                raise ProviderError('Selecione um motivo de cancelamento válido no iFood.')
            # Current Order cancellation documentation: reason is the selected code.
            # Free-text justification stays in our audit; Shipping has a different contract.
            body={'reason':payload['cancellationCode']}
        return self.request('POST','/order/v1.0/orders/'+quote(external.external_id,safe='')+'/'+paths[target],json=body)

def connector(connection) -> MarketplaceConnector:
    return IFood(connection.mode) if connection.provider=='ifood' else BlockedConnector(connection.mode)

def valid_ifood_signature(body,signature,mode):
    prefix='IFOOD_LIVE' if mode=='live' else 'IFOOD_TEST'
    secret=getattr(settings,prefix+'_CLIENT_SECRET','')
    return bool(secret and isinstance(signature,str) and re.fullmatch(r'[a-fA-F0-9]{64}',signature) and hmac.compare_digest(hmac.new(secret.encode(),body,hashlib.sha256).hexdigest(),signature.lower()))
