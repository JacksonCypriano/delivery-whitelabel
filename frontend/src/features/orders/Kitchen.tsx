import {Monitor} from '../../components/Monitor';
import {useEffect,useState} from 'react';
import {request} from '../../api/client';
import {useQuery} from '../../hooks/useQuery';
import {useOrderRealtime} from './OrdersBoard';
import {TransitionDialog} from './TransitionDialog';
import {Feedback} from '../../components/Feedback';
import {itemDetails,actionLabel} from './orderHelpers';
export function Kitchen(){
 const q=useQuery(()=>request('kitchen/'));const realtime=useOrderRealtime(q.reload);
 const [selected,setSelected]=useState<any>(null),[busy,setBusy]=useState(false),[error,setError]=useState<Error|null>(null),[,tick]=useState(0);

 useEffect(()=>{const timer=setInterval(()=>tick(n=>n+1),15000);return()=>clearInterval(timer);},[]);
 async function action(id:number,body:any){setBusy(true);setError(null);try{await request(`kitchen/${id}/`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});setSelected(null);q.reload();}catch(e){setError(e as Error);}finally{setBusy(false);}}
 return <Monitor><div className="kitchen-screen"><div className="page-heading"><div><p className="eyebrow">Cozinha · {realtime==='online'?'Ao vivo':'Atualização automática'}</p><h1>KDS</h1></div></div><Feedback loading={q.loading} error={q.error||error}>{q.data&&<div className="kitchen-columns">{[['confirmed','Aguardando preparo'],['preparing','Em preparo'],['ready','Prontos']].map(([status,label])=><section key={status}><h2>{label}</h2>{q.data.orders.filter((o:any)=>status==='ready'?['ready','ready_for_pickup'].includes(o.status):o.status===status).map((o:any)=>{
 const minutes=Math.max(0,Math.floor((Date.now()-new Date(o.created_at).getTime())/60000));
 const preparing=Math.max(0,Math.floor((Date.now()-new Date(o.status_updated_at).getTime())/60000));
 return <article className={`card kitchen-card ${o.late?'late':''}`} key={o.id}><header><strong>#{o.id} · {o.delivery_label}</strong><button className="secondary" disabled={busy} onClick={()=>action(o.id,{priority:!o.kitchen_priority})}>{o.kitchen_priority?'★ Prioritário':'Priorizar'}</button></header><p>{o.scheduled_for&&<>Agendado: {new Date(o.scheduled_for).toLocaleString("pt-BR")} · </>}{o.customer_name} · há {minutes} min</p>{o.status==='preparing'&&<p>Em preparo há {preparing} min</p>}{o.late&&<strong className="late-text">Prazo de preparo excedido</strong>}{o.items.map((i:any)=><section key={i.id}><h3>{i.quantity}× {i.name}</h3>{itemDetails(i.combination_details).map((line:string,n:number)=><p key={n}>{line}</p>)}{i.notes&&<p className="operation-note">{i.notes}</p>}</section>)}{o.allowed_transitions.map((a:any)=><button disabled={busy} key={a.value} onClick={()=>setSelected({order:o,status:a.value})}>{actionLabel[a.value]||a.label}</button>)}</article>;})}</section>)}</div>}</Feedback>{selected&&<TransitionDialog order={selected.order} status={selected.status} settings={q.data.notification_settings} busy={busy} error={error} onClose={()=>setSelected(null)} onConfirm={options=>action(selected.order.id,{status:selected.status,...options})}/>}</div></Monitor>;
}
