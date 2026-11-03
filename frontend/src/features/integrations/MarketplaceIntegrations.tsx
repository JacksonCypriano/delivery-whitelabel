import {useState} from 'react';
import {Link} from 'react-router-dom';
import {request} from '../../api/client';
import {useQuery} from '../../hooks/useQuery';
import {Feedback} from '../../components/Feedback';
import {panelUrl} from '../../panel';

type Provider = 'ifood' | '99food';
type Connection = {
  id: number;
  merchant_id: string;
  merchant_name: string;
  mode: string;
  enabled: boolean;
  status: string;
  last_sync: string|null;
};
type Channel = {
  provider: Provider;
  label: string;
  blocked: boolean;
  connections: Connection[];
};
type IntegrationResponse = {providers: Channel[]};

function visibleConnection(channel: Channel): Connection|undefined {
  // No merchant-facing sandbox, simulation, token, webhook or test controls.
  // Only a truly active production connection is presented as connected.
  return channel.connections.find(c => c.mode === 'live' && c.enabled);
}

function requested(channel: Channel): boolean {
  return channel.connections.some(c => c.merchant_id.startsWith('request-') &&
    c.status === 'awaiting_authorization');
}

function ChannelCard({channel, onUpdated}: {channel: Channel; onUpdated: () => void}) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const connected = visibleConnection(channel);
  const pending = requested(channel);
  const status = connected ? 'Conectado' : pending ? 'Solicitação em análise' :
    channel.blocked ? 'Disponível em breve' : 'Não conectado';

  async function requestConnection() {
    if (busy || connected || pending) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const data = await request<{detail:string}>('integrations/', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({provider: channel.provider, action: 'request'}),
      });
      setNotice(data.detail || 'Solicitação registrada.');
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Não foi possível solicitar a conexão.');
    } finally {setBusy(false);}
  }

  return <section className="card" aria-label={`Integração ${channel.label}`}>
    <div className={`channel-band channel-${channel.provider}`}><strong>{channel.label}</strong></div>
    <h2>{channel.label}</h2>
    <p>Receba pedidos do {channel.label} em Pedidos ativos e na Cozinha/KDS, com a origem identificada.</p>
    <p><strong>Status:</strong> {notice ? 'Solicitação em análise' : status}</p>
    {connected && <>
      <p><strong>Loja vinculada:</strong> {connected.merchant_name || 'Estabelecimento autorizado'}</p>
      {connected.last_sync && <p>Última sincronização: {new Date(connected.last_sync).toLocaleString('pt-BR')}</p>}
    </>}
    {!connected && <p>{channel.blocked
      ? 'Estamos preparando a integração com esta plataforma. Solicite o vínculo e nossa equipe acompanhará a liberação.'
      : 'Solicite a conexão; nossa equipe orientará a autorização no portal da plataforma.'}</p>}
    {notice && <p role="status">{notice}</p>}
    {error && <p role="alert">{error}</p>}
    {!connected && !pending && !notice && <button type="button" disabled={busy}
      onClick={requestConnection}>{busy ? 'Solicitando...' : `Solicitar conexão ${channel.label}`}</button>}
    {pending && <p>Você já solicitou esta integração. Aguarde a validação do vínculo.</p>}
    {connected && <p>Os pedidos desta plataforma serão identificados automaticamente na operação.</p>}
  </section>;
}

/** Merchant-only navigation; diagnostics and test tooling remain shell-only. */
export function MarketplaceIntegrations() {
  return <>
    <div className="page-heading"><div><p className="eyebrow">Canais de venda</p><h1>Integrações</h1>
      <p>Conecte seus canais de venda e acompanhe os pedidos em um só lugar.</p></div></div>
    <div className="integration-grid">
      <section className="card"><div className="channel-band channel-ifood"><strong>iFood</strong></div>
        <p>Conecte sua loja ao iFood.</p><Link to={panelUrl('integracoes/ifood')}>Gerenciar iFood</Link></section>
      <section className="card"><div className="channel-band channel-99food"><strong>99Food</strong></div>
        <p>Solicite a integração com a 99Food.</p><Link to={panelUrl('integracoes/99food')}>Gerenciar 99Food</Link></section>
    </div>
  </>;
}

export function MarketplaceProvider({provider}: {provider:Provider}) {
  const query = useQuery<IntegrationResponse>(() => request('integrations/'));
  const channel = query.data?.providers?.find(p => p.provider === provider);
  return <>
    <div className="page-heading"><div>
      <p className="eyebrow">Canais de venda · <Link to={panelUrl('integracoes')}>Integrações</Link></p>
      <h1>Integração {provider === 'ifood' ? 'iFood' : '99Food'}</h1>
      <p>Gerencie a conexão da sua loja sem configurações técnicas.</p>
    </div><button type="button" className="secondary" onClick={query.reload}>Atualizar status</button></div>
    <Feedback loading={query.loading} error={query.error}>
      {channel && <div className="integration-grid"><ChannelCard key={channel.connections.map(c=>`${c.id}:${c.status}:${c.enabled}`).join('|')} channel={channel} onUpdated={query.reload}/></div>}
    </Feedback>
  </>;
}
