// @vitest-environment jsdom
import {render,screen,cleanup,fireEvent,waitFor} from '@testing-library/react';
import {afterEach,it,expect,vi} from 'vitest';
import {Sales} from './Sales';
import {request} from '../../api/client';
vi.mock('../../api/client',()=>({request:vi.fn().mockResolvedValue({})}));
vi.mock('../../hooks/useQuery',()=>({useQuery:()=>({loading:false,reload:vi.fn(),data:{settings:{scheduling_enabled:false,recovery_enabled:false,lead_minutes:60},messages:[],feedback:[{id:3,order_id:2,rating:1,comment:'Pedido frio'}]}})}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('starts disabled and sends explicit checkbox choice',async()=>{render(<Sales/>);const box=screen.getByLabelText('Recuperar carrinhos') as HTMLInputElement;expect(box.checked).toBe(false);fireEvent.click(box);fireEvent.click(screen.getByText('Salvar configurações'));await waitFor(()=>expect(request).toHaveBeenCalled());expect(JSON.parse((vi.mocked(request).mock.calls[0][1] as any).body).recovery_enabled).toBe(true);});
it('allows handling a poor review',async()=>{render(<Sales/>);expect(screen.getByText('Pedido frio')).toBeTruthy();fireEvent.click(screen.getByText('Marcar como tratada'));await waitFor(()=>expect(request).toHaveBeenCalled());expect(JSON.parse((vi.mocked(request).mock.calls[0][1] as any).body)).toEqual({handled_id:3});});
