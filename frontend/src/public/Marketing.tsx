import { Fragment } from "react";
export function Landing({data}:any){const p=data.props;return <>

<a className="skip" href="#conteudo">Pular para o conteúdo</a>
<header className="site-header">
  <div className="wrap top">
    <a href="/" aria-label="VemDeDelivery, marketplace"><img src="/static/images/brand/logo-vemdedelivery.svg" width="220" height="44" alt="VemDeDelivery"/></a>
    <nav aria-label="Navegação principal">
      <a href="#recursos">Recursos</a>
      <a href="#agente">Agente no WhatsApp</a>
      <a href="#segmentos">Segmentos</a>
      <a href="#plano">Planos</a>
      <a href="#duvidas">Dúvidas</a>
    </nav>
    <a className="button small" href={p.whatsapp} data-cta="header">Quero minha loja ↗</a>
  </div>
</header>

<main id="conteudo">
  <section className="hero wrap">
    <div className="hero-copy">
      <p className="eyebrow">PARA DELIVERY E COMÉRCIO LOCAL</p>
      <h1>Sua loja online, com pedidos e <em>agente no WhatsApp.</em></h1>
      <p className="lead">Crie seu cardápio ou catálogo online, divulgue um link próprio e deixe o cliente comprar direto da sua loja. O VemDeDelivery reúne vitrine, carrinho, painel de gestão e atendimento no WhatsApp.</p>
      <div className="actions">
        <a className="button" href={p.whatsapp} data-cta="hero">Quero vender com o VemDeDelivery ↗</a>
        <a className="text-link" href={p.demo_url} data-cta="demo">Explorar a loja demo →</a>
      </div>
      <div className="hero-proof" aria-label="Condições principais">
        <span><strong>R$ 149/mês</strong><small>plano mensal</small></span>
        <span><strong>0% de comissão</strong><small>do VemDeDelivery por pedido</small></span>
        <span><strong>Sem app</strong><small>seu cliente abre pelo navegador</small></span>
      </div>
    </div>

    <div className="showcase" aria-label="Representação do catálogo e do atendimento pelo WhatsApp">
      <div className="showcase-head"><span>SEU CANAL PRÓPRIO</span><span>catálogo + WhatsApp</span></div>
      <div className="store-window">
        <div className="browser-bar"><i></i><i></i><i></i><span>sualoja.vemdedelivery.com.br</span></div>
        <div className="store-mini-head">
          <div className="brand-mark">S</div>
          <div><strong>Sua Loja</strong><small>Entrega e retirada disponíveis</small></div>
          <b>2 itens</b>
        </div>
        <div className="catalog-grid">
          <div className="catalog-product"><span className="product-art art-one"></span><strong>Produto em destaque</strong><small>Opções e adicionais</small><b>R$ 29,90</b></div>
          <div className="catalog-product"><span className="product-art art-two"></span><strong>Outro favorito</strong><small>Descrição clara</small><b>R$ 18,90</b></div>
        </div>
        <div className="cart-line"><span>Carrinho</span><strong>Revisar pedido →</strong></div>
      </div>
      <div className="agent-card">
        <div className="agent-title"><span className="status-dot"></span><strong>Agente no WhatsApp</strong><small>usando dados da sua loja</small></div>
        <p className="bubble customer">Quero 2 unidades e tirar um adicional. Faz entrega?</p>
        <p className="bubble agent">Claro. Atualizo seu carrinho e confiro a entrega para seu endereço. Se preferir, você também pode retirar na loja.</p>
      </div>
      <p className="illustration">Representação da experiência. A loja demo mostra o catálogo funcionando.</p>
    </div>
  </section>

  <div className="strip" aria-label="Principais benefícios">
    <div className="wrap">
      <span>Marca da sua loja</span>
      <span>Catálogo e carrinho</span>
      <span>Pedidos no WhatsApp</span>
      <span>Entrega ou retirada</span>
      <span>Sem comissão por pedido</span>
    </div>
  </div>

  <section id="recursos" className="wrap section">
    <div className="section-heading">
      <p className="eyebrow">DO PRIMEIRO CLIQUE AO PEDIDO</p>
      <h2>Uma estrutura para sua loja vender direto.</h2>
      <p className="intro">O VemDeDelivery foi além de um cardápio bonito: ele conecta apresentação, atendimento e operação para reduzir o atrito entre o cliente encontrar sua loja e concluir o pedido.</p>
    </div>
    <div className="cards feature-cards">
      <article><span className="number">01 / VITRINE</span><h3>Cardápio ou catálogo com sua marca</h3><p>Logo, cores, banner, categorias, produtos, fotos, preços e descrições em uma experiência responsiva para celular e computador.</p></article>
      <article><span className="number">02 / PRODUTO</span><h3>Opções, adicionais e combinações</h3><p>Cadastre escolhas ligadas ao produto. Para operações como pizzaria, o projeto também possui fluxo de pizza meio a meio.</p></article>
      <article><span className="number">03 / PEDIDO</span><h3>Carrinho e checkout organizados</h3><p>O cliente adiciona itens, revisa o carrinho e avança com as informações necessárias para entrega ou retirada.</p></article>
      <article><span className="number">04 / OPERAÇÃO</span><h3>Horários, entrega e retirada</h3><p>Configure períodos de funcionamento, modalidades de atendimento, áreas e taxas de entrega de acordo com a realidade da loja.</p></article>
      <article><span className="number">05 / RELACIONAMENTO</span><h3>Cupons e campanhas</h3><p>Use recursos promocionais para ações próprias e divulgue o mesmo link em Instagram, WhatsApp, QR Codes e anúncios.</p></article>
      <article><span className="number">06 / GESTÃO</span><h3>Painel do lojista</h3><p>Administre catálogo, pedidos e configurações da loja sem depender de alguém para cada alteração do dia a dia.</p></article>
    </div>
  </section>

  <section id="agente" className="agent-section">
    <div className="wrap agent-layout">
      <div>
        <p className="eyebrow">UM DOS PRINCIPAIS DIFERENCIAIS</p>
        <h2>Seu WhatsApp pode atender e ajudar a montar o pedido.</h2>
        <p className="intro">O agente não trabalha com um texto genérico. Ele consulta informações cadastradas na própria loja para responder e conduzir o cliente com contexto.</p>
        <a className="text-link" href="/agente-whatsapp-delivery/">Conheça o agente em detalhes →</a>
      </div>
      <div className="agent-capabilities">
        <article><span>01</span><div><h3>Responde sobre o que você vende</h3><p>Produtos, preços, ingredientes, opções, adicionais, promoções e informações do catálogo.</p></div></article>
        <article><span>02</span><div><h3>Conhece como a loja atende</h3><p>Horários, entrega, retirada, áreas e taxas, além das formas de pagamento configuradas.</p></div></article>
        <article><span>03</span><div><h3>Trabalha com o carrinho</h3><p>Pode adicionar, remover, trocar itens, alterar quantidades e revisar o pedido antes da confirmação.</p></div></article>
        <article><span>04</span><div><h3>Entrega para uma pessoa quando precisa</h3><p>O cliente pode pedir atendimento humano; a automação não precisa bloquear a conversa com a equipe.</p></div></article>
      </div>
    </div>
    <div className="wrap agent-note">
      <strong>Pagamento online:</strong> quando a loja habilita a integração, o fluxo pode oferecer Pix online e aguardar a confirmação do provedor antes de efetivar o pedido. Outras formas podem ser combinadas para entrega ou retirada conforme a configuração.
    </div>
  </section>

  <section className="soft">
    <div className="wrap section split process-section">
      <div>
        <p className="eyebrow">COMEÇAR É SIMPLES</p>
        <h2>Do cadastro ao seu novo canal de vendas.</h2>
        <p className="intro">Você pode configurar a loja pelo próprio painel. Se quiser ajuda com a implantação e cadastro inicial, existem serviços opcionais contratados à parte da assinatura.</p>
        <a className="text-link" href={p.demo_url} data-cta="demo_steps">Ver uma loja funcionando →</a>
      </div>
      <ol className="steps">
        <li><h3>Contrate o plano</h3><p>Escolha a opção comercial e receba as orientações para o primeiro acesso.</p></li>
        <li><h3>Monte sua vitrine</h3><p>Cadastre identidade, categorias, produtos, horários, entrega e retirada.</p></li>
        <li><h3>Conecte o WhatsApp</h3><p>Ative o atendimento inteligente e deixe o canal alinhado às informações da sua loja.</p></li>
        <li><h3>Divulgue seu link</h3><p>Use nas redes sociais, mensagens, materiais físicos e campanhas de tráfego.</p></li>
      </ol>
    </div>
  </section>

  <section id="segmentos" className="wrap section segments-section">
    <div className="section-heading wide-heading">
      <p className="eyebrow">NÃO É SÓ PARA RESTAURANTE</p>
      <h2>Feito para negócios locais que vendem produtos.</h2>
      <p className="intro">Alimentação continua sendo um ponto forte, mas a mesma estrutura pode servir a muitos comércios que trabalham com catálogo, retirada, entrega e atendimento direto.</p>
    </div>
    {(p.page_groups||[]).map(([group_name,pages]:any,index:number) => <Fragment key={index}>
      <div className="segment-group">
        <h3>{group_name}</h3>
        <div className="segment-links">
          {pages.map((item:any,index:number) => <Fragment key={index}>
            <a href={item.url}><strong>{item.title.replace(" | VemDeDelivery", "")}</strong><span>{item.description}</span><b>Ver solução →</b></a>
          </Fragment>)}
        </div>
      </div>
    </Fragment>)}
  </section>

  <section id="plano" className="pricing-band">
    <div className="wrap section split pricing">
      <div>
        <p className="eyebrow">UMA ASSINATURA. SEU CANAL PRÓPRIO.</p>
        <h2>Comece por R$ 149 por mês.</h2>
        <p className="intro">Sem comissão do VemDeDelivery sobre cada pedido. Além do mensal, a estrutura comercial conta com opções trimestral, semestral e anual com descontos progressivos.</p>
        <div className="pricing-points">
          <p><strong>Nota fiscal:</strong> as cobranças pagas contam com o fluxo fiscal da plataforma e a NFS-e autorizada pode ser enviada automaticamente por e-mail.</p>
          <p><strong>Implantação opcional:</strong> se você preferir que a equipe ajude no cadastro inicial, esse serviço é contratado separadamente da assinatura.</p>
        </div>
      </div>
      <article className="plan">
        <span className="pill">VemDeDelivery</span>
        <h3>Plano mensal</h3>
        <div className="price">R$ 149<span>/mês</span></div>
        <p>Um canal próprio para apresentar, atender e receber pedidos.</p>
        <ul>
          <li>Cardápio ou catálogo com sua identidade</li>
          <li>Carrinho, entrega e retirada</li>
          <li>Pedidos e agente no WhatsApp</li>
          <li>Painel de gestão da loja</li>
          <li>Cupons e recursos promocionais</li>
          <li>Sem comissão do VemDeDelivery por pedido</li>
        </ul>
        <a className="button" href={p.whatsapp} data-cta="plan">Quero contratar para minha loja ↗</a>
        <small>Pagamentos online, quando habilitados, podem ter tarifas do provedor de pagamento. Serviços adicionais de implantação/cadastro são cobrados à parte.</small>
      </article>
    </div>
  </section>

  <section id="duvidas" className="wrap section faq">
    <div><p className="eyebrow">ANTES DE COMEÇAR</p><h2>Perguntas frequentes.</h2></div>
    <div>
      {p.landing_faq.map(([question,answer]:any,index:number) => <Fragment key={index}>
        <details><summary>{question}</summary><p>{answer}</p></details>
      </Fragment>)}
      <details><summary>Posso conhecer antes de contratar?</summary><p>Sim. <a href={p.demo_url}>Abra a loja de demonstração</a> para navegar pelo catálogo e depois fale com a equipe pelo WhatsApp.</p></details>
      <details><summary>Como faço para me tornar uma loja parceira?</summary><p>Clique em “Quero minha loja”, fale com a equipe no WhatsApp e receba as orientações de contratação e configuração.</p></details>
    </div>
  </section>

  <section className="final">
    <div className="wrap">
      <p className="eyebrow">SUA MARCA. SEU CLIENTE. SEU CANAL.</p>
      <h2>Coloque sua loja no próximo pedido.</h2>
      <p className="final-lead">Conheça a plataforma, conte como sua operação funciona e veja como o VemDeDelivery pode entrar na rotina do seu negócio.</p>
      <a className="button light" href={p.whatsapp} data-cta="footer">Conversar sobre minha loja ↗</a>
    </div>
  </section>
</main>

<footer className="wrap bottom">
  <img src="/static/images/brand/logo-vemdedelivery.svg" width="200" height="40" alt="VemDeDelivery"/>
  <p>COBRADEV SOLUTIONS · CNPJ 59.198.345/0001-44<br/>© {data.year} VemDeDelivery</p>
  <div>{p.marketing_consent_enabled && <><button type="button" data-vdd-reopen="">Preferências de métricas</button></>}<a href="/privacidade/">Privacidade</a><a href="/termos/">Termos</a><a href="/">Encontrar lojas</a></div>
</footer>

</>;}
export function SEOPage({data}:any){const p=data.props;return <>

<a className="skip" href="#conteudo">Pular para o conteúdo</a>
<header className="site-header">
  <div className="wrap top">
    <a href="/para-lojistas/" aria-label="VemDeDelivery para lojistas"><img src="/static/images/brand/logo-vemdedelivery.svg" width="220" height="44" alt="VemDeDelivery"/></a>
    <nav aria-label="Navegação principal"><a href="/para-lojistas/#recursos">Recursos</a><a href="/para-lojistas/#agente">Agente</a><a href="/para-lojistas/#segmentos">Segmentos</a><a href="#duvidas">Dúvidas</a></nav>
    <a className="button small" href={p.whatsapp} data-cta="seo_header">Quero minha loja ↗</a>
  </div>
</header>

<main id="conteudo">
  <div className="wrap breadcrumb" aria-label="Breadcrumb"><a href="/">VemDeDelivery</a><span>›</span><a href={p.landing_url}>Para lojistas</a><span>›</span><strong>{p.page.eyebrow}</strong></div>

  <section className="seo-hero wrap">
    <div>
      <p className="eyebrow">{p.page.eyebrow}</p>
      <h1>{p.page.h1} <em>{p.page.highlight}</em>.</h1>
      <p className="lead">{p.page.lead}</p>
      <div className="actions">
        <a className="button" href={p.whatsapp} data-cta="seo_hero">Quero conhecer para minha loja ↗</a>
        <a className="text-link" href={p.demo_url} data-cta="seo_demo">Abrir loja demo →</a>
      </div>
      <p className="note"><strong>R$ 149/mês</strong> · sem comissão do VemDeDelivery sobre pedidos</p>
    </div>
    <aside className="seo-summary">
      <span className="summary-kicker">O QUE ENTRA NO CANAL</span>
      <ul>
        <li><strong>Catálogo próprio</strong><span>produtos, fotos, preços e categorias</span></li>
        <li><strong>Pedido estruturado</strong><span>carrinho, entrega ou retirada</span></li>
        <li><strong>WhatsApp</strong><span>agente e atendimento da própria loja</span></li>
        <li><strong>Painel</strong><span>gestão da operação e do catálogo</span></li>
      </ul>
    </aside>
  </section>

  <div className="strip compact-strip"><div className="wrap"><span>Canal próprio</span><span>Sem app para o cliente</span><span>Sem comissão por pedido</span><span>Feito para comércio local</span></div></div>

  <section className="wrap section seo-intro">
    <div className="section-heading">
      <p className="eyebrow">POR QUE FAZ SENTIDO</p>
      <h2>{p.page.section_title}</h2>
      <p className="intro">{p.page.section_text}</p>
    </div>
    <div className="cards seo-benefits">
      {p.page.benefits.map(([title,text]:any,index:number) => <Fragment key={index}>
        <article><span className="number">0{index+1}</span><h3>{title}</h3><p>{text}</p></article>
      </Fragment>)}
    </div>
  </section>

  <section className="soft use-cases">
    <div className="wrap section split">
      <div>
        <p className="eyebrow">NA PRÁTICA</p>
        <h2>O catálogo acompanha o jeito que seu negócio vende.</h2>
        <p className="intro">Você escolhe o que destacar e como organizar a vitrine. O VemDeDelivery fornece a estrutura para transformar essa apresentação em um caminho claro até o pedido.</p>
      </div>
      <div className="example-list">
        {p.page.examples.map((example:string,index:number) => <Fragment key={index}><div><span>0{index+1}</span><strong>{example}</strong></div></Fragment>)}
      </div>
    </div>
  </section>

  <section className="wrap section seo-platform">
    <div className="section-heading wide-heading">
      <p className="eyebrow">A MESMA PLATAFORMA POR TRÁS</p>
      <h2>Catálogo, pedido e atendimento conversando entre si.</h2>
      <p className="intro">Independentemente do segmento, a loja usa os mesmos dados para apresentar produtos, orientar o cliente e operar o pedido.</p>
    </div>
    <div className="platform-grid">
      <article><h3>Catálogo e carrinho</h3><p>Categorias, produtos, fotos, preços, opções e adicionais, com carrinho para revisar a compra.</p><a href="/cardapio-online/">Ver cardápio online →</a></article>
      <article><h3>Agente no WhatsApp</h3><p>Responde com base nos dados da loja e pode apoiar alterações no carrinho, entrega, retirada e finalização.</p><a href="/agente-whatsapp-delivery/">Ver agente no WhatsApp →</a></article>
      <article><h3>Operação local</h3><p>Horários, áreas e taxas de entrega, retirada e formas de pagamento configuradas pelo estabelecimento.</p><a href="/pedidos-pelo-whatsapp/">Ver pedidos pelo WhatsApp →</a></article>
      <article><h3>Canal sem comissão</h3><p>Assinatura do VemDeDelivery sem percentual sobre o valor de cada pedido feito pelo seu canal.</p><a href="/delivery-sem-comissao/">Ver modelo sem comissão →</a></article>
    </div>
  </section>

  <section className="agent-section seo-agent-callout">
    <div className="wrap agent-layout">
      <div>
        <p className="eyebrow">ATENDIMENTO INTELIGENTE</p>
        <h2>O WhatsApp não precisa ser só uma caixa de entrada.</h2>
        <p className="intro">O agente consulta produtos, preços, opções, horários e entrega. Quando o cliente quer comprar, ele pode ajudar a montar e revisar o carrinho; quando precisa de uma pessoa, a loja pode assumir.</p>
      </div>
      <div className="mini-chat" aria-label="Exemplo de atendimento">
        <p className="bubble customer">Tem esse produto? E vocês entregam no meu bairro?</p>
        <p className="bubble agent">Vou conferir no catálogo e nas áreas de entrega da loja. Se estiver tudo certo, posso ajudar a montar seu pedido.</p>
        <p className="chat-caption">O atendimento usa informações configuradas pelo estabelecimento.</p>
      </div>
    </div>
  </section>

  {p.related_pages.length>0 && <>
  <section className="wrap section related-section">
    <div className="section-heading"><p className="eyebrow">CONTINUE EXPLORANDO</p><h2>Outras soluções que podem fazer sentido.</h2></div>
    <div className="related-grid">
      {p.related_pages.map((item:any,index:number) => <Fragment key={index}>
        <a href={item.url}><strong>{item.title}</strong><span>{item.description}</span><b>Conhecer →</b></a>
      </Fragment>)}
    </div>
  </section>
  </>}

  <section className="pricing-band compact-pricing">
    <div className="wrap section split pricing">
      <div>
        <p className="eyebrow">SEU CANAL PRÓPRIO</p>
        <h2>R$ 149/mês no plano mensal.</h2>
        <p className="intro">Sem comissão do VemDeDelivery por pedido. Há opções trimestral, semestral e anual com descontos progressivos, além de serviços opcionais de implantação contratados separadamente.</p>
      </div>
      <article className="plan slim-plan">
        <span className="pill">Incluído</span>
        <ul><li>Catálogo com sua marca</li><li>Carrinho e pedido</li><li>Agente no WhatsApp</li><li>Painel do lojista</li><li>Entrega ou retirada</li></ul>
        <a className="button" href={p.whatsapp} data-cta="seo_plan">Quero falar sobre minha loja ↗</a>
        <small>Pagamentos online podem ter tarifas do provedor quando habilitados.</small>
      </article>
    </div>
  </section>

  <section id="duvidas" className="wrap section faq">
    <div><p className="eyebrow">DÚVIDAS SOBRE ESTA SOLUÇÃO</p><h2>Perguntas frequentes.</h2></div>
    <div>
      {p.page.faq.map(([question,answer]:any,index:number) => <Fragment key={index}><details><summary>{question}</summary><p>{answer}</p></details></Fragment>)}
      <details><summary>Como conheço o VemDeDelivery antes de contratar?</summary><p>Você pode <a href={p.demo_url}>navegar na loja demo</a> e conversar com a equipe pelo WhatsApp para explicar sua operação.</p></details>
    </div>
  </section>

  <section className="final">
    <div className="wrap">
      <p className="eyebrow">SEU NEGÓCIO, SEU CANAL</p>
      <h2>Quer ver como isso pode funcionar na sua loja?</h2>
      <p className="final-lead">Conte o que você vende, como entrega e como atende hoje. A equipe explica a contratação e os próximos passos.</p>
      <a className="button light" href={p.whatsapp} data-cta="seo_footer">Conversar pelo WhatsApp ↗</a>
    </div>
  </section>
</main>

<footer className="wrap bottom">
  <img src="/static/images/brand/logo-vemdedelivery.svg" width="200" height="40" alt="VemDeDelivery"/>
  <p>COBRADEV SOLUTIONS · CNPJ 59.198.345/0001-44<br/>© {data.year} VemDeDelivery</p>
  <div>{p.marketing_consent_enabled && <><button type="button" data-vdd-reopen="">Preferências de métricas</button></>}<a href="/para-lojistas/">Para lojistas</a><a href="/privacidade/">Privacidade</a><a href="/termos/">Termos</a></div>
</footer>

</>;}
