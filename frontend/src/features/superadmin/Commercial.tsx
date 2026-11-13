import { SectionTabs } from "../../components/SectionTabs";
import {useState,useEffect} from 'react';
import {Link} from 'react-router-dom';
import {panelUrl} from '../../panel';
import {request} from '../../api/client';
import {useQuery} from '../../hooks/useQuery';
import {Feedback} from '../../components/Feedback';
import {Pagination} from '../../components/Pagination';

const stages:Record<string,string>={new:'Novo',attending:'Em atendimento',qualified:'Qualificado',demo:'Demonstração',negotiation:'Negociação',converted:'Convertido',lost:'Perdido'};
export function Commercial(){
 const [selected,setSelected]=useState<number|null>(null),[page,setPage]=useState(1),[search,setSearch]=useState(''),[onlyHuman,setOnlyHuman]=useState(false);
 const q=useQuery(()=>request(`commercial/?conversation=${selected||''}&page=${page}&q=${encodeURIComponent(search)}&paused=${onlyHuman?1:0}`),[selected,page,search,onlyHuman]);
 const [busy,setBusy]=useState(false),[error,setError]=useState<Error|null>(null),[notice,setNotice]=useState(''),[remote,setRemote]=useState<any>({}),[instance,setInstance]=useState('');
 const [pilotPhone,setPilotPhone]=useState('');
 const [notifyPhone,setNotifyPhone]=useState('5511983491206');
 const [article,setArticle]=useState({slug:'',title:'',body:'',source_url:'',published:true});
 async function act(action:string,data:any={}){setBusy(true);setError(null);setNotice('');try{const r=await request('commercial/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,...data})});setRemote(r);setNotice(r.detail||'Consulta concluída.');q.reload();}catch(e){setError(e as Error);}finally{setBusy(false);}}
 useEffect(()=>{const timer=window.setInterval(q.reload,15000);return()=>window.clearInterval(timer);},[]);
 const d=q.data,c=d?.selected;
 useEffect(()=>{if(d?.control?.handoff_notify_phone)setNotifyPhone(d.control.handoff_notify_phone);},[d?.control?.handoff_notify_phone]);
 return <><div className="page-heading"><div><p className="eyebrow">Aquisição · VemDeDelivery</p><h1>Agente comercial</h1><p className="muted">Atendimento receptivo da plataforma, com conhecimento revisado e transferência humana.</p></div><div className="heading-actions"><Link className="button" to={panelUrl("comercial/inbox")}>Abrir Inbox{d?.pilot?.pending_count ? ` · ${d.pilot.pending_count} pendentes` : ""}</Link><button className="secondary" onClick={q.reload}>Atualizar</button></div></div>
 <Feedback error={error||q.error}>{notice&&<p role="status">{notice}</p>}</Feedback><Feedback loading={q.loading && !q.data}>{d&&<>
 <div className="order-summary-strip">{d.metrics.map((m:any)=><span key={m.stage}><strong>{m.count}</strong> {stages[m.stage]}</span>)}</div>
 <SectionTabs label="Configurações do agente comercial" sections={[
 {id:"connection",label:"Conexão",content:<> <section className="card"><h2>Conexão dedicada</h2><p>{d.control.instance||'Nenhuma instância vinculada'} · {d.control.enabled?'Respostas ativas':'Respostas pausadas'}</p>{!d.control.server_enabled&&<p role="status">O servidor mantém o envio desativado. Configure e valide em homologação antes de ativar.</p>}
 <div className="heading-actions"><button disabled={busy} onClick={()=>act('instances')}>Buscar instâncias</button><button disabled={busy||!d.control.instance} className="secondary" onClick={()=>act('status')}>Verificar conexão</button><button disabled={busy||!d.control.instance} className="secondary" onClick={()=>act('connect')}>Conectar / QR Code</button><button disabled={busy||!d.control.instance} className="secondary" onClick={()=>act('restart')}>Reconectar</button><button disabled={busy||!d.control.instance} className="secondary" onClick={()=>act('logout')}>Desconectar</button><button disabled={busy} onClick={()=>act(d.control.enabled?'pause':'enable',d.control.enabled?{}:{confirm_pilot:true})}>{d.control.enabled?'Pausar respostas':'Ativar respostas'}</button></div>
 <div className="board-toolbar"><label>Instância<select value={instance} onChange={e=>setInstance(e.target.value)}><option value="">Selecionar existente</option>{(remote.instances||[]).map((n:string)=><option key={n}>{n}</option>)}</select></label><button disabled={busy||!instance||d.control.enabled} onClick={()=>act('bind',{instance})}>Vincular e configurar callback</button></div>
 <details><summary>Criar instância exclusiva</summary><label>Nome<input value={instance} onChange={e=>setInstance(e.target.value)} placeholder="vdd-comercial-hml"/></label><button disabled={busy||!instance||d.control.enabled} onClick={()=>act('create',{instance})}>Criar instância</button><p className="muted">Use instância exclusiva da plataforma. Compartilhar com OTP exige configuração explícita no servidor e bloqueio dos destinatários de códigos.</p></details>
 {remote.connection&&<p role="status">Estado: {remote.connection}</p>}{remote.qr&&<img src={remote.qr} alt="QR Code para conectar o WhatsApp comercial" width={250}/>}
 </section>
</>},
 {id:"safety",label:"Piloto e alertas",content:<> <section className="card"><h2>Piloto restrito · segurança</h2>
 <p role="status">Somente números autorizados podem receber respostas automáticas; destinatários de OTP são excluídos da IA comercial. O envio permanece sujeito à chave global e ao controle da instância.</p>
 <p>Contatos excluídos por OTP: <strong>{d.pilot?.otp_excluded_count||0}</strong>. Bloqueio permanente e sem exibição de códigos.</p>
 <form className="board-toolbar" onSubmit={e=>{e.preventDefault();void act('pilot_allow',{phone:pilotPhone.replace(/\D/g,'')}).then(()=>setPilotPhone(''));}}>
 <label>Telefone autorizado para teste (55 + DDD + número)<input required inputMode="numeric" value={pilotPhone} onChange={e=>setPilotPhone(e.target.value)} placeholder="5511999999999"/></label>
 <button disabled={busy||!pilotPhone||d.control.enabled} type="submit">Autorizar teste</button>
 </form>
 <p>Contatos autorizados: {d.pilot?.allowed?.length||0}</p>
 {(d.pilot?.allowed||[]).map((x:any)=><div key={x.phone} className="board-toolbar"><span>{x.phone}</span><button className="secondary" disabled={busy||d.control.enabled} onClick={()=>act('pilot_revoke',{phone:x.phone})}>Revogar</button></div>)}
 <h3>Notificações operacionais pelo WhatsApp</h3>
 <p>Destinatário inicial: 5511983491206. Os avisos usam a instância comercial conectada e não alteram a lista do piloto. O envio vem <strong>desabilitado</strong> até autorização explícita nesta tela.</p>
 <form className="board-toolbar" onSubmit={e=>{e.preventDefault();void act('handoff_notify',{phone:notifyPhone.replace(/\D/g,''),enabled:!d.control.handoff_notify_enabled});}}>
  <label>WhatsApp para receber alertas (55 + DDD + número)<input required inputMode="numeric" value={notifyPhone} onChange={e=>setNotifyPhone(e.target.value)} placeholder="5511983491206"/></label>
  <button type="submit" disabled={busy||!/^55[1-9][0-9]{9,10}$/.test(notifyPhone.replace(/\D/g,''))}>{d.control.handoff_notify_enabled?'Desativar avisos':'Habilitar avisos'}</button>
  <button type="button" className="secondary" disabled={busy||!d.control.handoff_notify_enabled} onClick={()=>act('handoff_notify',{phone:notifyPhone.replace(/\D/g,''),enabled:true})}>Salvar número</button>
 </form>
 <p role="status">Avisos WhatsApp: <strong>{d.control.handoff_notify_enabled?'Habilitados':'Desabilitados'}</strong>. Tentativas incertas não são reenviadas automaticamente.</p>
 <h3>Transferências aguardando resposta: {d.pilot?.pending_count||0}</h3>
 {(d.pilot?.alerts||[]).map((a:any)=><div key={a.id} className="board-toolbar"><span>{a.name||a.phone||`Conversa #${a.conversation_id}`} · {a.reason}</span><Link className="button secondary" to={`${panelUrl('comercial/inbox')}?conversation=${a.conversation_id}`}>Ver conversa</Link>{a.wa_link&&<a className="button secondary" href={a.wa_link} target="_blank" rel="noopener noreferrer">Abrir WhatsApp</a>}</div>)}
 <p className="muted">As notificações saem dos pendentes após uma resposta humana efetiva, não apenas por assumir a conversa. Respostas por outro número precisam de confirmação manual na Inbox.</p>
 </section>
</>},
 {id:"catalog",label:"Catálogo",content:<> <details className="card" open><summary>Catálogo comercial · {d.published?'Revisado e publicado':'Revisão necessária'}</summary><p>Os valores abaixo vêm dos planos oficiais. Publicar autoriza o agente a consultá-los; não altera assinaturas.</p><div className="table-wrap"><table><thead><tr><th>Plano</th><th>Meses</th><th>Base mensal</th><th>Desconto</th><th>Total antecipado</th></tr></thead><tbody>{d.catalog.data.plans.map((p:any)=><tr key={p.id}><td>{p.name}</td><td>{p.months}</td><td>R$ {p.monthly_price}</td><td>{p.discount}%</td><td>R$ {p.total}</td></tr>)}</tbody></table></div><h3>Serviços opcionais</h3>{d.catalog.data.services.map((s:any)=><p key={s.code}>{s.name} · R$ {s.price}</p>)}<p>Meios habilitados: {d.catalog.data.payments.join(', ')}</p><p>{d.catalog.data.terms}</p>{!d.catalog.valid&&<p role="alert">Catálogo diferente da política aprovada: base R$ 149,90 e descontos 0%, 5%, 10% e 15%. O agente não poderá ofertar preços até a reconciliação.</p>}<button disabled={busy||!d.catalog.valid} onClick={()=>act('publish_catalog',{fingerprint:d.catalog.fingerprint})}>Aprovar versão atual para o agente</button></details>
</>},
 {id:"knowledge",label:"Conhecimento",content:<> <details className="card" open><summary>Conhecimento comercial revisado ({d.articles.length})</summary><p>Cadastre fatos confirmados sobre o produto. Diferencie recursos disponíveis e em homologação. Cada publicação cria uma revisão; preços são sempre consultados no catálogo.</p>{d.articles.map((a:any)=><article key={a.id}><strong>{a.title} · v{a.version} · {a.published?'Publicado':'Rascunho'}</strong><p>{a.body}</p><button className="secondary" onClick={()=>setArticle({slug:a.slug,title:a.title,body:a.body,source_url:a.source_url,published:true})}>Nova revisão</button></article>)}<form onSubmit={e=>{e.preventDefault();void act('article',article);}}><div className="settings-grid"><label>Identificador<input required value={article.slug} pattern="[a-z0-9-]+" onChange={e=>setArticle({...article,slug:e.target.value})}/></label><label>Título<input required maxLength={160} value={article.title} onChange={e=>setArticle({...article,title:e.target.value})}/></label><label>Fonte verificável<input type="url" value={article.source_url} onChange={e=>setArticle({...article,source_url:e.target.value})}/></label></div><label>Resposta revisada<textarea required maxLength={1100} rows={5} value={article.body} onChange={e=>setArticle({...article,body:e.target.value})}/></label><label className="toggle-row"><input type="checkbox" checked={article.published} onChange={e=>setArticle({...article,published:e.target.checked})}/>Disponível ao agente (desmarque para retirar este artigo)</label><button disabled={busy}>Salvar revisão</button></form></details>
</>},
 {id:"activity",label:"Atendimento e atividade",content:<> <section className="card"><h2>Atendimento comercial</h2><p>O inbox foi transferido para uma página exclusiva com contatos, histórico, atendimento humano e anotações.</p><Link className="button" to={panelUrl("comercial/inbox")}>Abrir inbox comercial</Link></section>
 <details className="card"><summary>Atividade recente</summary>{d.events.map((e:any,i:number)=><p key={i}>{new Date(e.created_at).toLocaleString('pt-BR')} · {e.action}{e.conversation_id&&` · conversa #${e.conversation_id}`}</p>)}</details></>},
 ]}/>
 </>}</Feedback></>;
}
