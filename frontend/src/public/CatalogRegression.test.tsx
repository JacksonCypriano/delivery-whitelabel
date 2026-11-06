// @vitest-environment jsdom
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {PublicApp} from './PublicApp';
import {ProductDialog} from './Commerce';
const pizza={id:1,name:'Sabor A',slug:'a',price:'40',half_enabled:true,available:true,min_qty:1,max_qty:5,category_id:7};
const second={...pizza,id:2,name:'Sabor B',slug:'b',price:'50'};
const water={...pizza,id:3,name:'Água',slug:'agua',price:'5',half_enabled:false,category_id:8};
const data:any={page:'catalog',heading:'Cardápio',year:2026,csrf:'test',messages:[],user:{authenticated:false},store:{name:'Teste',slug:'teste',cart_count:0,brand:{},hours:[],whatsapp:'5511999999999'},props:{categories:[{id:7,name:'Sabores',products:[pizza,second]},{id:8,name:'Bebidas',products:[water]}]}};
const required={id:10,name:'Borda',apply_to:'whole',min_options:1,max_options:1,options:[{id:11,name:'Queijo',price:'6'}]};
let fetchMock:any;
beforeEach(()=>{
 HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
 HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};
 fetchMock=vi.fn(async(url:string)=>({ok:true,json:async()=>url.includes('/customizations/')?{groups:[]}:{success:true,cart_count:2,cart_total:'10'}}));vi.stubGlobal('fetch',fetchMock);
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();localStorage.clear();});
async function loaded(){await waitFor(()=>expect(screen.queryByText('Carregando opções…')).toBeNull());}
it.each([false,undefined,'false',0])('não autoriza meio a meio com half_enabled=%s, mesmo startHalf=true',async(flag)=>{
 render(<ProductDialog data={data} product={{...water,half_enabled:flag}} products={[pizza,water]} startHalf close={()=>{}}/>);await loaded();
 expect(screen.queryByText('Montar pizza meio a meio')).toBeNull();expect(screen.queryByText('Escolha o segundo sabor')).toBeNull();
});
it('isola sabores, adicionais, notas e quantidade ao trocar o produto',async()=>{
 const {rerender}=render(<ProductDialog data={data} product={pizza} products={[pizza,second,water]} startHalf close={()=>{}}/>);await loaded();
 fireEvent.click(screen.getByRole('button',{name:'Selecione o segundo sabor'}));fireEvent.click(screen.getByRole('option',{name:/Sabor B/}));
 fireEvent.change(screen.getByLabelText('Quantidade'),{target:{value:'3'}});
 fireEvent.change(screen.getByLabelText('Metade 1: Sabor A'),{target:{value:'Sem cebola'}});
 fireEvent.change(screen.getByLabelText('Metade 2: Sabor B'),{target:{value:'Bem assada'}});
 rerender(<ProductDialog data={data} product={water} products={[pizza,second,water]} startHalf close={()=>{}}/>);await loaded();
 expect(screen.queryByText('Escolha o segundo sabor')).toBeNull();expect((screen.getByLabelText('Quantidade') as HTMLInputElement).value).toBe('1');
 expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('');
 fireEvent.click(screen.getByRole('button',{name:'Adicionar ao carrinho'}));await waitFor(()=>expect(fetchMock.mock.calls.some((c:any)=>c[0]==='/checkout/add/')).toBe(true));
 const payload=JSON.parse(fetchMock.mock.calls.find((c:any)=>c[0]==='/checkout/add/')[1].body);expect(payload).toMatchObject({product_id:3,quantity:1,notes:'',is_half:false,customizations:[]});expect(payload.product_ids).toBeUndefined();
});
it.each(['água','adicionais','meio a meio'])('adiciona %s, fecha modal, atualiza contador/total e permanece no catálogo',async(mode)=>{
 fetchMock.mockImplementation(async(url:string)=>({ok:true,json:async()=>url.includes('/customizations/')?{groups:mode==='adicionais'?[required]:[]}:{success:true,cart_count:2,cart_total:'112'}}));
 const initialURL=window.location.href;render(<PublicApp data={data}/>);
 if(mode==='meio a meio'){
  fireEvent.click(screen.getByRole('button',{name:'Montar pizza meio a meio com Sabor A'}));await loaded();
  fireEvent.click(screen.getByRole('button',{name:'Selecione o segundo sabor'}));fireEvent.click(screen.getByRole('option',{name:/Sabor B/}));await loaded();
 }else{fireEvent.click(screen.getByRole('button',{name:mode==='água'?'Escolher Água':'Escolher Sabor A'}));await loaded();}
 if(mode==='adicionais'){
  fireEvent.click(screen.getByRole('button',{name:'Adicionar ao carrinho'}));expect(screen.getByRole('alert').textContent).toContain('obrigatórias');
  fireEvent.click(screen.getByRole('radio',{name:/Queijo/}));fireEvent.change(screen.getByLabelText('Quantidade'),{target:{value:'2'}});
  fireEvent.change(screen.getByRole('textbox'),{target:{value:'Bem assada'}});expect(within(screen.getByRole('dialog')).getByText('R$ 92,00')).toBeTruthy();
 }
 fireEvent.click(screen.getByRole('button',{name:'Adicionar ao carrinho'}));await waitFor(()=>expect(screen.queryByRole('dialog')).toBeNull());
 expect(screen.getByRole('link',{name:'Carrinho, 2 itens'})).toBeTruthy();expect(screen.getByText('R$ 112,00')).toBeTruthy();expect(window.location.href).toBe(initialURL);
 expect(screen.getByRole('link',{name:/Ver carrinho/}).getAttribute('href')).toBe('/checkout/cart/');
 const post=fetchMock.mock.calls.find((c:any)=>c[1]?.method==='POST');const body=JSON.parse(post[1].body);
 expect(post[0]).toBe(mode==='meio a meio'?'/checkout/checkout/add-half-half/':'/checkout/add/');
 if(mode==='adicionais')expect(body).toMatchObject({quantity:2,notes:'Bem assada',customizations:[{group_id:10,option_id:11}]});
});
it.each(['5511999999999',''])('expõe presença do WhatsApp para posicionamento: %s',(whatsapp)=>{
 const {container}=render(<PublicApp data={{...data,store:{...data.store,whatsapp}}}/>);
 expect(container.querySelector('.storefront')?.getAttribute('data-has-whatsapp')).toBe(String(Boolean(whatsapp)));
 expect(screen.queryByRole('link',{name:'Falar com a loja no WhatsApp'})!==null).toBe(Boolean(whatsapp));
});

it('mantém modal e contador em caso de recusa do backend',async()=>{
 fetchMock.mockImplementation(async(url:string)=>({ok:!url.includes('/checkout/add/'),json:async()=>url.includes('/customizations/')?{groups:[]}:{error:'Estoque insuficiente'}}));
 render(<PublicApp data={data}/>);fireEvent.click(screen.getByRole('button',{name:'Escolher Água'}));await loaded();
 fireEvent.click(screen.getByRole('button',{name:'Adicionar ao carrinho'}));await waitFor(()=>expect(screen.getByRole('alert').textContent).toBe('Estoque insuficiente'));
 expect(screen.getByRole('dialog')).toBeTruthy();expect(screen.getByRole('link',{name:'Carrinho, 0 itens'})).toBeTruthy();
});
