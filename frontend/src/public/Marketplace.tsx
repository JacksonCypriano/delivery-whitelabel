import { useEffect, useRef, useState } from "react";
import { CSRF } from "./PublicApp";
import { AddressFields } from "./Commerce";

/** Apresentação pública reproduzida do template de produção marketplace/home.html.
 * A origem dos dados e as ações continuam controladas pelo backend Django.
 */
export function Marketplace({ data }: any) {
  const p = data.props;
  const [geoError, setGeoError] = useState("");
  const [editAddress, setEditAddress] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [stuck, setStuck] = useState(false);
  const headerRef = useRef<HTMLElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const location = p.global_delivery_location;
  const title = p.favorites_only ? "Suas lojas favoritas" : p.location_active ? "Perto de você" : p.selected_city ? `Lojas em ${p.selected_city}` : "Descubra seu próximo favorito";

  useEffect(() => {
    const header = headerRef.current;
    const sentinel = sentinelRef.current;
    if (!header || !sentinel) return;
    let observer: IntersectionObserver | undefined;
    const setup = () => {
      const height = Math.ceil(header.getBoundingClientRect().height);
      document.documentElement.style.setProperty("--header-height", `${height}px`);
      observer?.disconnect();
      if (!("IntersectionObserver" in window)) return;
      observer = new IntersectionObserver(([entry]) => {
        setStuck(!entry.isIntersecting && entry.boundingClientRect.top < height);
      }, { rootMargin: `-${height}px 0px 0px 0px`, threshold: 0 });
      observer.observe(sentinel);
    };
    setup();
    window.addEventListener("resize", setup);
    return () => {observer?.disconnect();window.removeEventListener("resize", setup);document.documentElement.style.removeProperty("--header-height");};
  }, []);

  function urlWith(changes: Record<string, string | null>, anchor = "#lojas") {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries({
      q: p.search, cidade: p.selected_city, uf: p.selected_state,
      categoria: p.selected_category, abertas: p.open_only ? "1" : "",
      favoritas: p.favorites_only ? "1" : "",
      lat: p.location_active ? p.user_latitude : "",
      lng: p.location_active ? p.user_longitude : "",
      accuracy: p.location_active ? p.user_accuracy : "",
    })) if (value !== null && value !== undefined && value !== "") query.set(key, String(value));
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "") query.delete(key); else query.set(key, value);
    }
    return (query.size ? `?${query}` : "/") + anchor;
  }

  function locate() {
    if (!navigator.geolocation) { setGeoError("Localização indisponível neste navegador."); return; }
    navigator.geolocation.getCurrentPosition(({ coords }) => {
      window.location.assign(urlWith({ lat: String(coords.latitude), lng: String(coords.longitude), accuracy: String(coords.accuracy) }));
    }, () => setGeoError("Não foi possível obter sua localização. Informe seu endereço."));
  }

  return <div className="mp-production">
    <a className="skip" href="#lojas">Ir para as lojas</a>
    <header className="site-header" ref={headerRef}><div className="wrap header-inner">
      <a className="brand" href="/" aria-label="VemDeDelivery, início"><img className="brand-logo" src="/static/images/brand/logo-vemdedelivery.svg" alt="VemDeDelivery" width="365" height="72" /></a>
      <nav className="navigation" aria-label="Navegação principal">
        <a className="nav-explore desktop-only" href="#lojas">Explorar lojas</a>
        {data.user.authenticated ? <a className="btn btn-dark" href="/conta/">Minha conta ↗</a> : <><a className="btn" href="/conta/entrar/">Entrar</a><a className="btn btn-dark desktop-only" href="/conta/criar-conta/">Criar conta ↗</a></>}
      </nav>
    </div></header>
    {(data.messages || []).length > 0 && <div className="wrap" aria-live="polite">{data.messages.map((message:any, i:number) => <div key={i} className={`notice ${message.level}`}>{message.text}</div>)}</div>}
    <section className="hero wrap" aria-labelledby="hero-title"><div className="hero-panel mp-hero-panel"><div className="hero-copy">
      <div className="eyebrow">Seu bairro tem o que você procura</div>
      <h1 id="hero-title">Deu vontade? <br/><em>Vem de delivery.</em></h1>
      <p>Descubra as lojas da sua região e encontre o lugar certo para o seu próximo pedido.</p>
      <div className="hero-tags"><span>Lojas da sua região</span><span>Entrega ou retirada</span></div>
    </div></div>
      <div id="endereco-entrega" className="delivery-bar"><span className="pin" aria-hidden="true">⌖</span><div className="delivery-copy"><span className="micro">Onde vai ser o pedido?</span>
        <p>{location ? `${location.label ? location.label + " · " : ""}${location.neighborhood || location.street || ""}, ${location.city || ""}${location.state ? "/" + location.state : ""}` : "Encontre sua região. Você confirma o endereço e a taxa no checkout."}</p>
      </div><a className="btn" href={data.user.authenticated ? "/conta/enderecos/" : "/conta/entrar/"}>{data.user.authenticated ? (location ? "Alterar endereço ↗" : "Meus endereços ↗") : "Entrar para salvar endereço ↗"}</a></div>
    </section>
    <div id="search-sentinel" aria-hidden="true" ref={sentinelRef}/>
    <section id="sticky-search" className={`wrap search-section ${stuck ? "is-stuck" : ""} ${expanded ? "filters-expanded" : ""}`} aria-label="Buscar e filtrar lojas">
      <button type="button" className="compact-filter-toggle" aria-expanded={expanded} aria-controls="marketplace-search-form category-navigation" onClick={() => setExpanded(!expanded)}>{expanded ? "Ocultar filtros" : "Mostrar filtros"}</button>
      <form method="get" id="marketplace-search-form" className="search-box">
        {p.location_active && <><input type="hidden" name="lat" value={p.user_latitude} /><input type="hidden" name="lng" value={p.user_longitude} />{p.user_accuracy != null && <input type="hidden" name="accuracy" value={p.user_accuracy}/>}</>}
        {p.favorites_only && <input type="hidden" name="favoritas" value="1" />}
        <div className="search-grid">
          <label className="field"><span className="sr-only">Buscar produto ou loja</span><span aria-hidden="true">⌕</span><input type="search" name="q" defaultValue={p.search} placeholder="O que você quer pedir hoje?"/></label>
          <select name="cidade" aria-label="Cidade" defaultValue={p.location_active ? "" : p.selected_city || ""} disabled={p.location_active}>
            <option value="">{p.location_active ? "Usando localização atual" : "Todas as cidades"}</option>
            {!p.location_active && (p.cities || []).map((city:string) => <option key={city} value={city}>{city}</option>)}
          </select>
          <select name="categoria" aria-label="Categoria" defaultValue={p.selected_category || ""}><option value="">Todas as categorias</option>{(p.categories || []).map((c:any) => <option key={c.slug} value={c.slug}>{c.name}</option>)}</select>
          <button className="btn btn-orange" type="submit">Buscar lojas ↗</button>
        </div>
        <div className="filter-row">
          <button type="button" onClick={locate}>{p.location_active ? "Atualizar localização" : "⌖ Usar minha localização"}</button>
          {p.location_active && <a href={urlWith({lat:null,lng:null,accuracy:null})}>Remover localização</a>}
          <label><input type="checkbox" name="abertas" value="1" defaultChecked={p.open_only}/> Abertas agora</label>
          <button type="button" onClick={() => setEditAddress(!editAddress)}>{editAddress ? "Fechar endereço" : "Informar endereço"}</button>
          {(p.search || p.selected_city || p.selected_category || p.open_only || p.location_active || p.favorites_only) && <a className="clear" href="/">Limpar filtros ×</a>}
        </div>
        {geoError && <p className="location-message" role="status" aria-live="polite">{geoError}</p>}
        {p.location_active && p.geocoded_location && <p className="gps-note">Região aproximada pelo GPS: {[p.geocoded_location.neighborhood, p.geocoded_location.city, p.geocoded_location.state].filter(Boolean).join(", ")}. Confirme o endereço antes do pedido.</p>}
      </form>
      {editAddress && <div className="mp-production-address">
        <form method="post" action="/localizacao-entrega/"><CSRF data={data}/><input type="hidden" name="mode" value="manual"/><AddressFields initial={location || {}}/>{data.user.authenticated && <label><input type="checkbox" name="save_address" value="1"/> Salvar endereço</label>}<button className="btn btn-dark" type="submit">Usar endereço</button></form>
        {(p.customer_addresses || []).length > 0 && <form method="post" action="/localizacao-entrega/"><CSRF data={data}/><input type="hidden" name="mode" value="saved"/><select name="customer_address_id">{p.customer_addresses.map((a:any)=><option key={a.id} value={a.id}>{a.label} — {a.street}, {a.number}</option>)}</select><button className="btn btn-dark" type="submit">Usar endereço salvo</button></form>}
      </div>}
      {(p.categories || []).length > 0 && <nav id="category-navigation" className="category-row" aria-label="Categorias de lojas">
        <a className={`category-chip ${!p.selected_category ? "active" : ""}`} href={urlWith({categoria:null})}>Todas as lojas</a>
        {p.categories.map((cat:any) => <a key={cat.slug} className={`category-chip ${p.selected_category === cat.slug ? "active" : ""}`} href={urlWith({categoria:cat.slug})}>{cat.icon && <span className="category-icon" aria-hidden="true">{cat.icon}</span>}{cat.name}</a>)}
      </nav>}
    </section>
    <main id="lojas" className="wrap results">
      <div className="results-heading"><div><h2>{title}</h2><p>{p.result_count} {p.result_count === 1 ? "loja encontrada" : "lojas encontradas"}{p.search ? ` para “${p.search}”` : ""}{location ? " · entrega no endereço selecionado primeiro" : p.location_active ? " · por distância aproximada" : ""}</p></div>
        {data.user.authenticated && <nav className="account-links" aria-label="Seus atalhos"><a className="btn" href="/meus-pedidos/">Meus pedidos</a><a className={`btn ${p.favorites_only ? "active" : ""}`} href={urlWith({favoritas:p.favorites_only?null:"1"})}>{p.favorites_only ? "♥" : "♡"} Favoritas{p.favorite_count ? ` · ${p.favorite_count}` : ""}</a></nav>}
      </div>
      {(p.stores || []).length > 0 ? <div className="store-grid">{p.stores.map((store:any) => <article className="store-card mp-store-card" key={store.id}>
        <a className="store-link" href={store.url} aria-label={`Ver produtos de ${store.name}`}/>
        {data.user.authenticated && <form method="post" action={`/favoritos/loja/${store.id}/`} className="favorite-store-form"><CSRF data={data}/><input type="hidden" name="next" value="/"/><button type="submit" className="favorite-store-button" aria-pressed={Boolean(store.is_favorite)} title={store.is_favorite ? "Remover dos favoritos" : "Adicionar aos favoritos"} aria-label={`Favoritar ${store.name}`}><span className={store.is_favorite ? "text-rose-500" : "text-slate-300"} aria-hidden="true">♥</span></button></form>}
        <div className="store-top"><div className="logo">{store.logo_url ? <img src={store.logo_url} alt={`Logo ${store.name}`} width="66" height="66" loading="lazy"/> : <span aria-hidden="true">{store.name?.slice(0,1)?.toUpperCase()}</span>}</div><div className="store-identity"><h3>{store.name}</h3><p className="store-location">{store.distance_km != null ? `${Number(store.distance_km).toLocaleString("pt-BR",{maximumFractionDigits:1})} km de você` : [store.city,store.state].filter(Boolean).join("/")}</p>{store.is_featured && <p className="featured">✦ Em destaque</p>}</div></div>
        {store.description && <p className="store-description">{store.description}</p>}
        {!!store.categories?.length && <div className="store-categories">{store.categories.slice(0,3).map((cat:any,i:number)=><span key={i}>{cat.name}</span>)}</div>}
        {!!store.matched_products?.length && <div className="matched"><strong>Encontrado nesta loja</strong>{store.matched_products.map((product:any) => <span key={product.id}>{product.name} · {Number(product.price).toLocaleString("pt-BR",{style:"currency",currency:"BRL"})}</span>)}</div>}
        <div className="store-status"><span className={`status ${store.is_open ? "open" : "closed"}`}>{store.is_open ? "Aberto agora" : "Fechado"}</span>{store.accepts_delivery && <span>Entrega</span>}{store.accepts_pickup && <span>Retirada</span>}</div>
        {store.delivery?.status === "pickup_only" ? <p className="delivery-state">Somente retirada</p> : store.delivery?.status === "available" ? <p className="delivery-state available">Entrega no seu endereço · {store.delivery.fee_display}</p> : store.delivery?.status === "unavailable" ? <p className="delivery-state unavailable">Não entrega neste endereço</p> : store.accepts_delivery && <p className="delivery-state">Confirme o endereço para entrega</p>}
        <div className="card-bottom" aria-hidden="true"><span>Explorar loja</span><span className="card-arrow">↗</span></div>
      </article>)}</div> : <div className="empty"><div className="empty-icon" aria-hidden="true">⌕</div><h3>Vamos encontrar outra opção?</h3><p>Nenhuma loja encontrada com esses filtros. Busque outro produto ou amplie sua região.</p><a className="btn btn-dark" href="/">Ver todas as lojas ↗</a></div>}
      {(p.pagination?.previous || p.pagination?.next) && <nav className="pagination" aria-label="Paginação">{p.pagination.previous && <a className="btn" href={p.pagination.previous + "#lojas"}>← Anterior</a>}<span>Página {p.pagination.page}</span>{p.pagination.next && <a className="btn" href={p.pagination.next + "#lojas"}>Próxima →</a>}</nav>}
    </main>
    <section className="wrap how-it-works" aria-label="Como pedir"><p className="how-title">Da vontade<br/>ao seu próximo pedido.</p><div className="step"><span className="step-number">01</span><div><strong>Encontre sua loja</strong><p>Explore as lojas da região.</p></div></div><div className="step"><span className="step-number">02</span><div><strong>Escolha os produtos</strong><p>Monte o pedido do seu jeito.</p></div></div><div className="step"><span className="step-number">03</span><div><strong>Combine com a loja</strong><p>Envie seu pedido pelo WhatsApp.</p></div></div></section>
    <footer className="footer"><div className="wrap footer-inner"><a className="footer-brand" href="/" aria-label="VemDeDelivery, início"><img src="/static/images/brand/logo-vemdedelivery-clara.svg" alt="VemDeDelivery" width="365" height="72"/></a><p className="footer-tagline">Seu bairro. Suas lojas. Seu próximo pedido.</p><div className="footer-company"><strong>COBRADEV SOLUTIONS</strong><p>CNPJ 59.198.345/0001-44</p></div><div className="footer-legal"><a href="/termos/">Termos de Serviço</a> · <a href="/privacidade/">Política de Privacidade</a></div><a className="btn btn-orange" href="/para-lojistas/">Sou lojista · Conheça o VemDeDelivery</a><div className="footer-meta"><p>© {data.year} VemDeDelivery</p><p>Dados de localização: <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a></p></div></div></footer>
  </div>;
}
