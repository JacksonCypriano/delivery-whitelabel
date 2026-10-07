import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { orders } from "../../api/orders";
import { Feedback, Notice } from "../../components/Feedback";
import { useQuery } from "../../hooks/useQuery";
import { panelUrl } from "../../panel";
import { money } from "./orderHelpers";

type Choice = { group_id: number; option_id: number };
type DraftItem = {
  key: number;
  product_id: string;
  second_product_id: string;
  is_half: boolean;
  quantity: number;
  notes: string;
  notes_half1: string;
  notes_half2: string;
  customizations: Choice[];
  customizations_whole: Choice[];
  customizations_half1: Choice[];
  customizations_half2: Choice[];
};

let nextKey = 1;
const blankItem = (): DraftItem => ({
  key: nextKey++,
  product_id: "",
  second_product_id: "",
  is_half: false,
  quantity: 1,
  notes: "",
  notes_half1: "",
  notes_half2: "",
  customizations: [],
  customizations_whole: [],
  customizations_half1: [],
  customizations_half2: [],
});

function GroupChoices({
  group,
  value,
  onChange,
}: {
  group: any;
  value: Choice[];
  onChange: (value: Choice[]) => void;
}) {
  const selected = value.filter((row) => row.group_id === group.id);
  function toggle(optionId: number, checked: boolean) {
    let rows = value.filter(
      (row) => !(row.group_id === group.id && row.option_id === optionId),
    );
    if (checked) {
      if (selected.length >= group.max_options) return;
      rows = [...rows, { group_id: group.id, option_id: optionId }];
    }
    onChange(rows);
  }
  return (
    <fieldset className="choice-group">
      <legend>
        {group.name || "Adicionais"}
        <small>
          {group.min_options > 0 ? ` obrigatório · mínimo ${group.min_options}` : " opcional"}
          {` · máximo ${group.max_options}`}
        </small>
      </legend>
      <div className="choice-options">
        {group.options.map((option: any) => {
          const checked = selected.some((row) => row.option_id === option.id);
          return (
            <label key={option.id} className="choice-option">
              <input
                type="checkbox"
                checked={checked}
                disabled={!checked && selected.length >= group.max_options}
                onChange={(event) => toggle(option.id, event.target.checked)}
              />
              <span>
                <strong>{option.name}</strong>
                {Number(option.price) > 0 && <small>+ {money(option.price)}</small>}
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function ItemEditor({
  item,
  catalog,
  onChange,
  onRemove,
  canRemove,
}: {
  item: DraftItem;
  catalog: any;
  onChange: (next: DraftItem) => void;
  onRemove: () => void;
  canRemove: boolean;
}) {
  const product = catalog.products.find((row: any) => String(row.id) === item.product_id);
  const groups = product ? catalog.groups[String(product.category_id)] || [] : [];
  const wholeGroups = groups.filter((row: any) => ["whole", "both"].includes(row.apply_to));
  const halfGroups = groups.filter((row: any) => row.apply_to === "half");
  const secondProducts = product
    ? catalog.products.filter(
        (row: any) =>
          row.category_id === product.category_id &&
          row.half_enabled &&
          String(row.id) !== item.product_id,
      )
    : [];

  function selectProduct(id: string) {
    onChange({
      ...blankItem(),
      key: item.key,
      product_id: id,
      quantity: item.quantity || 1,
    });
  }

  return (
    <section className="card manual-item">
      <div className="manual-item-head">
        <h2>Item</h2>
        {canRemove && (
          <button type="button" className="text-button danger-text" onClick={onRemove}>
            Remover
          </button>
        )}
      </div>
      <div className="form-grid compact-grid">
        <label className="field">
          Produto
          <select value={item.product_id} onChange={(e) => selectProduct(e.target.value)}>
            <option value="">Selecione…</option>
            {catalog.categories.map((category: any) => (
              <optgroup key={category.id} label={category.name}>
                {catalog.products
                  .filter((row: any) => row.category_id === category.id)
                  .map((row: any) => (
                    <option key={row.id} value={row.id}>
                      {row.name} · {money(row.price)}
                    </option>
                  ))}
              </optgroup>
            ))}
          </select>
        </label>
        <label className="field quantity-field">
          Quantidade
          <input
            type="number"
            min={product?.min_qty || 1}
            max={product?.max_qty || 99}
            value={item.quantity}
            onChange={(e) => onChange({ ...item, quantity: Math.max(1, Number(e.target.value) || 1) })}
          />
        </label>
      </div>

      {product?.half_enabled && secondProducts.length > 0 && (
        <label className="toggle-row manual-half-toggle">
          <input
            type="checkbox"
            checked={item.is_half}
            onChange={(e) =>
              onChange({
                ...item,
                is_half: e.target.checked,
                second_product_id: "",
                customizations: [],
                customizations_whole: [],
                customizations_half1: [],
                customizations_half2: [],
              })
            }
          />
          Montar meio a meio
        </label>
      )}

      {item.is_half && product && (
        <label className="field">
          Segunda metade
          <select
            value={item.second_product_id}
            onChange={(e) => onChange({ ...item, second_product_id: e.target.value })}
          >
            <option value="">Selecione a segunda metade…</option>
            {secondProducts.map((row: any) => (
              <option key={row.id} value={row.id}>
                {row.name} · {money(row.price)}
              </option>
            ))}
          </select>
          <small>O preço-base do meio a meio segue a regra atual da loja: a metade de maior valor.</small>
        </label>
      )}

      {product && !item.is_half &&
        groups.map((group: any) => (
          <GroupChoices
            key={group.id}
            group={group}
            value={item.customizations}
            onChange={(customizations) => onChange({ ...item, customizations })}
          />
        ))}

      {product && item.is_half && (
        <>
          {wholeGroups.map((group: any) => (
            <GroupChoices
              key={`whole-${group.id}`}
              group={group}
              value={item.customizations_whole}
              onChange={(customizations_whole) => onChange({ ...item, customizations_whole })}
            />
          ))}
          {halfGroups.length > 0 && (
            <div className="half-grid">
              <div>
                <h3>Primeira metade · {product.name}</h3>
                {halfGroups.map((group: any) => (
                  <GroupChoices
                    key={`h1-${group.id}`}
                    group={group}
                    value={item.customizations_half1}
                    onChange={(customizations_half1) => onChange({ ...item, customizations_half1 })}
                  />
                ))}
                <label className="field">
                  Observação da primeira metade
                  <textarea
                    rows={2}
                    value={item.notes_half1}
                    onChange={(e) => onChange({ ...item, notes_half1: e.target.value })}
                  />
                </label>
              </div>
              <div>
                <h3>Segunda metade</h3>
                {halfGroups.map((group: any) => (
                  <GroupChoices
                    key={`h2-${group.id}`}
                    group={group}
                    value={item.customizations_half2}
                    onChange={(customizations_half2) => onChange({ ...item, customizations_half2 })}
                  />
                ))}
                <label className="field">
                  Observação da segunda metade
                  <textarea
                    rows={2}
                    value={item.notes_half2}
                    onChange={(e) => onChange({ ...item, notes_half2: e.target.value })}
                  />
                </label>
              </div>
            </div>
          )}
        </>
      )}

      {product && (
        <label className="field">
          Observação do item
          <textarea
            rows={2}
            maxLength={2000}
            value={item.notes}
            onChange={(e) => onChange({ ...item, notes: e.target.value })}
            placeholder="Ex.: sem cebola, bem passado…"
          />
        </label>
      )}
    </section>
  );
}

function payloadItems(items: DraftItem[]) {
  return items.map((item) => {
    if (item.is_half) {
      return {
        is_half: true,
        product_ids: [item.product_id, item.second_product_id],
        quantity: item.quantity,
        notes: item.notes,
        customizations_whole: item.customizations_whole,
        customizations_half1: item.customizations_half1,
        customizations_half2: item.customizations_half2,
        notes_half1: item.notes_half1,
        notes_half2: item.notes_half2,
      };
    }
    return {
      product_id: item.product_id,
      quantity: item.quantity,
      notes: item.notes,
      customizations: item.customizations,
    };
  });
}

export function ManualOrder() {
  const navigate = useNavigate();
  const catalog = useQuery(() => orders.manualCatalog(), []);
  const [items, setItems] = useState<DraftItem[]>([blankItem()]);
  const [form, setForm] = useState({
    customer_name: "",
    customer_phone: "",
    delivery_type: "pickup",
    payment_method: "pix",
    payment_change_for: "",
    delivery_zip_code: "",
    delivery_street: "",
    delivery_number: "",
    delivery_complement: "",
    delivery_neighborhood: "",
    delivery_city: "",
    delivery_state: "",
    delivery_reference: "",
  });
  const [quote, setQuote] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [messages, setMessages] = useState<any[]>([]);

  useEffect(() => {
    if (!catalog.data) return;
    if (!catalog.data.accepts_pickup && catalog.data.accepts_delivery && form.delivery_type !== "delivery") {
      setForm((current) => ({ ...current, delivery_type: "delivery" }));
    }
  }, [catalog.data, form.delivery_type]);

  const data = useMemo(
    () => ({ ...form, items: payloadItems(items) }),
    [form, items],
  );

  function patchItem(index: number, next: DraftItem) {
    setItems((current) => current.map((row, i) => (i === index ? next : row)));
    setQuote(null);
  }

  async function calculate() {
    setBusy(true);
    setError(null);
    setMessages([]);
    try {
      const result = await orders.quoteManual(data);
      setQuote(result);
      setMessages([{ level: "success", text: "Pedido conferido com os preços atuais do catálogo." }]);
    } catch (e) {
      setError(e as Error);
      setQuote(null);
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    setBusy(true);
    setError(null);
    setMessages([]);
    try {
      const result = await orders.createManual(data);
      navigate(panelUrl(`orders/${result.id}`));
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Link className="back" to={panelUrl("orders")}>← Voltar aos pedidos</Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Balcão · telefone · atendimento</p>
          <h1>Novo pedido manual</h1>
          <p className="muted">Use o mesmo catálogo, preços, adicionais, entrega e estoque do canal online.</p>
        </div>
      </div>
      <Notice messages={messages} />
      <Feedback error={error}><></></Feedback>
      <Feedback loading={catalog.loading} error={catalog.error}>
        {catalog.data && (
          <div className="manual-order-layout">
            <div>
              <section className="card">
                <h2>Cliente</h2>
                <div className="form-grid">
                  <label className="field">Nome
                    <input value={form.customer_name} onChange={(e) => setForm({ ...form, customer_name: e.target.value })} placeholder="Cliente do balcão" />
                  </label>
                  <label className="field">WhatsApp
                    <input value={form.customer_phone} onChange={(e) => setForm({ ...form, customer_phone: e.target.value })} placeholder="(11) 99999-9999" inputMode="tel" />
                    <small>Opcional. Quando informado, permite avisos automáticos de status.</small>
                  </label>
                </div>
              </section>

              {items.map((item, index) => (
                <ItemEditor
                  key={item.key}
                  item={item}
                  catalog={catalog.data}
                  canRemove={items.length > 1}
                  onChange={(next) => patchItem(index, next)}
                  onRemove={() => { setItems((rows) => rows.filter((_, i) => i !== index)); setQuote(null); }}
                />
              ))}
              <button type="button" className="secondary add-item" onClick={() => { setItems([...items, blankItem()]); setQuote(null); }}>
                + Adicionar outro item
              </button>

              <section className="card">
                <h2>Recebimento e pagamento</h2>
                <div className="form-grid">
                  <label className="field">Recebimento
                    <select value={form.delivery_type} onChange={(e) => { setForm({ ...form, delivery_type: e.target.value }); setQuote(null); }}>
                      {catalog.data.accepts_pickup && <option value="pickup">Retirada</option>}
                      {catalog.data.accepts_delivery && <option value="delivery">Entrega</option>}
                    </select>
                  </label>
                  <label className="field">Pagamento
                    <select value={form.payment_method} onChange={(e) => setForm({ ...form, payment_method: e.target.value })}>
                      <option value="pix">Pix na entrega/retirada</option>
                      <option value="credit_card">Cartão de crédito</option>
                      <option value="debit_card">Cartão de débito</option>
                      <option value="cash">Dinheiro</option>
                    </select>
                  </label>
                </div>
                {form.payment_method === "cash" && (
                  <label className="field">Troco para
                    <input value={form.payment_change_for} onChange={(e) => setForm({ ...form, payment_change_for: e.target.value })} placeholder="Ex.: 100,00" />
                  </label>
                )}

                {form.delivery_type === "delivery" && (
                  <div className="delivery-fields">
                    <div className="form-grid">
                      <label className="field">CEP
                        <input value={form.delivery_zip_code} onChange={(e) => setForm({ ...form, delivery_zip_code: e.target.value })} />
                      </label>
                      <label className="field">Rua *
                        <input value={form.delivery_street} onChange={(e) => setForm({ ...form, delivery_street: e.target.value })} />
                      </label>
                      <label className="field">Número *
                        <input value={form.delivery_number} onChange={(e) => setForm({ ...form, delivery_number: e.target.value })} />
                      </label>
                      <label className="field">Complemento
                        <input value={form.delivery_complement} onChange={(e) => setForm({ ...form, delivery_complement: e.target.value })} />
                      </label>
                      <label className="field">Bairro *
                        <input value={form.delivery_neighborhood} onChange={(e) => { setForm({ ...form, delivery_neighborhood: e.target.value }); setQuote(null); }} />
                      </label>
                      <label className="field">Cidade *
                        <input value={form.delivery_city} onChange={(e) => { setForm({ ...form, delivery_city: e.target.value }); setQuote(null); }} />
                      </label>
                      <label className="field">UF
                        <input maxLength={2} value={form.delivery_state} onChange={(e) => setForm({ ...form, delivery_state: e.target.value.toUpperCase() })} />
                      </label>
                      <label className="field">Referência
                        <input value={form.delivery_reference} onChange={(e) => setForm({ ...form, delivery_reference: e.target.value })} />
                      </label>
                    </div>
                  </div>
                )}
              </section>
            </div>

            <aside>
              <section className="card manual-summary">
                <h2>Resumo</h2>
                {quote ? (
                  <>
                    {quote.items.map((row: any, index: number) => (
                      <div className="summary-line" key={`${row.name}-${index}`}>
                        <span>{row.quantity}× {row.name}</span><strong>{money(row.line_total)}</strong>
                      </div>
                    ))}
                    <div className="summary-line"><span>Subtotal</span><strong>{money(quote.subtotal)}</strong></div>
                    <div className="summary-line"><span>Entrega</span><strong>{money(quote.delivery_fee)}</strong></div>
                    <div className="summary-line total"><span>Total</span><strong>{money(quote.total)}</strong></div>
                  </>
                ) : (
                  <p className="muted">Confira o pedido para calcular os preços e a taxa de entrega antes de criar.</p>
                )}
                <button type="button" className="secondary" disabled={busy} onClick={calculate}>
                  {busy ? "Conferindo…" : "Conferir pedido"}
                </button>
                <button type="button" disabled={busy || !quote} onClick={create}>
                  {busy ? "Criando…" : "Criar pedido"}
                </button>
                <small>O backend recalcula tudo novamente ao criar. Valores do navegador nunca são aceitos como fonte de verdade.</small>
              </section>
            </aside>
          </div>
        )}
      </Feedback>
    </>
  );
}
