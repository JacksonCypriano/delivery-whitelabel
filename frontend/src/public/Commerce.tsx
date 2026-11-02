import { Fragment, useEffect, useRef, useState } from "react";
import { StoreIcon, useStorefront } from "./Storefront";
import { CSRF, OrderSummary, PostButton } from "./PublicApp";
export const money = (value: any) => Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }).replace(/\u00a0/g, " ");
export async function requestJSON(url: string, data: any, body?: any) {
  const response = await fetch(url, {credentials: "same-origin", headers: {Accept: "application/json", ...(body !== undefined ? {"Content-Type": body instanceof URLSearchParams ? "application/x-www-form-urlencoded;charset=UTF-8" : "application/json", "X-CSRFToken": data.csrf} : {})}, ...(body !== undefined ? {method: "POST", body: body instanceof URLSearchParams ? body.toString() : JSON.stringify(body)} : {})});
  const result = await response.json().catch(() => ({error: "Não foi possível concluir. Atualize a página e tente novamente."}));
  if (!response.ok || result.success === false) throw new Error(result.error || result.message || "Não foi possível concluir.");
  return result;
}
type ChoiceSelection = {group_id: number | string; option_id: number | string};
const optionKey = (value: unknown) => String(value);
const numericPrice = (value: any) => {
  const n = Number(String(value ?? 0).replace(',', '.'));
  return Number.isFinite(n) ? n : 0;
};
function useChoiceGroups(productId: number | string) {
  const [groups, setGroups] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setGroups([]); setLoading(true); setError('');
    requestJSON(`/api/product/${productId}/customizations/`, {}).then(result => {
      if (active) { setGroups(Array.isArray(result.groups) ? result.groups : []); setLoading(false); }
    }).catch(err => { if (active) { setError(err.message); setLoading(false); } });
    return () => { active = false; };
  }, [productId, attempt]);
  return { groups, loading, error, retry: () => setAttempt(n => n + 1) };
}
function ChoiceGroups({groups, bucket, allowed, selections, onChange}: any) {
  return <>{groups.filter((g:any) => !allowed || allowed.includes(String(g.apply_to).toLowerCase())).map((group:any) => {
    const selected = selections.filter((s:ChoiceSelection) => optionKey(s.group_id) === optionKey(group.id));
    const max = Number(group.max_options || 0);
    const single = max === 1;
    const min = Number(group.min_options || 0);
    return <fieldset className="store-customization-group" key={group.id}>
      <legend>{group.name} <small>{min > 0 ? `Obrigatório · escolha ${min}${max ? ` a ${max}` : ' ou mais'}` : `Opcional${max ? ` · até ${max}` : ''}`}</small></legend>
      <div className="store-customization-options">{(group.options || []).map((option:any) => {
        const checked = selected.some((s:ChoiceSelection) => optionKey(s.option_id) === optionKey(option.id));
        const isMaxed = !single && max > 0 && selected.length >= max && !checked;
        return <label className={`choice store-customization-option${checked ? ' is-selected' : ''}`} key={option.id}>
          <input type={single ? 'radio' : 'checkbox'} name={`${bucket}-group-${group.id}`} checked={checked} disabled={isMaxed}
            onChange={e => {
              const otherGroups = selections.filter((s:ChoiceSelection) => optionKey(s.group_id) !== optionKey(group.id));
              const next = single ? (e.target.checked ? [{group_id:group.id,option_id:option.id}] : []) : e.target.checked
                ? [...selected, {group_id:group.id,option_id:option.id}]
                : selected.filter((s:ChoiceSelection) => optionKey(s.option_id) !== optionKey(option.id));
              onChange(bucket, [...otherGroups, ...next]);
            }}/>
          {option.image && <img className="store-customization-image" src={option.image} alt="" loading="lazy"/>}
          <span className="store-customization-copy"><strong>{option.name}</strong>{option.description && <small>{option.description}</small>}</span>
          <span className="store-customization-price">{numericPrice(option.price) > 0 ? `+ ${money(option.price)}` : 'Grátis'}</span>
        </label>;
      })}</div>
    </fieldset>;
  })}</>;
}
export function Choices({product, bucket, allowed, selections, onChange}: any) {
  const {groups,loading,error,retry} = useChoiceGroups(product.id);
  return <>{loading && <p role="status">Carregando opções…</p>}{error && <div role="alert">{error} <button type="button" onClick={retry}>Tentar novamente</button></div>}
    <ChoiceGroups groups={groups} bucket={bucket} allowed={allowed} selections={selections} onChange={onChange}/></>;
}
function selectionError(groups:any[], selections:ChoiceSelection[], allowed?:string[]) {
  for (const group of groups.filter(g => !allowed || allowed.includes(String(g.apply_to).toLowerCase()))) {
    const count = selections.filter(s => optionKey(s.group_id) === optionKey(group.id)).length;
    if (count < Number(group.min_options || 0)) return `Selecione as opções obrigatórias de ${group.name}.`;
    if (Number(group.max_options || 0) > 0 && count > Number(group.max_options)) return `Limite de opções excedido em ${group.name}.`;
  }
  return '';
}
const halfEligible = (product:any) => product.half_enabled === true;
export function ProductDialog(props:any) {
  // A different product/mode always receives fresh quantities, notes and choices.
  return <ProductDialogContent key={`${props.product.id}-${Boolean(props.startHalf)}`} {...props}/>;
}
function ProductDialogContent({data, product, products, close, onAdded, startHalf=false}: any) {
  const [halfRequested,setHalf] = useState(startHalf === true);
  const half = halfEligible(product) && halfRequested;
  const [secondId,setSecondId] = useState('');
  const [filter,setFilter] = useState('');
  const [flavorOpen,setFlavorOpen] = useState(false);
  const [qty,setQty] = useState(Number(product.min_qty || 1));
  const [notes,setNotes] = useState(''), [notes1,setNotes1] = useState(''), [notes2,setNotes2] = useState('');
  const [selections,setSelections] = useState<Record<string,ChoiceSelection[]>>({});
  const [error,setError] = useState(''), [busy,setBusy] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const firstGroups = useChoiceGroups(product.id);
  const candidates = products.filter((p:any) => halfEligible(p) && p.available && optionKey(p.category_id) === optionKey(product.category_id) && optionKey(p.id) !== optionKey(product.id));
  const second = candidates.find((p:any) => optionKey(p.id) === secondId);
  const secondGroups = useChoiceGroups(second?.id || product.id);
  const change = (key:string, list:ChoiceSelection[]) => setSelections(old => ({...old,[key]:list}));
  const basePrice = half && second ? Math.max(numericPrice(product.price),numericPrice(second.price)) : numericPrice(product.price);
  const selectedTotal = (groups:any[], bucket:string, allowed?:string[]) => groups.filter(g => !allowed || allowed.includes(String(g.apply_to).toLowerCase())).reduce((acc:number,g:any) => acc + (g.options || []).reduce((sum:number,o:any) => sum + ((selections[bucket] || []).some(s => optionKey(s.group_id) === optionKey(g.id) && optionKey(s.option_id) === optionKey(o.id)) ? numericPrice(o.price) : 0),0),0);
  const extras = selectedTotal(firstGroups.groups,'whole',half ? ['whole','both'] : undefined) + (half ? selectedTotal(firstGroups.groups,'half1',['half']) + selectedTotal(secondGroups.groups,'half2',['half']) : 0);
  const quantityValid = Number.isInteger(qty) && qty >= Number(product.min_qty || 1) && qty <= Number(product.max_qty || 99);
  const preview = (basePrice + extras) * qty;
  useEffect(() => { const element=dialog.current; const previous=document.activeElement as HTMLElement; element?.showModal(); const overflow=document.body.style.overflow; document.body.style.overflow='hidden'; return () => {element?.close();document.body.style.overflow=overflow;previous?.focus();}; }, []);
  async function add() {
    if (busy) return;
    if (half && !second) {setError('Escolha o segundo sabor da pizza.');return;}
    if (!quantityValid) {setError('Informe uma quantidade válida.');return;}
    if (firstGroups.loading || (half && secondGroups.loading)) {setError('Aguarde o carregamento dos adicionais.');return;}
    if (firstGroups.error || (half && secondGroups.error)) {setError('Não foi possível carregar os adicionais. Tente novamente.');return;}
    const validation = selectionError(firstGroups.groups,selections.whole || [],half ? ['whole','both'] : undefined) || (half ? selectionError(firstGroups.groups,selections.half1 || [],['half']) || selectionError(secondGroups.groups,selections.half2 || [],['half']) : '');
    if (validation) {setError(validation);return;}
    setBusy(true);setError('');
    try {
      const result = await requestJSON(half ? '/checkout/checkout/add-half-half/' : '/checkout/add/',data,{product_id:product.id,quantity:qty,notes,is_half:half,...(half ? {product_ids:[product.id,second.id],customizations_whole:selections.whole || [],customizations_half1:selections.half1 || [],customizations_half2:selections.half2 || [],notes_half1:notes1,notes_half2:notes2} : {customizations:selections.whole || []})});
      // Em produção, adicionar apenas fecha o modal e atualiza o carrinho; não redireciona.
      onAdded?.(result);
      close();
    } catch(e:any) {setError(e.message);setBusy(false);}
  }
  return <dialog ref={dialog} onCancel={close} className={`product-dialog legacy-product-dialog ${half ? "legacy-half-dialog" : "legacy-add-dialog"}`} aria-labelledby="product-title">
    <div className="legacy-modal-header">
      <div className="legacy-modal-title">
        {half && <small>Personalização</small>}
        <h2 id="product-title">{half ? 'Pizza meio a meio' : product.name}</h2>
        {!half && <strong>{money(product.price)}</strong>}
      </div>
      <button className="store-dialog-close" type="button" onClick={close} aria-label="Fechar modal"><StoreIcon name="close"/></button>
    </div>
    <div className="legacy-modal-scroll">
      {!half && <>
        {product.description && <p className="legacy-product-description">{product.description}</p>}
        {halfEligible(product) && <button className="legacy-switch-half" type="button" onClick={()=>{setHalf(true);setSecondId('');setSelections({});setError('');}}>Montar pizza meio a meio</button>}
      </>}
      {half && <section className="legacy-half-builder" aria-label="Montar pizza meio a meio">
        <div className="legacy-flavor-field">
          <p>Escolha o segundo sabor</p>
          <div className="legacy-flavor-dropdown">
            <button type="button" className="legacy-dropdown-trigger" aria-haspopup="listbox" aria-expanded={flavorOpen} onClick={()=>setFlavorOpen(value=>!value)}>
              <span>{second ? second.name : 'Selecione o segundo sabor'}</span><span aria-hidden="true">⌄</span>
            </button>
            {flavorOpen && <div className="legacy-flavor-list" role="listbox" aria-label="Sabores disponíveis">
              <input aria-label="Buscar sabor" type="search" value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Buscar sabor..." autoFocus/>
              <div className="legacy-flavor-options">
                {candidates.filter((p:any)=>p.name.toLocaleLowerCase('pt-BR').includes(filter.toLocaleLowerCase('pt-BR'))).map((p:any)=><button key={p.id} type="button" role="option" aria-selected={secondId===optionKey(p.id)} onClick={()=>{setSecondId(optionKey(p.id));change('half2',[]);setNotes2('');setFlavorOpen(false);setFilter('');}}>
                  {p.image && <img src={p.image} alt=""/>}<span>{p.name}</span><strong>{money(p.price)}</strong>
                </button>)}
                {!candidates.some((p:any)=>p.name.toLocaleLowerCase('pt-BR').includes(filter.toLocaleLowerCase('pt-BR'))) && <p>Nenhum sabor encontrado.</p>}
              </div>
            </div>}
          </div>
        </div>
        <div className="legacy-pizza-card">
          <div className="legacy-pizza-intro"><h3>Sua pizza</h3><p>Escolha um sabor para cada metade.</p></div>
          <div className="legacy-pizza-circle">
            <div className="legacy-pizza-side">
              {product.image && <img src={product.image} alt=""/>}
              <small>Metade 1</small><strong>{product.name}</strong>
            </div>
            <div className="legacy-pizza-side">
              {second?.image && <img src={second.image} alt=""/>}
              <small>Metade 2</small><strong>{second?.name || 'Selecione...'}</strong>
            </div>
          </div>
          <div className="legacy-pizza-total"><strong>{second ? money(preview) : 'R$ 0,00'}</strong><small>Valor total da pizza + adicionais</small></div>
        </div>
      </section>}
      {firstGroups.loading && <p role="status">Carregando opções…</p>}
      {firstGroups.error && <div role="alert">{firstGroups.error} <button type="button" onClick={firstGroups.retry}>Tentar novamente</button></div>}
      <ChoiceGroups groups={firstGroups.groups} bucket="whole" allowed={half ? ['whole','both'] : undefined} selections={selections.whole || []} onChange={change}/>
      {half && second && <>
        <h3 className="legacy-half-label">Primeira metade: {product.name}</h3>
        <ChoiceGroups groups={firstGroups.groups} bucket="half1" allowed={['half']} selections={selections.half1 || []} onChange={change}/>
        <h3 className="legacy-half-label">Segunda metade: {second.name}</h3>
        {secondGroups.loading && <p role="status">Carregando opções…</p>}
        {secondGroups.error && <div role="alert">{secondGroups.error} <button type="button" onClick={secondGroups.retry}>Tentar novamente</button></div>}
        <ChoiceGroups groups={secondGroups.groups} bucket="half2" allowed={['half']} selections={selections.half2 || []} onChange={change}/>
        <div className="legacy-half-observations">
          <h3>Observações</h3>
          <label className="public-field">Metade 1: {product.name}<textarea rows={2} placeholder="Ex: sem cebola..." value={notes1} onChange={e=>setNotes1(e.target.value)}/></label>
          <label className="public-field">Metade 2: {second.name}<textarea rows={2} placeholder="Ex: sem cebola..." value={notes2} onChange={e=>setNotes2(e.target.value)}/></label>
        </div>
      </>}
      <label className="public-field legacy-quantity-field">Quantidade<input type="number" min={product.min_qty || 1} max={product.max_qty || 99} value={qty} onChange={e=>setQty(Number(e.target.value))}/></label>
      {!half && <label className="public-field legacy-note-field">Observação <small>(opcional)</small><textarea rows={3} placeholder="Ex: sem cebola, molho à parte..." maxLength={1000} value={notes} onChange={e=>setNotes(e.target.value)}/></label>}
      {!half && <p className="legacy-price-subtotal">Total: <strong>{money(preview)}</strong></p>}
      {error && <p role="alert">{error}</p>}
    </div>
    <div className="legacy-modal-footer">
      <button type="button" className="legacy-cancel" onClick={close}>Cancelar</button>
      <button className="store-dialog-submit" type="button" onClick={add} disabled={busy || !product.available || !quantityValid || (half && !second)} aria-busy={busy}>{busy ? 'Adicionando…' : 'Adicionar ao carrinho'}</button>
    </div>
  </dialog>;
}
export function DeliveryEstimate({data}:any){
 const [city,setCity]=useState(""),[neighborhood,setNeighborhood]=useState(""),[result,setResult]=useState<any>(null),[error,setError]=useState(""),[busy,setBusy]=useState(false);
 async function check(e:any){e.preventDefault();setBusy(true);setError("");setResult(null);try{setResult(await requestJSON(`/api/delivery-fee/?${new URLSearchParams({city,neighborhood})}`,data));}catch(e:any){setError(e.message);}finally{setBusy(false);}}
 return <details className="catalog-details-v2"><summary>Consultar entrega</summary><form onSubmit={check} className="store-delivery-estimate"><label className="public-field">Cidade<input value={city} onChange={e=>{setCity(e.target.value);setResult(null);}} required list="store-cities"/></label><label className="public-field">Bairro<input value={neighborhood} onChange={e=>{setNeighborhood(e.target.value);setResult(null);}} required list="store-neighborhoods"/></label><datalist id="store-cities">{[...new Set<string>((data.props.delivery_zones||[]).map((z:any)=>z.city))].map(c=><option key={c} value={c}/>)}</datalist><datalist id="store-neighborhoods">{(data.props.delivery_zones||[]).map((z:any,i:number)=><option key={i} value={z.neighborhood}>{z.city}</option>)}</datalist><button disabled={busy} aria-busy={busy}>{busy?"Consultando…":"Consultar taxa"}</button>{error&&<p role="alert">{error}</p>}{result&&<p role="status">{result.available ? `Entrega disponível · ${result.fee_display}` : result.message || "Entrega indisponível neste endereço."}</p>}</form></details>;
}
export function CouponPreview({data,fee}:any){
 const [code,setCode]=useState(""),[result,setResult]=useState<any>(null),[error,setError]=useState(""),[busy,setBusy]=useState(false);
 const generation=useRef(0);
 useEffect(()=>{generation.current++;setResult(null);setError("");setBusy(false);},[fee?.fee,data.props.subtotal]);
 async function check(){const id=++generation.current;setBusy(true);setError("");setResult(null);try{const response=await requestJSON("/api/cupons/validar/",data,{code,subtotal:data.props.subtotal,delivery_fee:fee?.fee||0});if(id!==generation.current)return;if(!response.valid)throw new Error(response.message||"Cupom inválido.");setResult(response);}catch(e:any){if(id===generation.current)setError(e.message);}finally{if(id===generation.current)setBusy(false);}}
 return <div className="store-coupon"><label className="public-field">Cupom<input name="coupon_code" maxLength={50} value={code} onChange={e=>{generation.current++;setCode(e.target.value.toUpperCase());setResult(null);setError("");setBusy(false);}}/></label><button type="button" onClick={check} disabled={!code.trim()||busy} aria-busy={busy}>{busy?"Validando…":"Aplicar cupom"}</button>{code&&<button type="button" onClick={()=>{generation.current++;setCode("");setResult(null);setError("");setBusy(false);}}>Remover cupom</button>}{error&&<p role="alert">{error}</p>}{result&&<p role="status">{result.message} Desconto: {money(result.discount)} · Prévia do total: {money(result.final_total)}. O valor definitivo será confirmado na revisão.</p>}</div>;
}
function ProductPrice({product:p}:any){return <div>{p.sale_price != null && <><del>{money(p.original_price)}</del><span className="catalog-offer-v2">OFERTA</span></>}<strong>{money(p.price)}</strong></div>;}
function ProductMeta({product:p}:any){return <div className="catalog-product-tags-v2">{p.is_vegan && <span>Vegano</span>}{p.is_spicy && <span>Picante</span>}{p.prep_time && <span>{`~${p.prep_time} min`}</span>}{p.weight && <span>{`${Number(p.weight)} g`}</span>}{p.calories && <span>{`${p.calories} kcal`}</span>}</div>;}
export function Catalog({data}:any) {
  const storefront = useStorefront();
  const [localSearch, setLocalSearch] = useState("");
  const search = storefront?.search ?? localSearch, setSearch = storefront?.setSearch ?? setLocalSearch;
  const [selected, setSelected] = useState<any>(null);
  const [startHalf, setStartHalf] = useState(false);
  const [cartNotice, setCartNotice] = useState('');
  const [categoriesOpen, setCategoriesOpen] = useState(false);
  const [activeCategory,setActiveCategory]=useState("");
  const brand = data.store?.brand || {};
  const store = data.store || {};
  const categories = data.props.categories || [];
  const products = categories.flatMap((category:any) => category.products);
  const visibleProducts = products.filter((p:any) => `${p.name} ${p.description}`.toLocaleLowerCase().includes(search.toLocaleLowerCase()));

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) setSearch(q);
    const product = products.find((p:any) => p.slug === data.props.open_product_slug);
    if (product) setSelected(product);
  }, []);

  const fontClass = brand.font_family === "Poppins" ? "font-poppins" : brand.font_family === "Roboto" ? "font-roboto" : "font-inter";
  const layoutClasses = ["catalog-v2", fontClass, brand.compact_product_cards ? "catalog-compact" : "", brand.card_shadow ? "catalog-shadow" : "", brand.hover_effect ? "catalog-hover" : "", brand.show_category_icons ? "catalog-category-icons" : ""].filter(Boolean).join(" ");
  const isPizzaCategory = (name:string) => ["pizza", "pizzas"].includes(name.trim().toLocaleLowerCase("pt-BR"));
  function openProduct(product:any, half=false) {setCartNotice('');setStartHalf(half === true && halfEligible(product));setSelected(product);}
  async function onProductAdded(result:any) {
    setCartNotice(result?.message || 'Produto adicionado ao carrinho!');
    const count = result?.cart_count ?? result?.data?.cart_count;
    const total = result?.cart_total ?? result?.data?.cart_total;
    if (total !== undefined && total !== null) storefront?.setTotal(total);
    if (count !== undefined && count !== null) {
      storefront?.setCount(Number(count));
    }
    if (count == null || total == null) {
      try {
        const cart = await requestJSON('/checkout/cart/', data);
        const cartCount = cart?.store?.cart_count ?? cart?.props?.items?.reduce((n:number, item:any) => n + Number(item.quantity || 0), 0);
        if (cartCount !== undefined) storefront?.setCount(Number(cartCount));
        if (cart?.props?.total != null) storefront?.setTotal(cart.props.total);
      } catch { /* O item já foi adicionado; eventual falha no contador não impede a compra. */ }
    }
  }
  const fulfillment = store.accepts_delivery && store.accepts_pickup ? "Entrega e retirada" : store.accepts_pickup ? "Apenas retirada" : "Apenas entrega";

  return <div className={layoutClasses} data-open-product-slug={data.props.open_product_slug || ""} data-header-style={brand.header_style || ""}>
    <div className="catalog-banner-v2" aria-label={`Banner da ${store.name || "loja"}`}>
      {store.banner && <img src={store.banner} alt="" />}
      <div className="catalog-banner-overlay-v2" />
    </div>
    <section className="catalog-identity-v2">
      <div className="catalog-identity-inner-v2">
        <div className="catalog-logo-v2">{store.logo ? <img src={store.logo} alt={`Logo ${store.name}`} /> : <span>{(store.name || "L").slice(0, 1)}</span>}</div>
        <div className="catalog-store-info-v2"><h1>{store.name || "Cardápio"}</h1>
          <div className="catalog-status-line-v2"><span className={store.is_open ? "catalog-open-v2" : "catalog-closed-v2"}>{store.is_open ? "● Aberto agora" : "● Fechado agora"}</span><span aria-hidden="true">•</span><span>{fulfillment}</span></div>
          {store.accepts_pickup && store.pickup_address && <p className="catalog-pickup-v2">Retirada: {store.pickup_address}</p>}
        </div>
        
      </div>
    </section>
    <div className="catalog-toolbar-v2" onKeyDown={e=>{if(e.key==="Escape")setCategoriesOpen(false);}}>
      <div className="catalog-toolbar-inner-v2">
        <button type="button" aria-label="Ver todas as categorias" aria-expanded={categoriesOpen} onClick={() => setCategoriesOpen(value => !value)} className="catalog-categories-toggle-v2"><StoreIcon name="menu"/></button>
        <nav className="catalog-categories-v2" aria-label="Categorias do cardápio">{categories.map((cat:any) => <Fragment key={cat.id}><a href={`#category-${cat.id}`} aria-current={activeCategory===`category-${cat.id}` ? "location" : undefined} onClick={()=>setActiveCategory(`category-${cat.id}`)}>{isPizzaCategory(cat.name) ? "Pizzas inteiras" : cat.name}</a>{cat.products.some((p:any)=>halfEligible(p)) && <a href={`#pizzas-meio-a-meio-${cat.id}`} aria-current={activeCategory===`pizzas-meio-a-meio-${cat.id}` ? "location" : undefined} onClick={()=>setActiveCategory(`pizzas-meio-a-meio-${cat.id}`)}>Pizza meio a meio</a>}</Fragment>)}</nav>

      </div>
      {categoriesOpen && <nav className="catalog-categories-drawer-v2" aria-label="Todas as categorias">{categories.map((cat:any) => <Fragment key={cat.id}><a onClick={() => setCategoriesOpen(false)} href={`#category-${cat.id}`}>{isPizzaCategory(cat.name) ? "Pizzas inteiras" : cat.name} <span>›</span></a>{cat.products.some((p:any)=>halfEligible(p)) && <a onClick={() => setCategoriesOpen(false)} href={`#pizzas-meio-a-meio-${cat.id}`}>Pizza meio a meio <span>›</span></a>}</Fragment>)}</nav>}
    </div>
    <div className="catalog-content-v2">
      {!storefront && <div className="catalog-search-row-v2">
        <div><small>Cardápio</small><h2>Escolha seus favoritos</h2></div>
        {brand.show_search_bar !== false && <label className="catalog-search-v2"><span className="catalog-sr-only-v2">Buscar no cardápio</span><span aria-hidden="true">⌕</span><input type="search" placeholder="Buscar no cardápio..." value={search} onChange={e => setSearch(e.target.value)} /></label>}
      </div>}
      <details className="catalog-details-v2" id="store-details"><summary>Horários, entrega e retirada</summary><div className="catalog-details-content-v2"><div>{store.hours?.map((h:any,n:number) => <p key={n}><strong>{h.day}</strong><span>{h.closed ? "Fechado" : `${h.open} – ${h.close}`}</span></p>)}</div>{store.accepts_pickup && store.pickup_address && <p><strong>Endereço de retirada</strong><span>{store.pickup_address}</span></p>}{data.props.delivery_zones?.map((z:any,n:number) => <p key={n}><strong>{z.city} — {z.neighborhood}</strong><span>{money(z.fee)}</span></p>)}</div></details>
      {store.accepts_delivery && <DeliveryEstimate data={data}/>}
      {data.props.deep_link_unavailable && <p role="alert" className="catalog-alert-v2">Este produto não está disponível no momento.</p>}
      {categories.map((category:any) => {
        const filtered = category.products.filter((p:any) => visibleProducts.some((current:any) => current.id === p.id));
        if (!filtered.length) return null;
        return <Fragment key={category.id}><section id={`category-${category.id}`} className="catalog-category-section-v2">
          <div className="catalog-category-title-v2"><small>Cardápio</small><h2>{isPizzaCategory(category.name) ? "Pizzas inteiras" : category.name}</h2></div>
          <div className="catalog-product-grid-v2">{filtered.map((p:any) => <article key={p.id} className={`catalog-product-card-v2 ${p.is_featured ? "product-card-featured is-featured" : ""}`} data-product-slug={p.slug} data-product-price={p.price}>
            <div className="catalog-product-info-v2">
              <div className={p.is_featured ? "catalog-featured-content-v2" : undefined}>{p.is_featured && <span className="catalog-featured-v2">★ Destaque</span>}
                <h3><a href={`/produto/${p.slug}/`} onClick={e => { e.preventDefault(); openProduct(p); }}>{p.name}</a></h3>
                {brand.show_product_description !== false && p.description && <p className="catalog-product-description-v2">{p.description}</p>}
                <ProductMeta product={p}/>
              </div>
              <div className="catalog-product-bottom-v2"><ProductPrice product={p}/><button type="button" disabled={!p.available} aria-label={p.available ? `Escolher ${p.name}` : `${p.name} esgotado`} onClick={() => openProduct(p)}>{p.available ? <StoreIcon name="plus"/> : "×"}</button></div>
            </div>
            {brand.show_product_image !== false && (p.image ? <img className="catalog-product-photo-v2" src={p.image} alt={p.name} loading="lazy" /> : <div className="catalog-product-placeholder-v2" aria-hidden="true">▧</div>)}
          </article>)}</div>
        </section>
        {filtered.some((p:any) => halfEligible(p)) && <section id={`pizzas-meio-a-meio-${category.id}`} className="catalog-category-section-v2 catalog-half-section-v2">
          <div className="catalog-category-title-v2"><small>Monte do seu jeito</small><h2>Pizza meio a meio</h2><p>Escolha dois sabores e monte uma pizza do jeito que você quiser.</p></div>
          <div className="catalog-product-grid-v2">{filtered.filter((p:any) => halfEligible(p)).map((p:any) => <article key={`half-${p.id}`} className="catalog-product-card-v2 catalog-half-card-v2" data-product-slug={p.slug} data-product-price={p.price}>
            <div className="catalog-product-info-v2"><div><span className="catalog-half-badge-v2">½ + ½</span><h3>{p.name}</h3>{brand.show_product_description !== false && p.description && <p className="catalog-product-description-v2">{p.description}</p>}
              <ProductMeta product={p}/></div>
              <div className="catalog-product-bottom-v2"><ProductPrice product={p}/><button className="catalog-half-button-v2" type="button" disabled={!p.available} onClick={() => openProduct(p,true)} aria-label={`Montar pizza meio a meio com ${p.name}`}>{p.available ? "Montar" : "Esgotado"}</button></div>
            </div>
            {brand.show_product_image !== false && (p.image ? <img className="catalog-product-photo-v2" src={p.image} alt={p.name} loading="lazy"/> : <div className="catalog-product-placeholder-v2" aria-hidden="true">½</div>)}
          </article>)}</div>
        </section>}
        </Fragment>;
      })}
      {visibleProducts.length === 0 && <div className="catalog-empty-v2"><h3>Nenhum produto encontrado</h3><p>Experimente buscar por outro nome.</p>{search && <button type="button" onClick={() => setSearch("")}>Limpar busca</button>}</div>}
    </div>
    {cartNotice && <div className="store-cart-success-notice" role="status">{cartNotice}<button type="button" onClick={() => setCartNotice('')} aria-label="Fechar aviso">×</button></div>}
    <a className="catalog-cart-sticky-v2" href="/checkout/cart/"><StoreIcon name="bag" size={24}/><span>Ver carrinho ({storefront?.count ?? store.cart_count ?? 0}){storefront?.total != null && <small className="store-cart-total">{money(storefront.total)}</small>}</span><StoreIcon name="arrow"/></a>
    {selected && <ProductDialog key={`${selected.id}-${startHalf}`} product={selected} products={products} data={data} startHalf={startHalf} close={() => setSelected(null)} onAdded={onProductAdded}/>}
  </div>;
}
function CartItem({item,data,onUpdate}:any){
  const [qty,setQty]=useState(item.quantity),[notes,setNotes]=useState(item.notes),[error,setError]=useState(""),[busy,setBusy]=useState(false);
  async function mutate(url:string,body:any){setBusy(true);setError("");try{await requestJSON(url,data,body);await onUpdate();}catch(e:any){setError(e.message);}finally{setBusy(false);}}
  const combo=item.combination_details || {};
  return <article className="public-card store-cart-item" aria-busy={busy}>{item.image && <img className="store-cart-image" src={item.image} alt=""/>}<h2>{item.name}</h2><p>{money(item.price)} cada · <strong>{money(item.total)}</strong></p>{Object.entries({customizations:"Adicionais",customizations_whole:"Inteira",customizations_half1:"Primeira metade",customizations_half2:"Segunda metade"}).map(([bucket,label])=><div key={bucket}>{combo[bucket]?.map((option:any,index:number)=><p key={index}>{label}: {option.option_name} (+ {money(option.price)}) {option.can_remove_from_cart && <button disabled={busy} onClick={()=>mutate(`/checkout/carrinho/item/${item.id}/opcional/remover/`,{bucket,index})}>Remover opcional</button>}</p>)}</div>)}{combo.notes_half1&&<p>Primeira metade: {combo.notes_half1}</p>}{combo.notes_half2&&<p>Segunda metade: {combo.notes_half2}</p>}<label className="public-field">Quantidade<input type="number" value={qty} min={item.min_qty} max={item.max_qty} onChange={e=>setQty(Number(e.target.value))}/></label><button disabled={busy} onClick={()=>mutate(`/checkout/update_quantity/${item.id}/`,{quantity:qty})}>Atualizar quantidade</button><label className="public-field">Observações<textarea value={notes} maxLength={1000} onChange={e=>setNotes(e.target.value)}/></label><button disabled={busy} onClick={()=>mutate(`/checkout/update_notes/${item.id}/`,new URLSearchParams({notes}))}>Salvar observações</button><button disabled={busy} onClick={()=>mutate(`/checkout/remove/${item.id}/`,{})}>Remover item</button>{error&&<p role="alert">{error}</p>}</article>;
}
export function Cart({data}:any){
 const storefront=useStorefront(); const [current,setCurrent]=useState(data);
 async function refresh(){const next=await requestJSON("/checkout/cart/",data);setCurrent(next);storefront?.setCount(Number(next.store?.cart_count ?? next.props.items.reduce((n:number,i:any)=>n+i.quantity,0)));}
 const p=current.props;
 return <><a href="/">← Continuar comprando</a><div className="store-cart-layout"><div>{p.items.map((item:any)=><CartItem key={`${item.id}-${item.price}-${item.quantity}`} item={item} data={data} onUpdate={refresh}/>)}</div>
 {!p.items.length?<section className="public-card store-empty"><StoreIcon name="bag" size={48}/><h2>Seu carrinho está vazio.</h2><p>Escolha algo no cardápio para começar seu pedido.</p><a className="store-button" href="/">Explorar cardápio</a></section>:<aside className="public-card store-cart-summary"><h2>Resumo do pedido</h2><p>Subtotal: <strong>{money(p.subtotal)}</strong></p><p>Entrega: <strong>{p.delivery_fee_display}</strong></p><p className="store-total">Total: <strong>{money(p.total)}</strong></p><p>{p.checkout_mode_hint}</p>{p.can_checkout === false ? <p role="alert">Confira a disponibilidade de entrega ou retirada antes de continuar.</p> : <a className="store-button" href="/checkout/checkout/">Escolher endereço e finalizar <StoreIcon name="arrow"/></a>}</aside>}</div>
 {data.user?.authenticated&&<form className="public-card" method="post" action="/preferencias/mensagens/"><CSRF data={data}/><label className="choice"><input type="checkbox" name="allowed"/>Autorizo lembretes de carrinho, pesquisa de satisfação e novidades desta loja pelo WhatsApp.</label><button>Salvar preferência de mensagens</button></form>}</>;
}
export function AddressFields({initial={},prefix="",onChange}:any){
 const [address,setAddress]=useState<any>(initial),[error,setError]=useState("");
 function update(key:string,value:string){const next={...address,[key]:value};setAddress(next);onChange?.(next);}
 async function cep(){const value=String(address.zip_code||"").replace(/\D/g,"");if(value.length!==8)return;try{const result=await requestJSON(`/api/cep/${value}/`,{});const next={...address,...result};setAddress(next);onChange?.(next);setError("");}catch(e:any){setError(e.message);}}
 return <>{[["zip_code","CEP"],["street","Rua"],["number","Número"],["complement","Complemento"],["neighborhood","Bairro"],["city","Cidade"],["state","UF"],["reference","Referência"]].map(([key,label])=><label className="public-field" key={key}>{label}<input name={prefix+(key==="zip_code"?"cep":key==="street"?"address":key)} value={address[key]||""} onChange={e=>update(key,e.target.value)} onBlur={key==="zip_code"?cep:undefined} required={["street","number","neighborhood","city"].includes(key)} maxLength={key==="state"?2:200}/></label>)}{error&&<p role="alert">{error}</p>}</>;
}
export function Checkout({data}:any){
 const p=data.props;const [mode,setMode]=useState(data.store.accepts_delivery?"delivery":"pickup"),[flow,setFlow]=useState("in_person"),[payment,setPayment]=useState("pix"),[saved,setSaved]=useState(p.default_address?String(p.default_address.id):""),[address,setAddress]=useState(p.global_delivery_location||{}),[fee,setFee]=useState<any>(null);
 useEffect(()=>{let active=true;if(mode==="pickup"){setFee({fee:0,fee_display:"Retirada sem taxa de entrega",available:true});return;}setFee(null);const a=p.customer_addresses.find((a:any)=>String(a.id)===saved)||address;requestJSON(`/api/delivery-fee/?${new URLSearchParams({delivery_type:mode,city:a.city||"",neighborhood:a.neighborhood||""})}`,data).then(r=>{if(active)setFee(r);}).catch(()=>{if(active)setFee(null);});return()=>{active=false;};},[mode,saved,address.city,address.neighborhood]);
 return <form className="store-checkout" method="post"><CSRF data={data}/><input type="hidden" name="checkout_token" value={p.checkout_token}/><section className="public-card store-order-preview"><h2>Seu pedido</h2>{p.cart_items.map((i:any,n:number)=><p key={n}>{i.quantity}× {i.name} · {money(i.line_total)}{i.notes&&<small> · {i.notes}</small>}</p>)}<p>Subtotal: {money(p.subtotal)}</p><p>{fee?.fee_display||"A taxa será confirmada conforme o endereço."}</p></section><section className="public-card"><h2>Contato</h2><label className="public-field">Nome completo<input name="full_name" defaultValue={p.initial_full_name} required maxLength={150}/></label><label className="public-field">WhatsApp<input type="tel" name="phone" defaultValue={p.initial_phone} required maxLength={20}/></label><h2>Recebimento</h2>{p.scheduling_enabled&&<label className="public-field">Agendar entrega ou retirada (opcional)<input type="datetime-local" name="scheduled_for"/><small>Horário de São Paulo. A loja confere antecedência e disponibilidade.</small></label>}<label className="public-field">Modalidade<select name="delivery_type" value={mode} onChange={e=>setMode(e.target.value)}>{data.store.accepts_delivery&&<option value="delivery">Entrega</option>}{data.store.accepts_pickup&&<option value="pickup">Retirada</option>}</select></label>{mode==="pickup"?<p>{p.store_address}</p>:<>{p.customer_addresses.length>0&&<label className="public-field">Endereço salvo<select name="customer_address_id" value={saved} onChange={e=>setSaved(e.target.value)}><option value="">Informar outro endereço</option>{p.customer_addresses.map((a:any)=><option key={a.id} value={a.id}>{a.label}: {a.street}, {a.number}</option>)}</select></label>}{!saved&&<AddressFields initial={address} onChange={setAddress}/>}</>}</section><section className="public-card"><h2>Pagamento</h2><label className="public-field">Quando pagar<select name="payment_flow" value={flow} onChange={e=>{setFlow(e.target.value);setPayment("pix");}}><option value="in_person">Na entrega / retirada</option>{p.online_payment_available&&<option value="online">Online pelo Asaas</option>}</select></label><label className="public-field">Forma<select name="payment_method" value={payment} onChange={e=>setPayment(e.target.value)}><option value="pix">Pix</option><option value="credit_card">Cartão de crédito</option>{flow==="in_person"&&<><option value="debit_card">Cartão de débito</option><option value="cash">Dinheiro</option></>}</select></label>{payment==="cash"&&<label className="public-field">Troco para<input type="number" name="change_for" min={0} step="0.01"/></label>}<CouponPreview data={data} fee={fee}/><p>O desconto, a taxa e o total definitivo aparecem na revisão.</p><button>Revisar pedido</button></section></form>;
}
export function Review({data}:any){const p=data.props,o=p.order,payment=p.payment;const base=`/pedido/${o.public_token}`;return <><OrderSummary order={{...o,repeat_url:null}} data={data}/>{payment&&<p>Situação do pagamento: {payment.label}</p>}{o.payment_flow==="online"&&payment?.status!=="PAID"?<>{payment?.checkout_url?<a href={payment.checkout_url}>Continuar pagamento no Asaas</a>:<PostButton data={data} action={`${base}/pagar/`}>Pagar online com Asaas</PostButton>}<PostButton data={data} action={`${base}/pagamento/atualizar/`}>Já paguei — verificar confirmação</PostButton></>:<>{payment?.confirmation_code&&<p>Código de confirmação: <strong>{payment.confirmation_code}</strong></p>}<PostButton data={data} action={`${base}/whatsapp/`}>Confirmar e enviar pedido pelo WhatsApp</PostButton></>}<PostButton data={data} action={`${base}/editar/`}>Alterar pedido</PostButton><p>A revisão e a reserva de estoque valem por 30 minutos. O backend confere novamente valores e disponibilidade ao confirmar.</p></>;}
