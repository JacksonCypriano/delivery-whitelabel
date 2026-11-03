import './Food99OperationalSafety.css';
import {useState} from 'react';
import {request} from '../../api/client';
import {useQuery} from '../../hooks/useQuery';
import {Feedback} from '../../components/Feedback';

type Blocker = {code:string; detail:string; status?:number};
type Readiness = {
  sandbox_linked:boolean; staged_count:number; reviewed_count:number;
  operational_enabled:boolean; can_promote_orders:boolean;
  can_receive_webhooks:boolean; can_send_transitions:boolean;
  blockers:Blocker[];
};
type Projection = {
  external_id:string; status_code:number; preview_only:boolean;
  operational_enabled:boolean; kds_visible:boolean; total_minor:number;
  payment_method:string; delivery_by:string; paid_unverified:boolean;
  items:Array<{name:string; quantity:number; line_total_minor:number;
    option_count:number; options:Array<{name:string;price:string}>}>;
  allowed_transitions:string[]; message:string;
};
type Integrity = {scanned:number;total:number;truncated:boolean;affected_scanned:number;findings:Array<{id:number;issues:string[]}>;note:string};
type DryRun = {
  external_id:string; status_code:number; staging_state:string;
  items_count:number; quantity_total:number; line_total_minor:number; order_total_minor:number;
  delivery_by:string; payment_method:string; payment_confirmed:boolean;
  operational_enabled:boolean; kds_visible:boolean; orders_created:number;
  contract_gates:Array<{code:string;label:string;approved:boolean}>;
  diagnostics:Array<{code:string;label:string}>; message:string;
};
type BatchDryRun = {results:Array<{id:number;status_code?:number;items_count?:number;
  error?:string; diagnostics?:Array<{code:string;label:string}>;operational_enabled:boolean}>;
  orders_created:number;operational_enabled:boolean};
type BatchResult = {results:Array<{id:number;result:string;status_code?:number}>};

const brl = (cents:number) => (cents/100).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});

export function Food99OperationalSafety(){
  const state=useQuery<Readiness>(()=>request('integrations/99food/operational-readiness/'));
  const [orderId,setOrderId]=useState('');
  const [selectedId,setSelectedId]=useState('');
  const [preview,setPreview]=useState<Projection|null>(null);
  const [dryRun,setDryRun]=useState<DryRun|null>(null);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const [error,setError]=useState('');
  const [batchIds,setBatchIds]=useState('');
  const [results,setResults]=useState<BatchResult|null>(null);
  const [batchDryRun,setBatchDryRun]=useState<BatchDryRun|null>(null);
  const integrity=useQuery<Integrity>(()=>request('integrations/99food/integrity-audit/'));

  async function run(action:()=>Promise<void>){
    setBusy(true);setError('');setMessage('');
    try { await action();state.reload();integrity.reload(); }
    catch(e){setError(e instanceof Error?e.message:'Não foi possível concluir a operação.');}
    finally{setBusy(false);}
  }
  async function stage(){
    if(!/^\d{1,30}$/.test(orderId)){setError('Informe um número de pedido válido.');return;}
    await run(async()=>{
      const result=await request<{result:string;external_id:string}>('integrations/99food/sandbox-stage/',{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id:orderId}),
      });
      setMessage(`Consulta do pedido ${result.external_id}: ${result.result}. Apenas sandbox.`);
    });
  }
  async function inspect(){
    if(!/^\d+$/.test(selectedId) || Number(selectedId)<=0){setError('Informe o ID interno de revisão válido.');return;}
    await run(async()=>{
      const result=await request<Projection>(`integrations/99food/operational-preview/${selectedId}/`);
      setPreview(result);setDryRun(null);setMessage('Prévia montada sem criar pedido ativo.');
    });
  }
  async function simulate(){
    if(!/^\d+$/.test(selectedId) || !Number.isSafeInteger(Number(selectedId)) || Number(selectedId)<1){
      setError('Informe um ID interno de revisão válido.');return;
    }
    await run(async()=>{
      const result=await request<DryRun>(`integrations/99food/operational-dryrun/${selectedId}/`);
      setDryRun(result);setMessage('Diagnóstico gerado sem importar pedidos ou acessar o KDS.');
    });
  }
  function validatedBatchIds():number[]|null {
    const text=batchIds.trim();
    if(!/^\d+(\s*,\s*\d+){0,4}$/.test(text))return null;
    const ids=text.split(',').map(x=>Number(x.trim()));
    if(new Set(ids).size!==ids.length || ids.some(x=>!Number.isSafeInteger(x)||x<1))return null;
    return ids;
  }
  async function simulateBatch(){
    const ids=validatedBatchIds();
    if(!ids){setError('Informe até 5 IDs internos distintos.');return;}
    await run(async()=>{
      const result=await request<BatchDryRun>('integrations/99food/operational-dryrun-batch/',{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids}),
      });
      setBatchDryRun(result);
      setMessage('Diagnóstico do lote concluído sem criar pedidos ativos.');
    });
  }
  async function batch(){
    const ids=validatedBatchIds();
    if(!ids){setError('IDs repetidos ou inválidos. Informe até cinco IDs internos.');return;}
    await run(async()=>{
      const result=await request<BatchResult>('integrations/99food/sandbox-refresh-batch/',{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids}),
      });
      setResults(result);setMessage('Atualização em lote concluída, sem ações remotas de pedido.');
    });
  }
  return <section className="card" aria-label="99Food prontidão operacional">
    <div className="page-heading"><div>
      <h2>99Food · Preparação operacional</h2>
      <p>Consulta, validação e prévia de pedidos. Nenhuma ação libera pedidos no KDS.</p>
    </div><button type="button" className="secondary" onClick={()=>state.reload()} disabled={busy}>Atualizar diagnósticos</button></div>
    <Feedback loading={state.loading} error={state.error}>{state.data&&<>
      <p role="status"><strong>{state.data.operational_enabled?'Operação habilitada':'Operação bloqueada com segurança'}</strong> ·
      {' '}{state.data.staged_count} pedidos em revisão · {state.data.reviewed_count} revisados</p>
      <p>Sandbox {state.data.sandbox_linked?'vinculado':'não vinculado'} · Webhook autenticado: não · Envio de status: não · KDS: não</p>
      <details><summary>Ver pendências para operação real ({state.data.blockers.length})</summary>
        <ul>{state.data.blockers.map((b,i)=><li key={`${b.code}-${i}`}>{b.detail}</li>)}</ul>
      </details>
    </>}</Feedback>
    <div style={{marginTop:16}}>
      <h3>Auditoria estrutural da quarentena</h3>
      <Feedback loading={integrity.loading} error={integrity.error}>
        {integrity.data&&<>
          <p>{integrity.data.scanned} de {integrity.data.total} registros inspecionados ·
             {' '}{integrity.data.affected_scanned} com alerta(s).
             {integrity.data.truncated?' Resultado limitado aos 100 mais recentes.':''}</p>
          {!!integrity.data.findings.length&&<ul>{integrity.data.findings.map(item=><li key={item.id}>
            Revisão interna #{item.id}: {item.issues.join(', ')}
          </li>)}</ul>}
          <p><small>{integrity.data.note}</small></p>
        </>}
      </Feedback>
    </div>
    <div className="food99-form-grid">
      <div className="food99-form-card">
        <div className="food99-form-card__intro"><h3>Consultar novo pedido sandbox</h3>
          <p>Somente leitura na 99Food. O pedido ficará isolado da operação.</p></div>
        <div className="food99-field"><label htmlFor="food99-new-order">ID do pedido 99Food</label>
          <input id="food99-new-order" value={orderId} onChange={e=>setOrderId(e.target.value)} inputMode="numeric" placeholder="Número do pedido"/></div>
        <div className="food99-form-card__actions"><button type="button" disabled={busy} onClick={stage}>Consultar e guardar para revisão</button></div>
      </div>
      <div className="food99-form-card">
        <div className="food99-form-card__intro"><h3>Prévia para Pedidos / KDS</h3>
          <p>Informe o ID interno de revisão. A prévia não cria um Order.</p></div>
        <div className="food99-field"><label htmlFor="food99-staged-id">ID interno da revisão</label>
          <input id="food99-staged-id" value={selectedId} onChange={e=>setSelectedId(e.target.value)} inputMode="numeric" placeholder="Ex.: 1"/></div>
        <div className="food99-form-card__actions food99-form-card__actions--stack">
          <button type="button" className="secondary" disabled={busy} onClick={inspect}>Visualizar prévia isolada</button>
          <button type="button" className="secondary" disabled={busy} onClick={simulate}>Ver diagnóstico operacional</button>
        </div>
      </div>
      <div className="food99-form-card">
        <div className="food99-form-card__intro"><h3>Atualização em lote</h3>
          <p>Até cinco IDs internos existentes, separados por vírgula.</p></div>
        <div className="food99-field"><label htmlFor="food99-batch-ids">IDs internos</label>
          <input id="food99-batch-ids" value={batchIds} onChange={e=>setBatchIds(e.target.value)} placeholder="1, 2, 3"/></div>
        <div className="food99-form-card__actions food99-form-card__actions--stack">
          <button type="button" className="secondary" disabled={busy} onClick={batch}>Consultar lote na 99Food</button>
          <button type="button" className="secondary" disabled={busy} onClick={simulateBatch}>Diagnosticar lote sem consultar API</button>
        </div>
      </div>
    </div>
    {message&&<p role="status">{message}</p>}
    {error&&<p role="alert">{error}</p>}
    {results&&<div><h3>Resultados do lote</h3><ul>{results.results.map(item=><li key={item.id}>Revisão #{item.id}: {item.result}</li>)}</ul></div>}
    {batchDryRun && <div className="food99-dryrun" aria-label="Diagnóstico em lote">
      <div className="food99-dryrun__header"><h3>Diagnóstico de {batchDryRun.results.length} revisões</h3>
        <button className="secondary" type="button" onClick={()=>setBatchDryRun(null)}>Fechar</button></div>
      <p><strong>{batchDryRun.orders_created} pedidos criados.</strong> Nenhuma operação de cozinha habilitada.</p>
      <ul>{batchDryRun.results.map(row=><li key={row.id}>Revisão #{row.id}: {row.error || `${row.items_count} produtos, status ${row.status_code}; ${row.diagnostics?.length || 0} avisos`}</li>)}</ul>
    </div>}
    {dryRun && <div className="food99-dryrun" aria-label="Diagnóstico operacional 99Food">
      <div className="food99-dryrun__header"><div><h3>Diagnóstico de integração — pedido {dryRun.external_id}</h3>
        <p>{dryRun.message}</p></div><button type="button" className="secondary" onClick={()=>setDryRun(null)}>Fechar</button></div>
      <div className="food99-dryrun__stats">
        <div><small>Produtos</small><strong>{dryRun.items_count}</strong></div>
        <div><small>Quantidade</small><strong>{dryRun.quantity_total}</strong></div>
        <div><small>Status externo</small><strong>{dryRun.status_code}</strong></div>
        <div><small>Pedidos criados</small><strong>{dryRun.orders_created}</strong></div>
      </div>
      <p><strong>6 requisitos de contrato ainda bloqueados.</strong> A simulação não faz aceitações, cobranças, transições ou estoque.</p>
      <ul>{dryRun.contract_gates.map(g=><li key={g.code}>{g.label}: {g.approved?'validado':'pendente'}</li>)}</ul>
      {!!dryRun.diagnostics.length && <><h4>Avisos informativos</h4><ul>{dryRun.diagnostics.map(d=><li key={d.code}>{d.label}</li>)}</ul></>}
    </div>}
    {preview&&<div className="card food99-preview" style={{marginTop:16}}>
      <h3>Prévia isolada — Pedido 99Food {preview.external_id}</h3>
      <p>Estado externo {preview.status_code} · {preview.message}</p>
      <p>Total informado: {brl(preview.total_minor)}* · Modalidade: {preview.delivery_by} · Pagamento informado: {preview.payment_method}</p>
      <div style={{overflowX:'auto'}}><table><thead><tr><th>Produto</th><th>Qtd.</th><th>Linha*</th><th>Adicionais</th></tr></thead>
        <tbody>{preview.items.map((item,i)=><tr key={i}><td>{item.name}</td><td>{item.quantity}</td><td>{brl(item.line_total_minor)}</td>
          <td><ul>{item.options.map((o,j)=><li key={j}>{o.name} · {o.price}</li>)}</ul></td>
        </tr>)}</tbody></table></div>
      <p><small>*Valores formatados para inspeção; moeda e composição não homologadas.</small></p>
      <p><strong>Operação: bloqueada.</strong> Não existe botão de aceitar, cancelar ou despachar nesta prévia.</p>
      <button type="button" className="secondary" onClick={()=>setPreview(null)}>Fechar prévia</button>
    </div>}
  </section>;
}
