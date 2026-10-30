// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { PublicApp } from './PublicApp';
import { ProductDialog, CouponPreview, DeliveryEstimate, requestJSON } from './Commerce';
const product={id:1,name:'Pizza de teste',slug:'pizza',description:'Massa artesanal',price:'40',original_price:'45',sale_price:'40',half_enabled:true,available:true,min_qty:1,max_qty:5,images:[],image:'',category_id:1};
const data:any={page:'catalog',heading:'Cardápio',year:2026,csrf:'csrf',home_url:'/',messages:[],user:{authenticated:false},store:{name:'Loja Teste',slug:'teste',cart_count:2,brand:{dark_mode_enabled:true},hours:[],accepts_delivery:true,accepts_pickup:true},props:{categories:[{id:1,name:'Pizzas',products:[product]}]}};
afterEach(()=>{cleanup();localStorage.clear();vi.unstubAllGlobals();});
describe('design system da loja',()=>{
 it('persiste o tema e reaplica no carrinho, sem duplicar controles',()=>{
  const {unmount}=render(<PublicApp data={data}/>);
  expect(screen.getAllByRole('button',{name:'Usar tema escuro'})).toHaveLength(1);
  fireEvent.click(screen.getByRole('button',{name:'Usar tema escuro'}));
  expect(localStorage.getItem('theme')).toBe('dark');expect(document.documentElement.dataset.storeTheme).toBe('dark');
  unmount();render(<PublicApp data={{...data,page:'cart',props:{items:[]}}}/>);
  expect(screen.getByRole('button',{name:'Usar tema claro'})).toBeTruthy();
  expect(screen.getByRole('heading',{name:'Seu carrinho está vazio.'})).toBeTruthy();
 });
 it('filtra o catálogo pela busca do cabeçalho e limpa a busca vazia',()=>{
  render(<PublicApp data={data}/>);
  expect(screen.getAllByRole('searchbox')).toHaveLength(1);
  fireEvent.change(screen.getByRole('searchbox'),{target:{value:'inexistente'}});
  expect(screen.getByText('Nenhum produto encontrado')).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Limpar busca'}));
  expect(screen.getByRole('link',{name:'Pizza de teste'})).toBeTruthy();
 });
 it('ignora preferência escura quando desabilitada pelo lojista',()=>{
  localStorage.setItem('theme','dark');render(<PublicApp data={{...data,store:{...data.store,brand:{dark_mode_enabled:false}}}}/>);
  expect(screen.queryByRole('button',{name:'Usar tema claro'})).toBeNull();expect(document.documentElement.dataset.storeTheme).toBe('light');
 });
 it('atualiza contador e totais com a resposta oficial do carrinho',async()=>{
  const item={id:2,name:'Pizza',price:'40',total:'80',quantity:2,notes:'',combination_details:{},min_qty:1,max_qty:5};
  const cart={...data,page:'cart',props:{items:[item],subtotal:'80',total:'80',can_checkout:true}};
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({...cart,store:{...data.store,cart_count:3},props:{...cart.props,items:[{...item,quantity:3,total:'120'}],subtotal:'120',total:'120'}})})));
  render(<PublicApp data={cart}/>);fireEvent.change(screen.getByLabelText('Quantidade'),{target:{value:'3'}});fireEvent.click(screen.getByRole('button',{name:'Atualizar quantidade'}));
  await waitFor(()=>expect(screen.getByRole('link',{name:'Carrinho, 3 itens'})).toBeTruthy());
  expect(screen.getAllByText('R$ 120,00').length).toBeGreaterThan(0);
 });
 it('não oferece avanço quando o backend bloqueia o checkout',()=>{
  render(<PublicApp data={{...data,page:'cart',props:{items:[{id:1,name:'Pizza',quantity:1,price:'40',total:'40',notes:'',min_qty:1,max_qty:5}],can_checkout:false}}}/>);
  expect(screen.queryByRole('link',{name:/Escolher endereço/})).toBeNull();
 });
 it('exibe erro de opções e permite tentar novamente; impede quantidade inválida',async()=>{
  HTMLDialogElement.prototype.showModal=function(){this.setAttribute("open","");};HTMLDialogElement.prototype.close=function(){this.removeAttribute("open");};
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,json:async()=>({error:'Opções indisponíveis'})})));
  render(<ProductDialog data={data} product={product} products={[product]} close={()=>{}}/>);
  await waitFor(()=>expect(screen.getByText('Opções indisponíveis')).toBeTruthy());
  expect(screen.getByRole('button',{name:'Tentar novamente'})).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Quantidade'),{target:{value:'0'}});
  expect((screen.getByRole('button',{name:'Adicionar ao carrinho'}) as HTMLButtonElement).disabled).toBe(true);
 });
 it('salva observações no formato de formulário esperado pelo backend',async()=>{
  const fetchMock=vi.fn(async()=>({ok:true,json:async()=>({success:true})}));vi.stubGlobal('fetch',fetchMock);
  await requestJSON('/checkout/update_notes/1/',data,new URLSearchParams({notes:'Sem cebola'}));
  const args:any=fetchMock.mock.calls[0];expect(args[1].headers['Content-Type']).toContain('application/x-www-form-urlencoded');expect(args[1].body).toBe('notes=Sem+cebola');expect(args[1].headers['X-CSRFToken']).toBe('csrf');
 });
 it('consulta taxa sem recalcular a regra do backend',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({available:true,fee_display:'R$ 7,00'})})));
  render(<DeliveryEstimate data={data}/>);fireEvent.click(screen.getByText('Consultar entrega'));
  fireEvent.change(screen.getByLabelText('Cidade'),{target:{value:'Itapevi'}});fireEvent.change(screen.getByLabelText('Bairro'),{target:{value:'Centro'}});
  fireEvent.click(screen.getByRole('button',{name:'Consultar taxa'}));await waitFor(()=>expect(screen.getByRole('status').textContent).toContain('R$ 7,00'));
 });
 it('invalida prévia do cupom quando a taxa muda',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({valid:true,discount:'10',final_total:'97',message:'Cupom aplicado.'})})));
  const {rerender}=render(<CouponPreview data={{...data,props:{subtotal:'100'}}} fee={{fee:7}}/>);
  fireEvent.change(screen.getByLabelText('Cupom'),{target:{value:'teste'}});fireEvent.click(screen.getByRole('button',{name:'Aplicar cupom'}));await waitFor(()=>expect(screen.getByRole('status').textContent).toContain('97,00'));
  rerender(<CouponPreview data={{...data,props:{subtotal:'100'}}} fee={{fee:9}}/>);expect(screen.queryByRole('status')).toBeNull();
 });

});
