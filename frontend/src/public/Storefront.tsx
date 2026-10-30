import { createContext, useContext, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';

const StoreContext = createContext<any>(null);
export const useStorefront = () => useContext(StoreContext);
export function StoreIcon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, string> = {
    bag: 'M16 11V7a4 4 0 0 0-8 0v4M5 9h14l1 12H4L5 9z',
    moon: 'M21 12.79A9 9 0 0 1 11.21 3 7 7 0 0 0 21 12.79z',
    sun: 'M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364-.707.707M6.343 17.657l-.707.707M17.657 17.657l-.707-.707M6.343 6.343l-.707-.707M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z',
    search: 'm21 21-4.35-4.35M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
    menu: 'M4 6h16M4 12h16M4 18h16', close: 'm6 6 12 12M6 18 18 6',
    user: 'M20 21a8 8 0 0 0-16 0M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
    arrow: 'M5 12h14m-6-6 6 6-6 6', plus: 'M12 5v14M5 12h14',
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.bag}/></svg>;
}

export function Storefront({ data, theme, children }: { data: any; theme: CSSProperties; children: ReactNode }) {
  const store = data.store, brand = store.brand || {};
  const [dark, setDark] = useState(false), [search, setSearch] = useState('');
  const [count, setCount] = useState(Number(store.cart_count || 0));
  const header = useRef<HTMLElement>(null), shell = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)');
    const sync = () => {
      let saved: string | null = null;
      try { saved = localStorage.getItem('theme'); if (!saved) { const legacy = localStorage.getItem('vdd_catalog_dark'); if (legacy !== null) saved = legacy === 'true' ? 'dark' : 'light'; } } catch {}
      const next = Boolean(brand.dark_mode_enabled && (saved ? saved === 'dark' : media?.matches));
      setDark(next); document.documentElement.dataset.storeTheme = next ? 'dark' : 'light';
    };
    sync(); media?.addEventListener('change', sync); window.addEventListener('storage', sync);
    return () => { media?.removeEventListener('change', sync); window.removeEventListener('storage', sync); delete document.documentElement.dataset.storeTheme; };
  }, [brand.dark_mode_enabled]);
  useEffect(() => {
    const update = () => shell.current?.style.setProperty('--store-header-height', `${header.current?.offsetHeight || 64}px`);
    update(); const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update);
    if (header.current) observer?.observe(header.current);
    return () => observer?.disconnect();
  }, []);
  function toggleTheme() {
    const next = !dark; setDark(next); document.documentElement.dataset.storeTheme = next ? 'dark' : 'light';
    try { localStorage.setItem('theme', next ? 'dark' : 'light'); localStorage.setItem('vdd_catalog_dark', String(next)); } catch {}
  }
  const initials = store.name.split(/\s+/).slice(0, 2).map((s: string) => s[0]).join('');
  return <StoreContext.Provider value={{ search, setSearch, dark, count, setCount }}><div ref={shell} className={`public-shell storefront shell-${data.page} font-${(brand.font_family || 'Inter').toLowerCase()}`} style={theme} data-dark-enabled={Boolean(brand.dark_mode_enabled)}>
    <a className="vdd-skip" href="#vdd-content">Ir para o conteúdo</a>
    <header className="store-header" ref={header}><nav className="store-container store-header-inner" aria-label="Navegação da loja">
      <a className="store-brand" href="/" aria-label={`Voltar ao cardápio ${store.name}`}>{store.logo ? <img src={store.logo} alt="" width="40" height="40"/> : <span className="store-monogram">{initials}</span>}<strong>{store.name}</strong></a>
      {data.page === 'catalog' && brand.show_search_bar !== false && <label className="store-search"><span className="store-sr-only">Buscar no cardápio</span><StoreIcon name="search"/><input type="search" placeholder="Buscar no cardápio..." value={search} onChange={e => setSearch(e.target.value)}/></label>}
      <div className="store-header-actions">{brand.dark_mode_enabled && <button type="button" className="store-icon" aria-label={dark ? 'Usar tema claro' : 'Usar tema escuro'} aria-pressed={dark} onClick={toggleTheme}><StoreIcon name={dark ? 'sun' : 'moon'}/></button>}
        <a className="store-icon store-cart" href="/checkout/cart/" aria-label={`Carrinho, ${count} itens`}><StoreIcon name="bag" size={24}/>{count > 0 && <span key={count} className="store-count">{count}</span>}</a>
        <details className="store-account"><summary className="store-icon" aria-label="Minha conta"><StoreIcon name="user"/></summary><div>{data.user?.authenticated ? <><a href="/conta/">Minha conta</a><a href="/meus-pedidos/">Meus pedidos</a><form method="post" action="/conta/sair/"><input type="hidden" name="csrfmiddlewaretoken" value={data.csrf}/><button>Sair</button></form></> : <><a href="/conta/entrar/">Entrar</a><a href="/conta/criar-conta/">Criar conta</a></>}</div></details>
      </div>
    </nav></header>
    {children}
    <footer className="store-footer"><div className="store-container"><strong>{store.name}</strong><p>Feito com VemDeDelivery</p><nav aria-label="Informações"><a href="/">Cardápio</a><a href="/conta/">Minha conta</a><a href="/termos/">Termos de Serviço</a><a href="/privacidade/">Política de Privacidade</a></nav><small>© {data.year} VemDeDelivery · COBRADEV SOLUTIONS · CNPJ 59.198.345/0001-44</small></div></footer>
    {/^\d{10,15}$/.test(String(store.whatsapp || '').replace(/\D/g, '')) && <a className="store-contact" href={`https://wa.me/${String(store.whatsapp).replace(/\D/g, '')}`} aria-label="Falar com a loja no WhatsApp">WhatsApp ↗</a>}
  </div></StoreContext.Provider>;
}
