// @vitest-environment jsdom
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {Checkout,Review,Catalog,requestJSON} from './Commerce';
const data:any={csrf:'csrf-token',store:{accepts_delivery:true,accepts_pickup:true,cart_count:0},props:{categories:[],cart_items:[],subtotal:'20',customer_addresses:[],online_payment_available:true,checkout_token:'cart-token'}};
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
describe('jornada pública React',()=>{
 it('preserva token, CSRF e regras de pagamento por modalidade',()=>{
  vi.stubGlobal('fetch',vi.fn(()=>Promise.resolve({ok:true,json:()=>Promise.resolve({})})));
  const {container}=render(<Checkout data={data}/>);
  expect(container.querySelector('input[name=checkout_token]')?.getAttribute('value')).toBe('cart-token');
  expect(container.querySelector('input[name=csrfmiddlewaretoken]')?.getAttribute('value')).toBe('csrf-token');
  fireEvent.change(screen.getByLabelText('Quando pagar'),{target:{value:'online'}});
  expect(screen.queryByRole('option',{name:'Dinheiro'})).toBeNull();
  expect(screen.getByRole('option',{name:'Pix'})).toBeTruthy();
 });
 it('não oferece confirmação de pedido online ainda não pago',()=>{
  render(<Review data={{...data,props:{order:{id:1,public_token:'token',payment_flow:'online',total:'20'},payment:{status:'PENDING',label:'Pendente',checkout_url:'https://example.com/pay'}}}}/>);
  expect(screen.queryByRole('button',{name:'Confirmar e enviar pedido pelo WhatsApp'})).toBeNull();
  expect(screen.getByText('Continuar pagamento no Asaas').getAttribute('href')).toBe('https://example.com/pay');
 });
 it('exibe confirmação oficial e usa POST quando pago',()=>{
  const {container}=render(<Review data={{...data,props:{order:{id:1,public_token:'token',payment_flow:'online',total:'20'},payment:{status:'PAID',confirmation_code:'OK123'}}}}/>);
  expect(screen.getByText('OK123')).toBeTruthy();
  expect(container.querySelector('form[action="/pedido/token/whatsapp/"]')?.getAttribute('method')).toBe('post');
 });
 it('envia apenas no mesmo domínio com CSRF e preserva erro do backend',async()=>{
  const fetchMock=vi.fn((_url:any,_options:any)=>Promise.resolve({ok:false,json:()=>Promise.resolve({error:'Estoque insuficiente'})}));vi.stubGlobal('fetch',fetchMock);
  await expect(requestJSON('/checkout/add/',data,{quantity:2})).rejects.toThrow('Estoque insuficiente');
  expect(fetchMock.mock.calls[0][1].headers['X-CSRFToken']).toBe('csrf-token');
 });
});
