// @vitest-environment jsdom
import {render,screen,cleanup} from '@testing-library/react';
import {afterEach,it,expect,vi} from 'vitest';
import {Kitchen} from './Kitchen';
vi.mock('./OrdersBoard',()=>({useOrderRealtime:()=> 'online'}));
vi.mock('../../hooks/useQuery',()=>({useQuery:()=>({loading:false,reload:vi.fn(),data:{orders:[{id:5,status:'preparing',delivery_label:'Retirada',created_at:new Date().toISOString(),status_updated_at:new Date().toISOString(),late:true,items:[{id:1,name:'Pizza',quantity:2,notes:'Sem queijo',combination_details:{}}],allowed_transitions:[{value:'ready_for_pickup',label:'Pronto para retirada'}]},{id:22,status:'confirmed',cancellation_pending:true,cancellation_requested_at:new Date().toISOString(),source:'ifood',channel:'ifood',delivery_label:'Entrega',customer_name:'Cliente cancelamento',created_at:new Date().toISOString(),status_updated_at:new Date().toISOString(),items:[],allowed_transitions:[]}],notification_settings:{}}})}));
afterEach(cleanup);
it('destaca observações e oferece ação específica de retirada',()=>{render(<Kitchen/>);expect(screen.getByText('Sem queijo')).toBeTruthy();expect(screen.getByText('Prazo de preparo excedido')).toBeTruthy();expect(screen.getByRole('button',{name:/Pronto para retirada/i})).toBeTruthy();expect(screen.queryByRole('button',{name:/saiu para entrega/i})).toBeNull();});

it('isola pedidos com cancelamento pendente no KDS',()=>{const {container}=render(<Kitchen/>);const lane=container.querySelector('.kitchen-cancel-column');expect(lane?.textContent).toContain('Aguardando cancelamento');expect(lane?.textContent).toContain('#22');expect(container.querySelectorAll('.kitchen-card.cancel-awaiting')).toHaveLength(1);expect(container.querySelectorAll('.kitchen-card')).toHaveLength(2);});
