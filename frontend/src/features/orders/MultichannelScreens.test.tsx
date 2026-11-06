// @vitest-environment jsdom
import {render,screen,cleanup,fireEvent,waitFor} from '@testing-library/react';
import {afterEach,beforeAll,it,expect,vi} from 'vitest';
import {MemoryRouter} from 'react-router-dom';
import {OrdersBoard} from './OrdersBoard';
import {Kitchen} from './Kitchen';
const cards=['manual','ifood','99food'].map((source,n)=>({id:n+1,source,channel:source==='manual'?'vemdedelivery':source,external_id:n?`external-${n}`:null,status:'pending',customer_name:`Cliente ${n}`,created_at:new Date().toISOString(),status_updated_at:new Date().toISOString(),delivery_label:'Entrega',payment:{label:'Marketplace'},items:[{id:n,name:'Lanche',quantity:1,notes:'Sem cebola'}],total:'35',allowed_transitions:n?[{value:'confirmed',label:'Confirmado'}]:[]}));
vi.mock('../../hooks/useQuery',()=>({useQuery:()=>({data:{orders:cards.slice(1),columns:[{status:'pending',label:'Novos',orders:cards}],finished:[],notification_settings:{}},reload:vi.fn(),loading:false})}));
beforeAll(()=>{vi.stubGlobal('WebSocket',class{close(){}});});
afterEach(()=>{cleanup();vi.restoreAllMocks();});
it.each([['pedidos',OrdersBoard],['cozinha',Kitchen]] as const)('mostra plataformas e mantém conteúdo em fullscreen na tela %s',async(_,Component)=>{
 Object.defineProperty(document,'fullscreenElement',{configurable:true,get:()=>full});let full:Element|null=null;
 Element.prototype.requestFullscreen=vi.fn(async function(this:Element){full=this;document.dispatchEvent(new Event('fullscreenchange'));});
 document.exitFullscreen=vi.fn(async()=>{full=null;document.dispatchEvent(new Event('fullscreenchange'));});
 const {container}=render(<MemoryRouter><Component/></MemoryRouter>);
 expect(screen.getByText('iFood')).toBeTruthy();expect(screen.getByText('99Food')).toBeTruthy();expect(container.querySelector('.channel-ifood')).toBeTruthy();expect(container.querySelector('.channel-99food')).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Tela cheia'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Sair da tela cheia'})).toBeTruthy());
 expect(screen.getByText(/external-1/)).toBeTruthy();expect(container.querySelector('.monitor-screen .channel-ifood')).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Sair da tela cheia'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Tela cheia'})).toBeTruthy());
});
