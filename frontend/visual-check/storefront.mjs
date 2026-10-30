import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE ? pathToFileURL(process.env.PLAYWRIGHT_MODULE).href : 'playwright');
const output=path.resolve(process.env.VISUAL_OUTPUT||'visual-results');fs.mkdirSync(output,{recursive:true});
const base=process.env.VISUAL_BASE_URL||'http://127.0.0.1:4173';
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox']});
const results=[];
for(const width of [1440,768,390]){
 const context=await browser.newContext({viewport:{width,height:960},reducedMotion:'reduce'});
 await context.addInitScript(()=>{localStorage.setItem('vdd_analytics_permission','no');if(!localStorage.getItem('theme'))localStorage.setItem('theme','light');});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 async function snap(name){await page.screenshot({path:path.join(output,`${width}-${name}.png`),fullPage:/checkout|review|payment|coupon/.test(name)});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Horizontal overflow: ${width} ${name}`);}
 await page.goto(base);await page.getByRole('searchbox').waitFor();await snap('catalog-light');
 const cartColors=await page.locator('.catalog-cart-sticky-v2').evaluate(e=>({color:getComputedStyle(e).color,bg:getComputedStyle(e).backgroundColor}));assert.notEqual(cartColors.color,cartColors.bg,'Cart text must contrast with its background');
 await page.getByRole('searchbox').focus();await snap('focus');
 await page.getByRole('button',{name:/^Escolher /}).first().hover();await snap('hover');
 await page.getByText('Consultar entrega',{exact:true}).click();await page.getByLabel('Cidade',{exact:true}).fill('Itapevi');await page.getByLabel('Bairro',{exact:true}).fill('Centro');await page.getByRole('button',{name:'Consultar taxa'}).click();await page.getByText('Entrega disponível · R$ 5,00').waitFor();await snap('delivery-estimate');await page.getByText('Consultar entrega',{exact:true}).click();
 const theme=page.getByRole('button',{name:'Usar tema escuro'});await theme.click();await snap('catalog-dark');
 assert.equal(await page.evaluate(()=>localStorage.getItem('theme')),'dark');
 await page.getByRole('button',{name:'Usar tema claro'}).click();
 await page.getByRole('searchbox').fill('produto inexistente');await page.getByText('Nenhum produto encontrado').waitFor();await snap('search-empty');
 await page.getByRole('button',{name:'Limpar busca'}).click();
 await page.getByRole('button',{name:/^Escolher /}).first().click();await page.getByRole('dialog').waitFor();await page.getByRole('dialog').getByText('Catupiry',{exact:false}).waitFor();await snap('product');await page.getByRole('dialog').getByLabel('Quantidade').fill('0');await snap('product-disabled');
 await page.getByRole('dialog').getByLabel('Quantidade').fill('0');assert.equal(await page.getByRole('button',{name:'Adicionar ao carrinho'}).isEnabled(),false);
 await page.keyboard.press('Escape');assert.equal(await page.getByRole('dialog').count(),0);
 await page.getByRole('button',{name:/Montar pizza meio a meio com/}).first().click();await page.getByLabel('Segundo sabor').waitFor();await snap('half');await page.keyboard.press('Escape');
 let pendingOptions;
 await page.route('**/api/product/*/customizations/',route=>{pendingOptions=route;});
 await page.getByRole('button',{name:/^Escolher /}).first().click();await page.getByRole('status').filter({hasText:'Carregando opções'}).waitFor();await snap('product-loading');
 await pendingOptions.fulfill({status:200,contentType:'application/json',body:JSON.stringify({groups:[]})});await page.keyboard.press('Escape');await page.unroute('**/api/product/*/customizations/');
 await page.route('**/api/product/*/customizations/',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Não foi possível carregar as opções.'})}));
 await page.getByRole('button',{name:/^Escolher /}).first().click();await page.getByRole('button',{name:'Tentar novamente'}).waitFor();await snap('product-error');
 await page.unroute('**/api/product/*/customizations/');await page.getByRole('button',{name:'Tentar novamente'}).click();await page.getByRole('dialog').getByText('Catupiry',{exact:false}).waitFor();await page.keyboard.press('Escape');
 await page.getByRole('button',{name:'Usar tema escuro'}).click();
 await page.getByRole('button',{name:/^Escolher /}).first().click();await page.getByRole('dialog').getByText('Catupiry',{exact:false}).waitFor();await snap('product-dark');await page.keyboard.press('Escape');
 for(const route of ['checkout/cart/','checkout/checkout/','review/','payment/','empty-cart/','empty/','unavailable/','conta/entrar/','conta/enderecos/','conta/pedidos/','success/']){
  await page.goto(`${base}/${route}`);await page.getByRole('button',{name:'Usar tema claro'}).waitFor();
  await snap(route.replaceAll('/','-')+'dark');
  await page.getByRole('button',{name:'Usar tema claro'}).click();await snap(route.replaceAll('/','-')+'light');
  if(route==='checkout/checkout/'){
   await page.getByLabel('Modalidade').selectOption('pickup');assert.equal(await page.getByLabel('Rua',{exact:true}).count(),0);await page.getByText('Retirada sem taxa de entrega').waitFor();await snap('checkout-pickup');await page.getByLabel('Cupom',{exact:true}).fill('TESTE');await page.getByRole('button',{name:'Aplicar cupom',exact:true}).click();await page.getByText(/Prévia do total/).waitFor();await snap('coupon');
   await page.getByLabel('Quando pagar').selectOption('online');assert.equal(await page.getByRole('option',{name:'Dinheiro'}).count(),0);
  }
  await page.getByRole('button',{name:'Usar tema escuro'}).click();
 }
 await page.goto(`${base}/checkout/cart/`);
 if(width===1440){await page.getByLabel('Quantidade').fill('3');await page.getByRole('button',{name:'Atualizar quantidade'}).click();await page.getByRole('link',{name:'Carrinho, 3 itens'}).waitFor();await snap('cart-updated');}
 assert.deepEqual(errors,[]);results.push({width,status:'passed',checks:'responsive, themes, persistence, search, dialog, half, cart, checkout, review, payment, account, empty/error/success'});await context.close();
}
await browser.close();fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
