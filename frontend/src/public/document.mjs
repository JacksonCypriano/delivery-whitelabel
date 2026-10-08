import React from 'react';
import {renderToString, renderToStaticMarkup} from 'react-dom/server';
import {PublicApp} from './PublicApp';
const h=React.createElement;
export const safeJSON = value => JSON.stringify(value).replace(/</g,'\\u003c').replace(/\u2028/g,'\\u2028').replace(/\u2029/g,'\\u2029');
export function renderDocument(data) {
  if (!data.page || !data.assets?.js || !/^\/static\/public\/[\w./-]+\.js$/.test(data.assets.js)) throw new Error('Invalid render payload');
  const meta=data.meta||{}, p=data.props||{};
  const head=renderToStaticMarkup(h(React.Fragment,null,
    h('meta',{charSet:'utf-8'}),h('meta',{name:'viewport',content:'width=device-width, initial-scale=1'}),
    h('title',null,meta.title||'VemDeDelivery'),h('meta',{name:'robots',content:meta.robots||'noindex,follow'}),
    meta.description&&h('meta',{name:'description',content:meta.description}),meta.canonical&&h('link',{rel:'canonical',href:meta.canonical}),
    ...Object.entries({'og:type':'website','og:locale':'pt_BR','og:site_name':'VemDeDelivery','og:title':meta.title,'og:description':meta.description,'og:url':meta.canonical,'og:image':meta.image,'og:image:width':meta.image?'1200':null,'og:image:height':meta.image?'630':null}).filter(([,v])=>v).map(([property,content])=>h('meta',{key:property,property,content})),
    ...Object.entries({'twitter:card':'summary_large_image','twitter:title':meta.title,'twitter:description':meta.description,'twitter:image':meta.image}).filter(([,v])=>v).map(([name,content])=>h('meta',{key:name,name,content})),
    ...(data.assets.css||[]).map(href=>h('link',{key:href,rel:'stylesheet',href})),h('link',{rel:'icon',href:data.store?.favicon||'/static/images/brand/icone-vemdedelivery.svg'}),
    meta.schema&&h('script',{type:'application/ld+json',dangerouslySetInnerHTML:{__html:safeJSON(meta.schema)}})
  ));
  const app=renderToString(h(PublicApp,{data}));
  const consent=p.marketing_consent_enabled?renderToStaticMarkup(h(React.Fragment,null,
    h('div',{id:'vdd-consent-banner',className:'vdd-consent',role:'region','aria-label':'Preferências de privacidade',hidden:true},
      h('p',null,h('strong',null,'Métricas opcionais'),h('br'),'Usamos o Google Analytics, se você permitir, para entender visitas e campanhas. O contato por WhatsApp funciona mesmo sem aceitar. ',h('a',{href:'/privacidade/'},'Privacidade')),
      h('div',{className:'vdd-consent-actions'},h('button',{type:'button','data-vdd-consent':'no'},'Recusar'),h('button',{type:'button','data-vdd-consent':'yes'},'Aceitar métricas'))),
    h('div',{id:'vdd-marketing-data',hidden:true,'data-token':p.marketing_contact_token,'data-csrf':data.csrf,'data-click-url':'/marketing/registrar-clique/'}),h('script',{src:'/static/js/vdd-marketing.js',defer:true})
  )):'';
  const gtm=/^GTM-[A-Z0-9]+$/.test(p.google_tag_manager_id||'')?`<script>window.vddMarketingAnalyticsGranted=false;try{window.vddMarketingAnalyticsGranted=localStorage.getItem('vdd_analytics_permission')==='yes';if (window.vddMarketingAnalyticsGranted){window.dataLayer=window.dataLayer||[];window.dataLayer.push({'gtm.start':Date.now(),event:'gtm.js'});var s=document.createElement('script');s.async=true;s.src='https://www.googletagmanager.com/gtm.js?id=${p.google_tag_manager_id.replace(/-/g,'\\u002D')}';document.head.appendChild(s);}}catch(e){}</script>`:'';
  return `<!doctype html><html lang="pt-br"><head>${head}${gtm}</head><body><div id="public-root">${app}</div>${consent}<script id="public-data" type="application/json">${safeJSON(data)}</script><script type="module" src="${data.assets.js}"></script></body></html>`;
}
