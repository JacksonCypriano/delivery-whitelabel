// @vitest-environment jsdom
import {render,screen,cleanup,fireEvent,waitFor} from '@testing-library/react';
import {afterEach,it,expect,vi} from 'vitest';
import {Conversations} from '../whatsapp/Conversations';
import {Logistics} from './Logistics';
import {CRM} from './CRM';
import {request} from '../../api/client';
vi.mock('../../api/client',()=>({request:vi.fn().mockResolvedValue({})}));
vi.mock('./OrdersBoard',()=>({useOrderRealtime:()=> 'online'}));
vi.mock('../../hooks/useQuery',()=>({useQuery:()=>({loading:false,reload:vi.fn(),data:{conversations:[{id:1,phone:'11999999999',paused:true,reason:'human',checkouts:[],entries:[]}],couriers:[],orders:[],history:[],integrations:[{name:'iFood',status:'Acesso oficial e credenciais pendentes'}],customers:[],loyalty:{enabled:false,reais_per_point:'1',reward_points:100,reward_value:'10'},campaigns:[],funnel:[],origins:[]}})}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('resumes conversation explicitly',async()=>{render(<Conversations/>);fireEvent.click(screen.getByText('Retomar agente'));await waitFor(()=>expect(request).toHaveBeenCalled());expect(JSON.parse((vi.mocked(request).mock.calls[0][1] as any).body)).toEqual({id:1,action:'resume'});});
it('external integration is visibly pending',()=>{render(<Logistics/>);expect(screen.getByText(/iFood: Acesso oficial/)).toBeTruthy();expect(screen.getByText('Nenhuma entrega aguardando operação.')).toBeTruthy();});
it('loyalty starts disabled',()=>{render(<CRM/>);expect((screen.getByLabelText('Habilitar para novas compras') as HTMLInputElement).checked).toBe(false);});
