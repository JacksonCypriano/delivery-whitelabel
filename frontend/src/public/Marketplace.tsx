import { useState } from "react";
import { CSRF, PostButton } from "./PublicApp";
import { AddressFields } from "./Commerce";

/** Marketplace visual baseado na vitrine pública anterior, mantendo os contratos do React. */
export function Marketplace({ data }: any) {
  const p = data.props;
  const [geoError, setGeoError] = useState("");
  const [editAddress, setEditAddress] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  function locate() {
    if (!navigator.geolocation) {
      setGeoError("Localização indisponível neste navegador.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const query = new URLSearchParams(window.location.search);
        query.set("lat", String(coords.latitude));
        query.set("lng", String(coords.longitude));
        query.set("accuracy", String(coords.accuracy));
        query.delete("page");
        window.location.assign("?" + query);
      },
      () => setGeoError("Não foi possível obter sua localização. Informe seu endereço."),
    );
  }

  function categoryUrl(slug: string) {
    const query = new URLSearchParams();
    if (p.search) query.set("q", p.search);
    if (p.selected_city) query.set("cidade", p.selected_city);
    if (p.selected_state) query.set("uf", p.selected_state);
    if (p.open_only) query.set("abertas", "1");
    if (p.favorites_only) query.set("favoritas", "1");
    if (p.location_active && p.user_latitude != null && p.user_longitude != null) {
      query.set("lat", String(p.user_latitude));
      query.set("lng", String(p.user_longitude));
      if (p.user_accuracy != null) query.set("accuracy", String(p.user_accuracy));
    }
    if (slug) query.set("categoria", slug);
    const result = query.toString();
    return (result ? `?${result}` : "/") + "#lojas";
  }

  function favoritesUrl(enable: boolean) {
    const url = categoryUrl(p.selected_category || "");
    const [path, anchor] = url.split("#");
    const query = new URLSearchParams(path.startsWith("?") ? path.slice(1) : "");
    if (enable) query.set("favoritas", "1"); else query.delete("favoritas");
    return (query.toString() ? "?" + query : "/") + (anchor ? "#" + anchor : "");
  }

  const address = p.global_delivery_location;
  const storeLabel = p.favorites_only ? "Suas lojas favoritas" : p.location_active ? "Perto de você" : p.selected_city ? `Lojas em ${p.selected_city}` : "Descubra seu próximo favorito";

  return <div className="mp-page">
    <section className="mp-hero" aria-labelledby="mp-hero-title">
      <div className="mp-hero-panel">
        <div className="mp-eyebrow">Seu bairro tem o que você procura</div>
        <h1 id="mp-hero-title">Deu vontade?<br /><em>Vem de delivery.</em></h1>
        <p>Descubra as lojas da sua região e encontre o lugar certo para o seu próximo pedido.</p>
        <div className="mp-hero-tags"><span>Lojas da sua região</span><span>Entrega ou retirada</span></div>
      </div>
      <div className="mp-delivery-bar" id="endereco-entrega">
        <span className="mp-pin" aria-hidden="true">⌖</span>
        <div className="mp-delivery-copy">
          <small>Onde vai ser o pedido?</small>
          <p>{address ? `${address.label ? address.label + " · " : ""}${address.neighborhood || address.street || ""}, ${address.city || ""}${address.state ? "/" + address.state : ""}` : "Encontre sua região. Você confirma o endereço e a taxa no checkout."}</p>
        </div>
        {data.user.authenticated && <a className="mp-btn mp-btn-light" href="/conta/enderecos/">{address ? "Alterar endereço" : "Meus endereços"} ↗</a>}
      </div>
    </section>

    <section className="mp-search" aria-label="Buscar e filtrar lojas">
      <div className="mp-search-head"><span>Explore sua região</span><button className="mp-filter-toggle" type="button" onClick={() => setShowFilters(v => !v)} aria-expanded={showFilters} aria-controls="mp-filters">{showFilters ? "Ocultar filtros" : "Mostrar filtros"}</button></div>
      <form className="mp-search-form" method="get" id="mp-filters">
        {p.location_active && p.user_latitude != null && p.user_longitude != null && <>
          <input type="hidden" name="lat" value={p.user_latitude} />
          <input type="hidden" name="lng" value={p.user_longitude} />
          {p.user_accuracy != null && <input type="hidden" name="accuracy" value={p.user_accuracy} />}
        </>}
        <div className="mp-search-grid">
          <label className="mp-field mp-query"><span className="mp-sr-only">Buscar loja ou produto</span><span className="mp-search-icon" aria-hidden="true">⌕</span><input name="q" type="search" defaultValue={p.search} placeholder="O que você quer pedir hoje?" /></label>
          <label className="mp-field mp-filter-field"><span className="mp-sr-only">Cidade</span><input name="cidade" list="mp-cities" defaultValue={p.selected_city} placeholder="Cidade" /></label>
          <datalist id="mp-cities">{(p.cities || []).map((city: string) => <option key={city} value={city} />)}</datalist>
          <label className="mp-field mp-filter-field"><span className="mp-sr-only">UF</span><input name="uf" defaultValue={p.selected_state} maxLength={2} placeholder="UF" /></label>
          <button type="submit" className="mp-btn mp-btn-primary">Buscar lojas</button>
        </div>
        <div className={`mp-filters ${showFilters ? "mp-filters-open" : ""}`}>
          <label><input type="checkbox" name="abertas" value="1" defaultChecked={p.open_only} /> Abertas agora</label>
          <label><input type="checkbox" name="favoritas" value="1" defaultChecked={p.favorites_only} /> Somente favoritas</label>
          <button type="button" onClick={locate}>⌖ Usar minha localização</button>
          <button type="button" onClick={() => setEditAddress(v => !v)}>{editAddress ? "Fechar endereço" : "Informar endereço"}</button>
          <a href="/">Limpar filtros</a>
        </div>
      </form>
      {geoError && <p className="mp-notice" role="alert">{geoError}</p>}
      {editAddress && <div className="mp-address-forms">
        <form method="post" action="/localizacao-entrega/" className="mp-address-form"><CSRF data={data} /><h3>Onde você quer receber?</h3><input type="hidden" name="mode" value="manual" /><AddressFields initial={address || {}} />{data.user.authenticated && <label><input type="checkbox" name="save_address" value="1" /> Salvar nos meus endereços</label>}<button type="submit">Confirmar endereço</button></form>
        {(p.customer_addresses || []).length > 0 && <form method="post" action="/localizacao-entrega/" className="mp-address-form"><CSRF data={data} /><input type="hidden" name="mode" value="saved" /><label className="public-field">Endereços salvos<select name="customer_address_id">{p.customer_addresses.map((a: any) => <option key={a.id} value={a.id}>{a.label} — {a.street}, {a.number}</option>)}</select></label><button type="submit">Usar endereço salvo</button></form>}
        {address && <PostButton data={data} action="/localizacao-entrega/remover/">Remover localização</PostButton>}
      </div>}
      <nav className="mp-categories" aria-label="Categorias de lojas">
        <a className={!p.selected_category ? "active" : ""} href={categoryUrl("")}>Todas as lojas</a>
        {(p.categories || []).map((category: any) => <a key={category.slug} className={p.selected_category === category.slug ? "active" : ""} href={categoryUrl(category.slug)}>{category.icon && <span aria-hidden="true">{category.icon}</span>}{category.name}</a>)}
      </nav>
    </section>

    <section className="mp-results" id="lojas">
      <div className="mp-results-head"><div><h2>{storeLabel}</h2><p>{p.result_count} {p.result_count === 1 ? "loja encontrada" : "lojas encontradas"}{p.search ? ` para “${p.search}”` : ""}</p></div>{data.user.authenticated && <div className="mp-account-links"><a className="mp-btn mp-btn-light" href="/meus-pedidos/">Meus pedidos</a><a className="mp-btn mp-btn-light" href={favoritesUrl(!p.favorites_only)}>♥ Favoritas {p.favorite_count ? `· ${p.favorite_count}` : ""}</a></div>}</div>
      {p.stores.length > 0 ? <div className="mp-stores">
        {p.stores.map((store: any) => <article key={store.id} className="mp-store-card">
          <div className="mp-store-top"><div className="mp-store-logo">{store.logo_url ? <img src={store.logo_url} alt="" loading="lazy" /> : <span>{store.name.slice(0, 1)}</span>}</div><div className="mp-store-name"><h3><a href={store.url}>{store.name}</a></h3><small>{[store.city, store.state].filter(Boolean).join("/")}{store.distance_km != null ? ` · ${Number(store.distance_km).toFixed(1)} km` : ""}</small></div><div className="mp-store-favorite"><PostButton data={data} action={`/favoritos/loja/${store.id}/`}>{store.is_favorite ? "♥" : "♡"}</PostButton></div></div>
          {store.description && <p className="mp-store-description">{store.description}</p>}
          {store.categories?.length > 0 && <div className="mp-store-categories">{store.categories.map((cat: any, index: number) => <span key={index}>{cat.icon} {cat.name}</span>)}</div>}
          {store.matched_products?.length > 0 && <div className="mp-matched"><strong>Produtos encontrados</strong>{store.matched_products.map((product: any) => <span key={product.id}>{product.name}</span>)}</div>}
          <div className="mp-store-bottom"><span className={store.is_open ? "mp-open" : "mp-closed"}>{store.is_open ? "Aberta agora" : "Fechada agora"}</span><span>{store.delivery?.message || store.delivery?.fee_display || (store.delivery?.status === "pickup_only" ? "Somente retirada" : "Taxa de entrega no checkout")}</span></div>
          <a className="mp-store-action" href={store.url}>Ver cardápio <span aria-hidden="true">↗</span></a>
        </article>)}
      </div> : <div className="mp-empty"><div aria-hidden="true">⌕</div><h3>Nenhuma loja encontrada</h3><p>Tente alterar a cidade, os filtros ou o termo pesquisado.</p><a className="mp-btn mp-btn-primary" href="/">Ver todas as lojas</a></div>}
      {(p.pagination.previous || p.pagination.next) && <nav className="mp-pagination" aria-label="Paginação">{p.pagination.previous && <a href={p.pagination.previous}>← Anterior</a>}<span>Página {p.pagination.page}</span>{p.pagination.next && <a href={p.pagination.next}>Próxima →</a>}</nav>}
    </section>
    <section className="mp-steps"><h2>Como funciona?</h2><div><span><b>01</b><strong>Encontre sua loja</strong><small>Explore lojas e produtos perto de você</small></span><span><b>02</b><strong>Monte seu pedido</strong><small>Escolha itens e personalize do seu jeito</small></span><span><b>03</b><strong>Receba ou retire</strong><small>Você escolhe como prefere comprar</small></span></div></section>
  </div>;
}
