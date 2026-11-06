/** Browser-only QA with mocked local HTTP. No marketplace access or credentials.
 * Start Vite on 127.0.0.1:5178. Install playwright in an isolated tooling folder,
 * then set PLAYWRIGHT_MODULE to its absolute index.mjs (or install in frontend).
 */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true});
const base='http://127.0.0.1:5178';
const statuses=['pending','confirmed','preparing','ready','ready_for_pickup','out_for_delivery'];
const cards=Array.from({length:18},(_,i)=>({id:i+1,source:['manual','ifood','99food'][i%3],channel:['vemdedelivery','ifood','99food'][i%3],channel_label:['VemDeDelivery','iFood','99Food'][i%3],external_id:i%3?`SIM-EXTERNO-${i}`:null,channel_simulated:i%3!==0,status:statuses[Math.floor(i/3)],status_label:statuses[Math.floor(i/3)],created_at:new Date().toISOString(),status_updated_at:new Date().toISOString(),customer_name:`Cliente de teste ${i}`,delivery_type:'delivery',delivery_label:'Entrega',payment:{label:'Pagamento de teste'},total:'49.90',items:[{id:i+1,name:'Lanche com adicionais',quantity:1,notes:'Sem cebola',combination_details:{customizations:[{option_name:'Queijo extra'}]}}],allowed_transitions:[]}));
await fs.mkdir('output/marketplace-browser',{recursive:true});
try{
 for(const width of [390,768,1920,2560])for(const route of ['operacao','cozinha']){
  const page=await browser.newPage({viewport:{width,height:1080}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/merchant/**',async r=>{
   const path=new URL(r.request().url()).pathname;
   const data=path.endsWith('/session/')?{authenticated:true}:path.endsWith('/dashboard/')?{store:'Loja fictícia',resources:[]}:path.endsWith('/kitchen/')?{orders:cards.filter(o=>['pending','confirmed','preparing','ready','ready_for_pickup'].includes(o.status)&&(o.status!=='pending'||o.source!=='manual')),notification_settings:{}}:{columns:statuses.map(status=>({status,label:status,orders:cards.filter(o=>o.status===status)})),finished:[],notification_settings:{}};
   await r.fulfill({json:data});
  });
  await page.goto(`${base}/painel/${route}`);
  await page.locator('.channel-ifood').first().waitFor();
  assert.equal(await page.locator('.channel-99food').count()>0,true);
  assert.equal(await page.locator('.channel-vemdedelivery').count()>0,true);
  assert.equal(await page.locator('article').evaluateAll(rows=>rows.every(r=>r.querySelector('.channel-band'))),true);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),true,`${route} ${width}: page overflow`);
  await page.getByRole('button',{name:'Tela cheia',exact:true}).click();
  await page.waitForFunction(()=>!!document.fullscreenElement);
  assert.equal(await page.locator('.monitor-screen .channel-ifood').count()>0,true);
  await page.screenshot({path:`output/marketplace-browser/${route}-${width}-fullscreen.png`});
  await page.getByRole('button',{name:'Sair da tela cheia',exact:true}).click();
  await page.waitForFunction(()=>!document.fullscreenElement);
  assert.deepEqual(errors,[]);
  await page.close();console.log(`PASS ${route} ${width}px normal/fullscreen`);
 }
}finally{await browser.close();}
