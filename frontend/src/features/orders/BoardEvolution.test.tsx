// @vitest-environment jsdom
import {afterEach,beforeAll,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,cleanup,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {OrdersBoard} from './OrdersBoard';
import {orders} from '../../api/orders';
const card={id:1,status:'pending',status_updated_at:'2026-11-05T12:00:00Z',created_at:'2026-11-05T12:00:00Z',customer_name:'Ana',delivery_type:'delivery',delivery_label:'Entrega',source:'manual',items:[],total:'20',payment:{label:'Na entrega'},allowed_transitions:[{value:'confirmed',label:'Confirmado'}]};
const done={...card,id:2,status:'delivered',customer_name:'Finalizado hoje',allowed_transitions:[]};
const data={columns:[{status:'pending',label:'Novos',orders:[card]},{status:'confirmed',label:'Confirmados',orders:[]}],finished:[],delivered:[done],all_orders:[done],notification_settings:{default_prep_minutes:30}};
vi.mock('../../api/orders',()=>({orders:{transition:vi.fn(async()=>({detail:'Status atualizado.'}))}}));
vi.mock('../../hooks/useQuery',()=>({useQuery:()=>({data,loading:false,reload:vi.fn()})}));
beforeAll(()=>{vi.stubGlobal('WebSocket',class{close(){}});HTMLDialogElement.prototype.showModal=vi.fn(function(this:HTMLDialogElement){this.setAttribute('open','');});});
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('keyboard move asks confirmation and sends the observed version',async()=>{
 render(<MemoryRouter><OrdersBoard/></MemoryRouter>);
 fireEvent.change(screen.getByLabelText('Mover pedido 1 para'),{target:{value:'confirmed'}});
 expect(orders.transition).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'Confirmar alteração'}));
 await waitFor(()=>expect(orders.transition).toHaveBeenCalledWith(1,'confirmed',expect.objectContaining({expected_status_updated_at:card.status_updated_at})));
});
it('drop outside permitted transitions never submits',()=>{
 const {container}=render(<MemoryRouter><OrdersBoard/></MemoryRouter>);
 const transfer={setData:vi.fn(),dropEffect:''};
 fireEvent.dragStart(container.querySelector('.order-card')!,{dataTransfer:transfer});
 fireEvent.drop(container.querySelector('.order-column.status-delivered')!,{dataTransfer:transfer});
 expect(orders.transition).not.toHaveBeenCalled();expect(screen.getByText(/Esta movimentação não é permitida/)).toBeTruthy();
});
it('delivered today remains accessible and Todos is a separate history view',()=>{
 const {container}=render(<MemoryRouter><OrdersBoard/></MemoryRouter>);
 expect(container.querySelector('.order-column.status-delivered')?.textContent).toContain('Finalizado hoje');
 fireEvent.click(screen.getByRole('button',{name:'Todos'}));
 expect(container.querySelector('.history-board')?.textContent).toContain('Finalizado hoje');
 expect(screen.queryByText('Ana')).toBeNull();
});
