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
export function Choices({product, bucket, allowed, selections, onChange}: any) {
  const [groups, setGroups] = useState<any[]>([]), [error, setError] = useState(""), [loading,setLoading]=useState(true), [attempt,setAttempt]=useState(0);
  useEffect(() => { let active = true; setGroups([]); setError(""); setLoading(true); requestJSON(`/api/product/${product.id}/customizations/`, {}).then(r => { if(active) {setGroups(r.groups);setLoading(false);} }).catch(e => {if(active) {setError(e.message);setLoading(false);}}); return () => {active=false;}; }, [product.id,attempt]);
  return <>{loading && <p role="status">Carregando opções…</p>}{error && <div role="alert">{error} <button type="button" onClick={()=>setAttempt(n=>n+1)}>Tentar novamente</button></div>}{groups.filter(g => !allowed || allowed.includes(g.apply_to)).map(group => <fieldset key={group.id}><legend>{group.name} · escolha {group.min_options} a {group.max_options || "várias"}</legend>{group.options.map((option:any) => <label className="choice" key={option.id}><input type="checkbox" checked={selections.some((s:any) => s.group_id === group.id && s.option_id === option.id)} onChange={e => onChange(bucket, e.target.checked ? [...selections, {group_id:group.id,option_id:option.id}] : selections.filter((s:any) => s.option_id !== option.id))}/>{option.name} {Number(option.price) > 0 && `+ ${money(option.price)}`}{option.description && <small>{option.description}</small>}</label>)}</fieldset>)}</>;
}
export function ProductDialog({data, product, products, close, startHalf=false}: any) {
  const [half, setHalf] = useState(Boolean(startHalf)), [secondId,setSecondId] = useState(String(product.id));
  const [qty,setQty]=useState(product.min_qty), [notes,setNotes]=useState(""), [notes1,setNotes1]=useState(""), [notes2,setNotes2]=useState("");
  const [selections,setSelections]=useState<any>({}), [error,setError]=useState(""), [busy,setBusy]=useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {const element=dialog.current; const previous=document.activeElement as HTMLElement; element?.showModal(); const overflow=document.body.style.overflow;document.body.style.overflow="hidden";try{if(localStorage.getItem("vdd_analytics_permission")==="yes")void requestJSON("/eventos/loja/",data,{stage:"product",consent:true}).catch(()=>{});}catch{}return()=>{element?.close();document.body.style.overflow=overflow;previous?.focus();};}, []);
  const second = products.find((p:any) => String(p.id) === secondId) || product;
  const change = (key:string, list:any[]) => setSelections((old:any) => ({...old,[key]:list}));
  async function add() {setBusy(true);setError("");try {
    await requestJSON(half ? "/checkout/checkout/add-half-half/" : "/checkout/add/", data, {product_id:product.id,quantity:qty,notes,is_half:half,...(half ? {product_ids:[product.id,second.id],customizations_whole:selections.whole||[],customizations_half1:selections.half1||[],customizations_half2:selections.half2||[],notes_half1:notes1,notes_half2:notes2} : {customizations:selections.whole||[]})});
    window.location.assign("/checkout/cart/");
  } catch(e:any){setError(e.message);setBusy(false);}}
  return <dialog ref={dialog} onCancel={close} className="product-dialog" aria-labelledby="product-title"><button className="store-dialog-close" type="button" onClick={close} aria-label="Fechar produto"><StoreIcon name="close"/></button><h2 id="product-title">{product.name}</h2><div className="product-gallery">{(product.images.length ? product.images : [product.image]).filter(Boolean).map((src:string) => <img key={src} src={src} alt={product.name}/>)}</div><p>{product.description}</p><strong>{money(product.price)}</strong><p>{product.is_vegan && "Vegano · "}{product.is_spicy && "Picante · "}{product.allergens && `Alérgenos: ${product.allergens}`}</p>{product.prep_time && <p>Preparo: {product.prep_time} min</p>}{product.half_enabled && <label className="choice"><input type="checkbox" checked={half} onChange={e=>{setHalf(e.target.checked);setSelections({});}}/>Montar meio a meio</label>}{half && <label className="public-field">Segundo sabor<select value={secondId} onChange={e=>{setSecondId(e.target.value);change("half2",[]);}}>{products.filter((p:any)=>p.half_enabled&&p.category_id===product.category_id&&p.available).map((p:any)=><option value={p.id} key={p.id}>{p.name}</option>)}</select></label>}
    <Choices product={product} bucket="whole" allowed={half ? ["whole","both"] : undefined} selections={selections.whole||[]} onChange={change}/>
    {half && <><h3>Primeira metade: {product.name}</h3><Choices product={product} bucket="half1" allowed={["half"]} selections={selections.half1||[]} onChange={change}/><label className="public-field">Observação da primeira metade<textarea value={notes1} onChange={e=>setNotes1(e.target.value)}/></label><h3>Segunda metade: {second.name}</h3><Choices product={second} bucket="half2" allowed={["half"]} selections={selections.half2||[]} onChange={change}/><label className="public-field">Observação da segunda metade<textarea value={notes2} onChange={e=>setNotes2(e.target.value)}/></label></>}
    <label className="public-field">Quantidade<input type="number" min={product.min_qty} max={product.max_qty} value={qty} aria-invalid={!Number.isInteger(qty)||qty<product.min_qty||qty>product.max_qty} onChange={e=>setQty(Number(e.target.value))}/></label><label className="public-field">Observações<textarea maxLength={1000} value={notes} onChange={e=>setNotes(e.target.value)}/></label><p>Os valores finais e as opções serão conferidos pela loja ao adicionar.</p>{error && <p role="alert">{error}</p>}<button className="store-dialog-submit" onClick={add} disabled={busy||!product.available||!Number.isInteger(qty)||qty<product.min_qty||qty>product.max_qty} aria-busy={busy}>{busy?"Adicionando…":"Adicionar ao carrinho"}</button></dialog>;
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
  function openProduct(product:any, half=false) {setStartHalf(half);setSelected(product);}
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
        <nav className="catalog-categories-v2" aria-label="Categorias do cardápio">{categories.map((cat:any) => <Fragment key={cat.id}><a href={`#category-${cat.id}`} aria-current={activeCategory===`category-${cat.id}` ? "location" : undefined} onClick={()=>setActiveCategory(`category-${cat.id}`)}>{isPizzaCategory(cat.name) ? "Pizzas inteiras" : cat.name}</a>{isPizzaCategory(cat.name) && cat.products.some((p:any)=>p.half_enabled) && <a href={`#pizzas-meio-a-meio-${cat.id}`} aria-current={activeCategory===`pizzas-meio-a-meio-${cat.id}` ? "location" : undefined} onClick={()=>setActiveCategory(`pizzas-meio-a-meio-${cat.id}`)}>Pizza meio a meio</a>}</Fragment>)}</nav>

      </div>
      {categoriesOpen && <nav className="catalog-categories-drawer-v2" aria-label="Todas as categorias">{categories.map((cat:any) => <Fragment key={cat.id}><a onClick={() => setCategoriesOpen(false)} href={`#category-${cat.id}`}>{isPizzaCategory(cat.name) ? "Pizzas inteiras" : cat.name} <span>›</span></a>{isPizzaCategory(cat.name) && cat.products.some((p:any)=>p.half_enabled) && <a onClick={() => setCategoriesOpen(false)} href={`#pizzas-meio-a-meio-${cat.id}`}>Pizza meio a meio <span>›</span></a>}</Fragment>)}</nav>}
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
        {isPizzaCategory(category.name) && filtered.some((p:any) => p.half_enabled) && <section id={`pizzas-meio-a-meio-${category.id}`} className="catalog-category-section-v2 catalog-half-section-v2">
          <div className="catalog-category-title-v2"><small>Monte do seu jeito</small><h2>Pizza meio a meio</h2><p>Escolha dois sabores e monte uma pizza do jeito que você quiser.</p></div>
          <div className="catalog-product-grid-v2">{filtered.filter((p:any) => p.half_enabled).map((p:any) => <article key={`half-${p.id}`} className="catalog-product-card-v2 catalog-half-card-v2" data-product-slug={p.slug} data-product-price={p.price}>
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
    <a className="catalog-cart-sticky-v2" href="/checkout/cart/"><StoreIcon name="bag" size={24}/><span>Ver carrinho ({storefront?.count ?? store.cart_count ?? 0})</span><StoreIcon name="arrow"/></a>
    {selected && <ProductDialog key={`${selected.id}-${startHalf}`} product={selected} products={products} data={data} startHalf={startHalf} close={() => setSelected(null)}/>}
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
