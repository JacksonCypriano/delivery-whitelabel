// @vitest-environment jsdom
import {afterEach,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,cleanup,waitFor} from '@testing-library/react';
import {Commercial} from './Commercial';
import {request} from '../../api/client';
vi.mock('../../api/client',()=>({request:vi.fn(async()=>({detail:'Conversa atualizada.'}))}));
vi.mock('../../hooks/useQuery',()=>({useQuery:()=>({data:{control:{instance:'sales',enabled:false,server_enabled:false},catalog:{valid:false,fingerprint:'x',data:{plans:[],services:[],payments:[],terms:""}},published:false,articles:[],metrics:[],events:[],conversations:[],pagination:{page:1,pages:1},selected:{id:1,phone:'5511999999999',stage:'new',paused:true,opted_out:true,messages:[]}},loading:false,reload:vi.fn()})}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('blocks publication of inconsistent catalog and opt-out resumption',()=>{
 render(<Commercial/>);
 expect((screen.getByRole('button',{name:'Aprovar versão atual para o agente'}) as HTMLButtonElement).disabled).toBe(true);
 expect((screen.getByRole('button',{name:'Devolver à IA'}) as HTMLButtonElement).disabled).toBe(true);
});
it('uses a scoped takeover request',async()=>{
 render(<Commercial/>);fireEvent.click(screen.getByRole('button',{name:'Assumir atendimento'}));
 await waitFor(()=>expect(request).toHaveBeenCalledWith('commercial/',expect.objectContaining({method:'POST',body:JSON.stringify({action:'takeover',conversation:1})})));
});
