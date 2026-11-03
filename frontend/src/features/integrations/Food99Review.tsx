import './Food99OperationalSafety.css';
import { useState } from 'react';
import { request } from '../../api/client';
import { useQuery } from '../../hooks/useQuery';
import { Feedback } from '../../components/Feedback';

type ReviewOrder = {
  id: number; external_id: string; state: string; status_code: number;
  item_count: number; amount_minor: number; change_count: number;
  revision_count: number; updated_at: string; app_shop_id: string;
};
type ReviewList = {results: ReviewOrder[]; page: number; pages: number; total: number; operational_enabled: boolean};
type Revision = {version: number; status_code: number; created_at: string};
type ReviewDetail = {
  order: ReviewOrder; revisions: Revision[];
  items?: Array<{name: string; quantity: number; line_total_minor: number; notes: string;
    options: Array<{option_name: string; price: string}>}>;
  financials?: {total_minor: number; real_pay_minor: number; delivery_fee_minor: number;
    discount_minor: number; currency_confirmed: boolean}|null;
  detail_error?: string|null;
};
type ReviewMeta = {fingerprint: string; state: string; status_policy: {mapped: boolean; reason: string}; operational_enabled: boolean};
type Summary = {total: number; by_state: Record<string, number>; operational_enabled: boolean};
type DiffItem = {code: string; name: string; quantity: number; line_total_minor: number; options: Array<{option_name: string; price: string}>};
type Diff = {
  from_version: number; to_version: number; status: {before: number; after: number}; status_changed: boolean;
  money_changes: Array<{field: string; before_minor: number; after_minor: number}>;
  item_changes: Array<{position: number; before: DiffItem|null; after: DiffItem|null}>;
  semantic_changes: boolean; ordering_only: boolean;
  fulfillment_changed: boolean; payment_changed: boolean; notes_changed: boolean;
  currency_confirmed: boolean; operational_enabled: boolean;
};

const brl = (value: number) => (value/100).toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
const date = (value: string) => new Date(value).toLocaleString('pt-BR');
const stateLabel = (state: string) => ({changed: 'Alterado · revisar', review: 'Aguardando revisão', reviewed: 'Revisado (somente sandbox)'}[state] || state);
const moneyNames: Record<string, string> = {total: 'Total', real_pay: 'Pago informado', delivery_fee: 'Entrega', discount: 'Descontos'};

export function Food99Review() {
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number|null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [actionError, setActionError] = useState('');
  const [comparison, setComparison] = useState<Diff|null>(null);
  const [compareBusy, setCompareBusy] = useState(false);
  const listing = useQuery<ReviewList>(() => request(`integrations/99food/review/?page=${page}`), [page]);
  const summary = useQuery<Summary>(() => request('integrations/99food/review/summary/'));
  const detail = useQuery<ReviewDetail>(
    () => selected === null ? Promise.resolve({order: {} as ReviewOrder, revisions: []}) : request(`integrations/99food/review/${selected}/`),
    [selected],
  );
  const meta = useQuery<ReviewMeta>(
    () => selected === null ? Promise.resolve({fingerprint: '', state: '', status_policy: {mapped: false, reason: ''}, operational_enabled: false}) : request(`integrations/99food/review/${selected}/acknowledge/`),
    [selected],
  );
  function reload() {listing.reload(); summary.reload(); detail.reload(); meta.reload();}
  function select(id: number|null) {setSelected(id); setNotice(''); setActionError(''); setComparison(null);}
  async function action(kind: 'acknowledge'|'refresh') {
    if (selected === null || busy || !meta.data) return;
    setBusy(true); setNotice(''); setActionError(''); setComparison(null);
    try {
      const body = kind === 'acknowledge' ? {fingerprint: meta.data.fingerprint} : {};
      const result = await request<{result: string}>(`integrations/99food/review/${selected}/${kind}/`, {
        method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body),
      });
      setNotice(kind === 'acknowledge' ? 'Revisão registrada no sandbox. Pedido NÃO liberado para operação.' : `Consulta concluída: ${result.result}.`);
      reload();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Não foi possível concluir a operação.');
      reload();
    } finally {setBusy(false);}
  }
  async function compare() {
    if (selected === null || compareBusy || !detail.data || detail.data.revisions.length < 2) return;
    setCompareBusy(true); setActionError(''); setComparison(null);
    const [latest, previous] = detail.data.revisions;
    try {
      const response = await request<Diff>(`integrations/99food/review/${selected}/compare/?from=${previous.version}&to=${latest.version}`);
      setComparison(response);
    } catch (error) {setActionError(error instanceof Error ? error.message : 'Comparação indisponível.');}
    finally {setCompareBusy(false);}
  }
  return <section className="card" aria-label="Revisão de pedidos 99Food">
    <div className="page-heading"><div><h2>99Food · Acompanhamento do sandbox</h2>
      <p>Pedidos isolados da operação. Revisar não significa aprovar pagamento, moeda ou status externo.</p></div>
      <button type="button" className="secondary" onClick={reload}>Atualizar painel</button>
    </div>
    <Feedback loading={summary.loading} error={summary.error}>
      {summary.data && <p role="status"><strong>{summary.data.total}</strong> pedido(s) · {summary.data.by_state.review || 0} aguardando · {summary.data.by_state.changed || 0} alterado(s) · {summary.data.by_state.reviewed || 0} revisado(s)</p>}
    </Feedback>
    <Feedback loading={listing.loading} error={listing.error}>
      {listing.data && <>
        {!listing.data.results.length && <p>Nenhum pedido 99Food aguardando revisão nesta loja.</p>}
        {!!listing.data.results.length && <div className="food99-review-table" style={{overflowX: 'auto'}}><table><thead><tr>
          <th>Pedido</th><th>Status externo</th><th>Itens</th><th>Total informado*</th><th>Histórico</th><th>Revisão</th><th>Ações</th>
        </tr></thead><tbody>{listing.data.results.map(row => <tr key={row.id}>
          <td>{row.external_id}<div><small>ID interno: {row.id}</small></div></td><td>{row.status_code} (não homologado)</td><td>{row.item_count}</td>
          <td>{brl(row.amount_minor)}</td><td>{row.revision_count} versão(ões), {row.change_count} mudança(s)</td>
          <td>{stateLabel(row.state)}</td>
          <td><button type="button" className="secondary" onClick={() => select(row.id)}>Revisar pedido</button></td>
        </tr>)}</tbody></table></div>}
        <p><small>*Valores apresentados como BRL apenas para inspeção; moeda e composição financeira pendentes de homologação.</small></p>
        <div style={{display: 'flex', gap: 12, alignItems: 'center'}}>
          <button type="button" className="secondary" disabled={page<=1} onClick={()=>{setPage(p=>p-1);select(null);}}>Anterior</button>
          <span>Página {listing.data.page} de {listing.data.pages} · {listing.data.total} pedido(s)</span>
          <button type="button" className="secondary" disabled={page>=listing.data.pages} onClick={()=>{setPage(p=>p+1);select(null);}}>Próxima</button>
        </div>
      </>}
    </Feedback>
    {selected!==null && <div className="card" style={{marginTop:16}}>
      <button type="button" className="secondary" onClick={()=>select(null)}>Fechar revisão</button>
      <h3>Revisão do pedido</h3>
      {notice && <p role="status">{notice}</p>}
      {actionError && <p role="alert">{actionError}</p>}
      <Feedback loading={detail.loading || meta.loading} error={detail.error || meta.error}>
        {detail.data && detail.data.order?.id === selected && meta.data && <>
          <p>Pedido {detail.data.order.external_id} · observação {date(detail.data.order.updated_at)}</p>
          <p><strong>{stateLabel(meta.data.state)}</strong> · Estado externo {detail.data.order.status_code} (sem mapeamento operacional).</p>
          <p><small>{meta.data.status_policy.reason}</small></p>
          <div style={{display:'flex', gap:12, flexWrap:'wrap', marginBottom:16}}>
            <button type="button" className="secondary" disabled={busy} onClick={()=>action('refresh')}>Consultar atualização na 99Food</button>
            <button type="button" disabled={busy || meta.data.state==='reviewed'} onClick={()=>action('acknowledge')}>Marcar como revisado</button>
            <button type="button" className="secondary" disabled={compareBusy || detail.data.revisions.length<2} onClick={compare}>Comparar últimas versões</button>
          </div>
          <p><small>As ações acima não aceitam, cancelam nem sincronizam pedidos com o KDS. Uma nova alteração desfaz a marcação de revisado.</small></p>
          {detail.data.detail_error && <p role="status">{detail.data.detail_error}</p>}
          {!!detail.data.items?.length && <div style={{overflowX:'auto'}}><h4>Itens e adicionais</h4><table><thead><tr><th>Produto</th><th>Qtd.</th><th>Total da linha*</th><th>Observações e adicionais</th></tr></thead><tbody>{detail.data.items.map((item,i)=><tr key={i}><td>{item.name}</td><td>{item.quantity}</td><td>{brl(item.line_total_minor)}</td><td>{item.notes || '—'}{item.options?.length > 0 && <ul>{item.options.map((option,j)=><li key={j}>{option.option_name} · {option.price}</li>)}</ul>}</td></tr>)}</tbody></table></div>}
          {detail.data.financials && <div><h4>Resumo financeiro do provedor*</h4><p>Valor total: {brl(detail.data.financials.total_minor)} · Pago informado: {brl(detail.data.financials.real_pay_minor)} · Entrega: {brl(detail.data.financials.delivery_fee_minor)} · Descontos: {brl(detail.data.financials.discount_minor)}</p></div>}
          <p><small>*Moeda, taxas e conciliação ainda não homologadas.</small></p>
          <h4>Versões registradas</h4>
          {!detail.data.revisions.length && <p>Sem versões registradas.</p>}
          <ul>{detail.data.revisions.map(rev=><li key={rev.version}>Versão {rev.version} · status {rev.status_code} · {date(rev.created_at)}</li>)}</ul>
          {comparison && <div className="card" aria-label="Comparação de versões">
            <h4>Comparação das versões {comparison.from_version} → {comparison.to_version}</h4>
            <p>Status externo: {comparison.status.before} → {comparison.status.after}</p>
            {comparison.ordering_only && <p role="status">As versões não apresentam alterações comerciais relevantes. A diferença pode ter sido apenas a ordem dos produtos ou adicionais retornados pela 99Food.</p>}
            {comparison.fulfillment_changed && <p>Modalidade de entrega alterada (revisar no provedor).</p>}
            {comparison.payment_changed && <p>Modalidade ou indicação de pagamento alterada (não homologada).</p>}
            {comparison.notes_changed && <p>Observações de itens alteradas. Consulte os detalhes do pedido para revisar.</p>}
            {!!comparison.money_changes.length && <ul>{comparison.money_changes.map(m=><li key={m.field}>{moneyNames[m.field] || m.field}: {brl(m.before_minor)} → {brl(m.after_minor)}</li>)}</ul>}
            {!!comparison.item_changes.length && <ul>{comparison.item_changes.map(item=><li key={item.position}>Item {item.position}: {item.before?.name || 'não existia'} → {item.after?.name || 'removido'} (quantidade {item.before?.quantity ?? 0} → {item.after?.quantity ?? 0}; adicionais e valores também comparados)</li>)}</ul>}
          </div>}
        </>}
      </Feedback>
    </div>}
  </section>;
}
