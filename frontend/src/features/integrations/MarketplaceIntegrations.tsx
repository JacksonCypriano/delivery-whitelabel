import { Food99Review } from './Food99Review';
import { Food99OperationalSafety } from './Food99OperationalSafety';
import {useState} from 'react';
import {Link} from 'react-router-dom';
import {request} from '../../api/client';
import {useQuery} from '../../hooks/useQuery';
import {Feedback} from '../../components/Feedback';
import {Pagination} from '../../components/Pagination';
import {panelUrl} from '../../panel';

type Provider = 'ifood' | '99food';
const labels: Record<string,string> = {not_configured:'Não configurado',awaiting_authorization:'Aguardando autorização',connected:'Conectado',error:'Erro'};

/** Navigation only: no provider requests are necessary on the channel chooser. */
export function MarketplaceIntegrations(){
  return <>
    <div className="page-heading"><div><p className="eyebrow">Canais de venda</p><h1>Integrações</h1>
      <p>Escolha a plataforma que deseja configurar ou acompanhar.</p></div></div>
    <div className="integration-grid">
      <section className="card"><div className="channel-band channel-ifood"><strong>iFood</strong></div>
        <p>Conexão, autorização e eventos dos pedidos iFood.</p>
        <Link className="button" to={panelUrl('integracoes/ifood')}>Abrir integração iFood</Link></section>
      <section className="card"><div className="channel-band channel-99food"><strong>99Food</strong></div>
        <p>Conexão, sandbox, simulação operacional e histórico dos pedidos 99Food.</p>
        <Link className="button" to={panelUrl('integracoes/99food')}>Abrir integração 99Food</Link></section>
    </div>
  </>;
}

export function MarketplaceProvider({provider}: {provider:Provider}){
  const [page,setPage]=useState(1);
  const [size,setSize]=useState(10);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const [error,setError]=useState<Error|null>(null);
  const q=useQuery<any>(()=>request('integrations/'));
  const events=useQuery<any>(()=>request(`integrations/events/?page=${page}&page_size=${size}&provider=${provider}`),[provider,page,size]);
  const title=provider==='ifood'?'iFood':'99Food';
  async function action(kind:string,id?:number){
    setBusy(true);setError(null);
    try {
      const result=await request<{detail:string}>('integrations/',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({provider,action:kind,id}),
      });
      setMessage(result.detail);q.reload();
    }catch(e){setError(e as Error);}finally{setBusy(false);}
  }
  const info=q.data?.providers?.find((p:any)=>p.provider===provider);
  return <>
    <div className="page-heading"><div><p className="eyebrow">Canais de venda · <Link to={panelUrl('integracoes')}>Integrações</Link></p>
      <h1>Integração {title}</h1>
      <p>{provider==='ifood'?'Gerencie o vínculo e os eventos do iFood.':'Gerencie o sandbox e as simulações locais da 99Food.'}</p>
    </div><button className="secondary" onClick={()=>{q.reload();events.reload();}}>Atualizar status</button></div>
    {message&&<p role="status">{message}</p>}
    <Feedback loading={q.loading} error={q.error||error}>{info&&
      <div className="integration-grid"><section className="card">
        <div className={`channel-band channel-${provider}`}><strong>{info.label}</strong></div>
        {info.blocked&&<p>O cadastro do aplicativo 99Food já está disponível. O conector de pedidos reais ainda aguarda validação do contrato técnico oficial; a simulação local permanece disponível em homologação.</p>}
        {!info.connections.length&&<p>Não configurado</p>}
        {info.connections.map((c:any)=><div key={c.id}>
          <h3>{provider==='99food'&&c.mode==='simulation'?'Simulação local':provider==='99food'&&c.mode==='test'&&!c.merchant_id.startsWith('request-')?(c.enabled?'Conectado':'Sandbox vinculado · Operação em validação'):(labels[c.status]||c.status)}</h3>
          <p>{c.mode==='simulation'?'SIMULAÇÃO LOCAL':c.mode==='test'?'MODO DE TESTE':'CONTA REAL'}</p>
          <p>Estabelecimento: {c.merchant_name||'Vínculo pendente'} · {c.merchant_id.startsWith('request-')?'Aguardando ID autorizado':c.merchant_id}</p>
          <p>Última sincronização: {c.last_sync?new Date(c.last_sync).toLocaleString('pt-BR'):'Ainda não realizada'}</p>
          {c.pending_events>0&&<p>{c.pending_events} evento(s) aguardando processamento.</p>}
          {c.error&&<p role="alert">{c.error}</p>}
          {c.enabled&&c.mode!=='simulation'&&<button type="button" className="secondary" disabled={busy} onClick={()=>action('disconnect',c.id)}>Desconectar</button>}
        </div>)}
        <p>{provider==='ifood'?'A equipe solicita a permissão do aplicativo. O responsável pela loja aprova no Portal do Parceiro; depois a equipe valida o vínculo.':info.connections.some((c:any)=>c.mode==='test'&&!c.merchant_id.startsWith('request-'))?'Loja sandbox vinculada. A sincronização operacional permanece desabilitada enquanto o contrato de eventos e estados é homologado.':'A conexão de uma nova loja requer autorização e vínculo técnico.'}</p>
        {!(provider==='99food'&&info.connections.some((c:any)=>c.mode==='test'&&!c.merchant_id.startsWith('request-')))&&<button type="button" disabled={busy} onClick={()=>action('request')}>Solicitar conexão {info.label}</button>}
      </section></div>
    }</Feedback>
    {provider==='99food'&&<><Food99OperationalSafety/><Food99Review/></>}
    <section className="card integration-events"><h2>Histórico de eventos {title}</h2>
      <Feedback loading={events.loading} error={events.error}>{events.data&&<>
        <div style={{overflowX:'auto'}}><table><thead><tr><th>Plataforma / pedido</th><th>Evento</th><th>Processamento</th><th>Detalhe</th></tr></thead>
          <tbody>{events.data.events.map((e:any)=><tr key={e.id}><td>{e.provider} · {e.order_id}</td>
            <td>{e.code}<br/>{new Date(e.received_at).toLocaleString('pt-BR')}</td>
            <td>{e.state} · {e.attempts} tentativa(s)</td><td>{e.error||'—'}</td></tr>)}</tbody></table></div>
        {!events.data.events.length&&<p>Nenhum evento recebido.</p>}
        <Pagination {...events.data.pagination} size={size} onPage={setPage} onSize={n=>{setSize(n);setPage(1);}}/>
      </>}</Feedback>
    </section>
  </>;
}
