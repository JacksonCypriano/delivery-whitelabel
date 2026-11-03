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
type ReviewDetail = { order: ReviewOrder; revisions: Revision[]; items?: Array<{name:string;quantity:number;line_total_minor:number;notes:string;options:Array<{option_name:string;price:string}>}>; financials?: {total_minor:number;real_pay_minor:number;delivery_fee_minor:number;discount_minor:number;currency_confirmed:boolean}|null; detail_error?: string|null };
type Revision = {version: number; status_code: number; created_at: string};

export function Food99Review() {
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number | null>(null);
  const listing = useQuery<ReviewList>(() => request(`integrations/99food/review/?page=${page}`), [page]);
  const detail = useQuery<ReviewDetail>(
    () => selected === null ? Promise.resolve({order: {} as ReviewOrder, revisions: []}) : request(`integrations/99food/review/${selected}/`),
    [selected],
  );
  const brl = (minor: number) => (minor / 100).toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
  const date = (value: string) => new Date(value).toLocaleString('pt-BR');
  return <section className="card" aria-label="Revisão de pedidos 99Food">
    <div className="page-heading"><div><h2>99Food · Pedidos em revisão</h2>
      <p>Sandbox: registros isolados da operação. Status numéricos ainda não homologados e nenhuma ação remota habilitada.</p></div>
      <button type="button" className="secondary" onClick={() => {listing.reload(); detail.reload();}}>Atualizar</button>
    </div>
    <Feedback loading={listing.loading} error={listing.error}>
      {listing.data && <>
        {!listing.data.results.length && <p>Nenhum pedido 99Food aguardando revisão nesta loja.</p>}
        {!!listing.data.results.length && <div style={{overflowX: 'auto'}}><table><thead><tr>
          <th>Pedido 99Food</th><th>Status externo</th><th>Itens</th><th>Total informado*</th><th>Revisões</th><th>Estado</th><th></th>
        </tr></thead><tbody>{listing.data.results.map(row => <tr key={row.id}>
          <td>{row.external_id}</td><td>{row.status_code} (não homologado)</td><td>{row.item_count}</td>
          <td>{brl(row.amount_minor)}</td><td>{row.revision_count} versão(ões), {row.change_count} mudança(s)</td>
          <td>{row.state === 'changed' ? 'Alterado · revisão necessária' : 'Aguardando revisão'}</td>
          <td><button type="button" className="secondary" onClick={() => setSelected(row.id)}>Ver histórico</button></td>
        </tr>)}</tbody></table></div>}
        <p><small>*Valor formatado em BRL apenas para leitura no sandbox; composição financeira ainda depende de homologação.</small></p>
        <div style={{display: 'flex', gap: 12, alignItems: 'center'}}>
          <button type="button" className="secondary" disabled={page <= 1} onClick={() => {setPage(p => p - 1); setSelected(null);}}>Anterior</button>
          <span>Página {listing.data.page} de {listing.data.pages} · {listing.data.total} pedido(s)</span>
          <button type="button" className="secondary" disabled={page >= listing.data.pages} onClick={() => {setPage(p => p + 1); setSelected(null);}}>Próxima</button>
        </div>
      </>}
    </Feedback>
    {selected !== null && <div className="card" style={{marginTop: 16}}>
      <button type="button" className="secondary" onClick={() => setSelected(null)}>Fechar histórico</button>
      <h3>Histórico do pedido</h3>
      <Feedback loading={detail.loading} error={detail.error}>
        {detail.data && detail.data.order?.id === selected && <>
          <p>Pedido {detail.data.order.external_id} · última observação {date(detail.data.order.updated_at)}</p>
          {detail.data.detail_error && <p role="status">{detail.data.detail_error}</p>}
          {!!detail.data.items?.length && <div style={{overflowX:'auto'}}><h4>Itens e adicionais</h4><table><thead><tr><th>Produto</th><th>Qtd.</th><th>Total da linha*</th><th>Observações e adicionais</th></tr></thead><tbody>{detail.data.items.map((item,i)=><tr key={i}><td>{item.name}</td><td>{item.quantity}</td><td>{brl(item.line_total_minor)}</td><td>{item.notes || '—'}{item.options?.length > 0 && <ul>{item.options.map((option,j)=><li key={j}>{option.option_name} · {option.price}</li>)}</ul>}</td></tr>)}</tbody></table></div>}
          {detail.data.financials && <div><h4>Resumo financeiro do provedor*</h4><p>Valor total: {brl(detail.data.financials.total_minor)} · Pago informado: {brl(detail.data.financials.real_pay_minor)} · Entrega: {brl(detail.data.financials.delivery_fee_minor)} · Descontos: {brl(detail.data.financials.discount_minor)}</p><p><small>*Valores formatados em BRL para inspeção. Regras financeiras e moeda ainda não homologadas.</small></p></div>}
          {!detail.data.revisions.length && <p>Sem versões registradas.</p>}
          <ul>{detail.data.revisions.map(rev => <li key={rev.version}>
            Versão {rev.version} · status {rev.status_code} · {date(rev.created_at)}
          </li>)}</ul>
        </>}
      </Feedback>
    </div>}
  </section>;
}
