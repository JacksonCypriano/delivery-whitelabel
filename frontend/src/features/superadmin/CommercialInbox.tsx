import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {request} from '../../api/client';
import {useQuery} from '../../hooks/useQuery';
import {Feedback} from '../../components/Feedback';
import {Pagination} from '../../components/Pagination';
import {panelUrl} from '../../panel';

const stages:Record<string,string>={new:'Novo',attending:'Em atendimento',qualified:'Qualificado',demo:'Demonstração',negotiation:'Negociação',converted:'Convertido',lost:'Perdido'};
export function CommercialInbox(){
 const [selected,setSelected]=useState<number|null>(null),[page,setPage]=useState(1),[search,setSearch]=useState(''),[filter,setFilter]=useState('all');
 const [draft,setDraft]=useState(''),[notes,setNotes]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[error,setError]=useState<Error|null>(null);
 const q=useQuery(()=>request(`commercial/?conversation=${selected||''}&page=${page}&q=${encodeURIComponent(search)}&paused=${filter==='human'?1:0}`),[selected,page,search,filter]);
 const d=q.data, c=d?.selected;
 useEffect(()=>{const timer=window.setInterval(()=>q.reload(),10000);return()=>window.clearInterval(timer);},[]);
 useEffect(()=>{setNotes(c?.notes||'');},[c?.id,c?.notes]);
 async function act(action:string,extra:Record<string,unknown>={}){
   setBusy(true);setError(null);setNotice('');
   try{const r=await request('commercial/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,conversation:selected,...extra})});setNotice(r.detail||'Atualizado.');if(action==='send_human')setDraft('');q.reload();}
   catch(e){setError(e as Error);}finally{setBusy(false);}
 }
 return <section className="commercial-inbox-page">
  <header className="page-heading"><div><p className="eyebrow">VemDeDelivery · atendimento</p><h1>Inbox comercial</h1><p className="muted">Atendimento humano e acompanhamento de leads. Atualização automática a cada 10 segundos.</p></div><div className="heading-actions"><Link className="button secondary" to={panelUrl('comercial')}>Configurar agente</Link><button className="secondary" onClick={q.reload}>Atualizar</button></div></header>
  <Feedback error={error}>{notice&&<p role="status">{notice}</p>}</Feedback>
  {d?.pilot?.pending_count>0&&<p className="commercial-alert" role="status">Há {d.pilot.pending_count} transferência(s) aguardando atendimento humano.</p>}
  <Feedback loading={q.loading&&!d} error={q.error}>{d&&<div className="commercial-chat-shell">
    <aside className="commercial-chat-contacts"><div className="commercial-chat-filters"><label>Buscar contato<input value={search} onChange={e=>{setSearch(e.target.value);setPage(1);}} placeholder="Nome ou telefone"/></label><label>Filtro<select value={filter} onChange={e=>{setFilter(e.target.value);setPage(1);}}><option value="all">Todas</option><option value="human">Aguardando humano</option></select></label></div>
    <div className="commercial-chat-list">{d.conversations.map((x:any)=><button key={x.id} className="commercial-chat-contact" aria-pressed={selected===x.id} onClick={()=>setSelected(x.id)}><span><strong>{x.name||x.phone}</strong><small>{x.phone}</small></span><span className="commercial-chat-meta"><small>{new Date(x.updated_at).toLocaleString('pt-BR')}</small><span>{x.paused?'👤 Humano':'🤖 IA'} · {stages[x.stage]||x.stage}</span></span></button>)}{!d.conversations.length&&<p className="muted">Nenhuma conversa encontrada.</p>}</div>
    <Pagination page={d.pagination.page} pages={d.pagination.pages} size={10} onPage={setPage} onSize={()=>{}}/>
    </aside>
    <div className="commercial-chat-main">{c?<><div className="commercial-chat-header"><div><h2>{c.name||c.phone}</h2><p className="muted">{c.phone} · {c.paused?'Atendimento humano':'Agente disponível'}{c.reason&&` · ${c.reason}`}</p></div><div className="heading-actions"><button disabled={busy} onClick={()=>act('takeover')}>Assumir atendimento</button><button className="secondary" disabled={busy||c.opted_out} onClick={()=>act('resume')}>Devolver à IA</button></div></div>
      <div className="commercial-chat-thread" aria-label="Histórico da conversa">{c.messages.map((m:any)=><article key={m.id} className={`commercial-chat-bubble ${m.from_me?'outgoing':'incoming'}`}><p>{m.text}</p><small>{new Date(m.created_at).toLocaleString('pt-BR')} · {m.state}</small>{m.reply&&<div className="commercial-chat-reply"><strong>Agente:</strong> {m.reply}</div>}</article>)}</div>
      <div className="commercial-chat-compose"><label>Responder pelo painel<textarea value={draft} maxLength={3000} onChange={e=>setDraft(e.target.value)} disabled={!c.paused||!d.control.human_send_enabled||busy} placeholder={d.control.human_send_enabled?'Escreva sua mensagem após assumir a conversa':'Envio manual desativado no servidor'} rows={3}/></label><button disabled={busy||!draft.trim()||!c.paused||!d.control.human_send_enabled} onClick={()=>act('send_human',{text:draft})}>Enviar no WhatsApp</button><p className="muted">Mensagens com confirmação incerta não são reenviadas automaticamente. A função exige autorização na produção.</p></div>
      <details className="commercial-chat-details"><summary>Dados do lead e observações</summary><label>Etapa<select value={c.stage} disabled={busy} onChange={e=>act('lead',{stage:e.target.value,notes})}>{Object.entries(stages).map(([key,value])=><option key={key} value={key}>{value}</option>)}</select></label><label>Observações internas<textarea rows={4} maxLength={4000} value={notes} onChange={e=>setNotes(e.target.value)}/></label><button className="secondary" disabled={busy} onClick={()=>act('lead',{stage:c.stage,notes})}>Salvar observações</button></details>
      </>:<div className="commercial-chat-empty">Selecione uma conversa para visualizar as mensagens e atender o cliente.</div>}</div>
    </div>}</Feedback>
 </section>;
}
