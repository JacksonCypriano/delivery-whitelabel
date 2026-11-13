import {Fragment, useEffect, useRef, useState} from 'react';
import {Link, useSearchParams} from 'react-router-dom';
import {request} from '../../api/client';
import {useQuery} from '../../hooks/useQuery';
import {Feedback} from '../../components/Feedback';
import {Pagination} from '../../components/Pagination';
import {panelUrl} from '../../panel';

const stages:Record<string,string>={new:'Novo',attending:'Em atendimento',qualified:'Qualificado',demo:'Demonstração',negotiation:'Negociação',converted:'Convertido',lost:'Perdido'};
const dateLabel=(value:string)=>new Date(value).toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
type Handoff={id:number;conversation_id:number;name:string;phone:string;reason:string;wa_link:string;created_at:string;whatsapp_status:string};

export function CommercialInbox(){
 const [params]=useSearchParams();
 const initialId=Number(params.get('conversation'));
 const [selected,setSelected]=useState<number|null>(Number.isSafeInteger(initialId)&&initialId>0?initialId:null);
 const [page,setPage]=useState(1),[search,setSearch]=useState(''),[filter,setFilter]=useState('all');
 const [showMobileThread,setShowMobileThread]=useState(Boolean(selected));
 const [draft,setDraft]=useState(''),[notes,setNotes]=useState(''),[busy,setBusy]=useState(false);
 const [notice,setNotice]=useState(''),[error,setError]=useState<Error|null>(null);
 const threadRef=useRef<HTMLDivElement|null>(null);
 const previousSelection=useRef<number|null>(null);
 const q=useQuery(()=>request(`commercial/?conversation=${selected||''}&page=${page}&q=${encodeURIComponent(search)}&paused=${filter==='human'?1:0}`),[selected,page,search,filter]);
 const d=q.data, c=d?.selected;
 const alerts:Handoff[]=d?.pilot?.alerts||[];
 useEffect(()=>{const timer=window.setInterval(()=>q.reload(),10000);return()=>window.clearInterval(timer);},[]);
 useEffect(()=>{setNotes(c?.notes||'');},[c?.id,c?.notes]);
 useEffect(()=>{
   const node=threadRef.current;
   if(!node)return;
   const changed=previousSelection.current!==selected;
   const nearBottom=node.scrollHeight-node.scrollTop-node.clientHeight<220;
   if(changed||nearBottom)node.scrollTop=node.scrollHeight;
   previousSelection.current=selected;
 },[selected,c?.messages?.length]);
 function openConversation(id:number){setSelected(id);setDraft('');setShowMobileThread(true);}
 async function act(action:string,extra:Record<string,unknown>={}){
   setBusy(true);setError(null);setNotice('');
   try{
     const r=await request('commercial/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,conversation:selected,...extra})});
     setNotice(r.detail||'Atualizado.');
     if(action==='send_human')setDraft('');
     q.reload();
   }catch(e){setError(e as Error);}finally{setBusy(false);}
 }
 async function confirmExternal(id:number){
   if(!window.confirm('Confirma que você respondeu ao cliente por outro número ou canal? A notificação sairá dos pendentes.'))return;
   setSelected(id);
   await act('resolve_handoff',{conversation:id,confirm_external_reply:true});
 }
 return <section className="commercial-inbox-page">
  <header className="page-heading commercial-inbox-title"><div><p className="eyebrow">VemDeDelivery · atendimento</p><h1>Inbox comercial</h1><p className="muted">Conversas, atendimento humano e alertas pendentes · atualização a cada 10 segundos.</p></div><div className="heading-actions"><Link className="button secondary" to={panelUrl('comercial')}>Configurar agente</Link><button className="secondary" type="button" onClick={q.reload}>Atualizar</button></div></header>
  <Feedback error={error}>{notice&&<p role="status">{notice}</p>}</Feedback>
  {d&&<details className="commercial-handoff-panel" open={alerts.length>0}>
    <summary>Atendimentos aguardando resposta <strong>{d.pilot?.pending_count||0}</strong></summary>
    <div className="commercial-handoff-items">{alerts.length?alerts.map(a=><article className="commercial-handoff-item" key={a.id}>
      <div className="commercial-handoff-info"><strong>{a.name||a.phone}</strong><span>{dateLabel(a.created_at)} · Atendimento humano necessário</span></div>
      <div className="commercial-handoff-actions"><button className="secondary" type="button" onClick={()=>openConversation(a.conversation_id)}>Ver na Inbox</button>{a.wa_link&&<a className="button secondary" href={a.wa_link} target="_blank" rel="noopener noreferrer">Abrir WhatsApp</a>}<button type="button" disabled={busy} className="secondary" onClick={()=>void confirmExternal(a.conversation_id)}>Já respondi fora</button></div>
    </article>):<p className="muted">Nenhum atendimento pendente. Os alertas só são encerrados após resposta humana confirmada.</p>}</div>
    {d.pilot?.pending_count>alerts.length&&<p className="muted">Mostrando os {alerts.length} avisos mais recentes de {d.pilot.pending_count} pendentes.</p>}
  </details>}
  <Feedback loading={q.loading&&!d} error={q.error}>{d&&<div className={`commercial-chat-shell${showMobileThread?' chat-open':''}`}>
    <aside className="commercial-chat-contacts"><div className="commercial-chat-filters"><label>Buscar contato<input value={search} onChange={e=>{setSearch(e.target.value);setPage(1);}} placeholder="Nome ou telefone"/></label><label>Filtro<select value={filter} onChange={e=>{setFilter(e.target.value);setPage(1);}}><option value="all">Todas</option><option value="human">Atendimento humano</option></select></label></div>
      <div className="commercial-chat-list">{d.conversations.map((x:any)=><button key={x.id} type="button" className="commercial-chat-contact" aria-pressed={selected===x.id} onClick={()=>openConversation(x.id)}><span className="commercial-chat-contact-name"><strong>{x.name||x.phone}</strong><small>{x.phone}</small><small className="commercial-chat-stage">{stages[x.stage]||x.stage}</small></span><span className="commercial-chat-meta"><small>{dateLabel(x.updated_at)}</small><small className={x.paused?'commercial-human-pill':'commercial-bot-pill'}>{x.paused?'Humano':'IA'}</small></span></button>)}{!d.conversations.length&&<p className="commercial-chat-list-empty muted">Nenhuma conversa encontrada.</p>}</div>
      <Pagination page={d.pagination.page} pages={d.pagination.pages} size={10} onPage={setPage} onSize={()=>{}}/>
    </aside>
    <div className="commercial-chat-main">{c?<>
      <div className="commercial-chat-header"><div className="commercial-chat-identity"><button type="button" className="secondary commercial-chat-back" onClick={()=>setShowMobileThread(false)} aria-label="Voltar aos contatos">←</button><div><h2>{c.name||c.phone}</h2><p className="muted">{c.phone} · {c.paused?'Atendimento humano':'Agente disponível'}</p></div></div><div className="commercial-chat-actions"><button type="button" disabled={busy} onClick={()=>act('takeover')}>Assumir</button><button type="button" className="secondary" disabled={busy||c.opted_out} onClick={()=>act('resume')}>Devolver à IA</button></div></div>
      <div ref={threadRef} className="commercial-chat-thread" aria-label="Histórico da conversa">{c.messages.map((m:any)=><Fragment key={m.id}>
       {m.text&&<article className={`commercial-chat-bubble ${m.from_me?'outgoing':'incoming'}`}><p>{m.text}</p><small>{m.from_me?'Atendente':'Cliente'} · {dateLabel(m.created_at)}</small></article>}
       {m.reply&&<article className="commercial-chat-bubble outgoing agent-reply"><p>{m.reply}</p><small>Agente virtual · {dateLabel(m.created_at)} · {m.state}</small></article>}
      </Fragment>)}{!c.messages.length&&<p className="commercial-chat-no-messages">Nenhuma mensagem registrada nesta conversa.</p>}</div>
      <div className="commercial-chat-compose"><div className="commercial-chat-compose-row"><label>Responder pelo painel<textarea value={draft} maxLength={3000} onChange={e=>setDraft(e.target.value)} disabled={!c.paused||!d.control.human_send_enabled||busy} placeholder={d.control.human_send_enabled?'Escreva sua mensagem após assumir a conversa':'Envio manual desativado no servidor'} rows={2}/></label><button disabled={busy||!draft.trim()||!c.paused||!d.control.human_send_enabled} type="button" onClick={()=>act('send_human',{text:draft})}>Enviar no WhatsApp</button></div><p className="muted">Envios incertos não são repetidos. A notificação é resolvida após resposta humana confirmada.</p></div>
      <details className="commercial-chat-details"><summary>Dados do lead e observações</summary><label>Etapa<select value={c.stage} disabled={busy} onChange={e=>act('lead',{stage:e.target.value,notes})}>{Object.entries(stages).map(([key,value])=><option key={key} value={key}>{value}</option>)}</select></label><label>Observações internas<textarea rows={4} maxLength={4000} value={notes} onChange={e=>setNotes(e.target.value)}/></label><button className="secondary" disabled={busy} type="button" onClick={()=>act('lead',{stage:c.stage,notes})}>Salvar observações</button></details>
    </>:<div className="commercial-chat-empty">Selecione uma conversa para visualizar o histórico e atender o cliente.</div>}</div>
  </div>}</Feedback>
 </section>;
}
