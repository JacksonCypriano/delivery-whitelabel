// Isolated fixture server: never submits orders or contacts a real backend.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const fixture=JSON.parse(fs.readFileSync(new URL('./fixtures/catalog.json',import.meta.url)));
const staticRoot=process.env.VISUAL_STATIC_ROOT || path.join(root,'static/public');
const manifest=JSON.parse(fs.readFileSync(path.join(staticRoot,'.vite/manifest.json')))['src/public/client.tsx'];
const base=structuredClone(fixture);
base.assets={js:'/static/public/'+manifest.file,css:['/static/css/customer-brand.css',...(manifest.css||[]).map(x=>'/static/public/'+x)]};
base.csrf='visual-fixture-csrf';base.store.whatsapp='';base.store.cart_count=2;
const product=base.props.categories[0].products[0];
let cart={...structuredClone(base),page:'cart',heading:'Seu carrinho',props:{items:[{id:1,name:product.name,quantity:2,price:product.price,total:String(Number(product.price)*2),image:product.image,notes:'Sem cebola',combination_details:{},min_qty:1,max_qty:9}],subtotal:String(Number(product.price)*2),total:String(Number(product.price)*2),delivery_fee_display:'A confirmar',can_checkout:true,checkout_mode_hint:'Escolha entrega ou retirada na próxima etapa.'}};
function dataFor(url){
 const d=structuredClone(base);const pathname=new URL(url,'http://localhost').pathname;
 if(pathname==='/checkout/cart/')return structuredClone(cart);
 if(pathname==='/empty-cart/'){d.page='cart';d.heading='Seu carrinho';d.store.cart_count=0;d.props={...cart.props,items:[]};}
 else if(pathname==='/checkout/checkout/'){d.page='checkout';d.heading='Finalizar pedido';d.props={cart_items:[{name:product.name,quantity:cart.store.cart_count,line_total:cart.props.total}],subtotal:cart.props.total,customer_addresses:[],global_delivery_location:{},default_address:null,initial_full_name:'',initial_phone:'',checkout_token:'fixture-checkout',online_payment_available:true,store_address:'Rua de Teste, 123',scheduling_enabled:true};}
 else if(['/review/','/payment/'].includes(pathname)){d.page=pathname==='/review/'?'review':'payment';d.heading='Revise seu pedido';d.props={order:{id:42,public_token:'fixture-order',payment_flow:pathname==='/payment/'?'online':'in_person',store_name:'Loja de teste',items:[{id:1,name:product.name,quantity:2,total:cart.props.total,details:[]}],total:cart.props.total,subtotal:cart.props.total,delivery_fee:'0',payment_label:'Pix',delivery_label:'Retirada'},payment:pathname==='/payment/'?{status:'PENDING',label:'Aguardando pagamento',checkout_url:'#fixture-payment'}:null};}
 else if(pathname==='/success/'){d.page='success';d.heading='Pedido registrado';d.props={message:'Acompanhe a confirmação da loja.'};}
 else if(pathname==='/conta/entrar/'){d.page='login';d.heading='Entrar na minha conta';d.props={form:{errors:[],fields:[{name:'email',label:'E-mail',kind:'email',value:'',required:true,errors:[]},{name:'password',label:'Senha',kind:'password',value:'',required:true,errors:[]}]}};}
 else if(pathname==='/conta/enderecos/'){d.page='addresses';d.heading='Meus endereços';d.props={addresses:[]};}
 else if(pathname==='/conta/pedidos/'){d.page='orders';d.heading='Meus pedidos';d.props={orders:[]};}
 else if(pathname==='/unavailable/'){d.props.deep_link_unavailable=true;}
 else if(pathname==='/empty/'){d.props.categories=[];}
 else if(pathname.startsWith('/produto/'))d.props.open_product_slug=product.slug;
 return d;
}
export const server=http.createServer(async(req,res)=>{
 try{
 const url=new URL(req.url,'http://localhost');
 if(url.pathname.startsWith('/static/')||url.pathname.startsWith('/media/')){
  const p=url.pathname.startsWith('/static/public/')?path.resolve(staticRoot,'.'+url.pathname.slice('/static/public'.length)):url.pathname.startsWith('/media/')?path.resolve(path.dirname(fileURLToPath(import.meta.url)),'fixtures/assets','.'+url.pathname):path.resolve(root,'.'+url.pathname);
  if(!p.startsWith(root+path.sep)&&!p.startsWith(path.resolve(staticRoot)+path.sep)){res.writeHead(403).end();return;}
  const mime={'.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp','.woff2':'font/woff2'}[path.extname(p)]||'application/octet-stream';
  res.writeHead(200,{'Content-Type':mime});fs.createReadStream(p).on('error',()=>res.end()).pipe(res);return;
 }
 if(url.pathname.includes('/customizations/')){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({groups:[{id:1,name:'Borda',min_options:0,max_options:1,apply_to:'whole',options:[{id:10,name:'Catupiry',price:'6.00'}]},{id:2,name:'Adicionais',min_options:0,max_options:3,apply_to:'half',options:[{id:20,name:'Queijo extra',price:'4.00'}]}]}));return;}
 if(url.pathname==='/api/delivery-fee/'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({fee_display:'R$ 5,00',available:true,fee:5}));return;}
 if(url.pathname==='/api/cupons/validar/'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({valid:true,discount:'10.00',final_total:'120.80',message:'Cupom aplicado.'}));return;}
 if(req.method==='POST'){
  let raw='';for await(const chunk of req)raw+=chunk;
  if(url.pathname.startsWith('/checkout/update_quantity/')){const q=JSON.parse(raw).quantity;cart.props.items[0].quantity=q;cart.props.items[0].total=String(q*Number(product.price));cart.props.subtotal=cart.props.total=cart.props.items[0].total;cart.store.cart_count=q;}
  if(url.pathname.startsWith('/checkout/remove/')){cart.props.items=[];cart.store.cart_count=0;}
  res.setHeader('Content-Type','application/json');res.end(JSON.stringify({success:true}));return;
 }
 const data=dataFor(req.url);
 if(req.headers.accept==='application/json'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify(data));return;}
 const rendered=await fetch(process.env.VISUAL_SSR_URL||'http://127.0.0.1:3001/render',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
 res.writeHead(rendered.status,{'Content-Type':'text/html; charset=utf-8'});res.end(await rendered.text());
 }catch(e){res.writeHead(500).end(e.message);}
});
server.listen(Number(process.env.VISUAL_PORT||4173),'127.0.0.1',()=>console.log('Visual fixture server ready'));
