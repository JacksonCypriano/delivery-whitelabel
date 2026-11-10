// @vitest-environment jsdom
import {afterEach,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,cleanup,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {CommercialInbox} from './CommercialInbox';
import {request} from '../../api/client';
vi.mock('../../api/client',()=>({request:vi.fn(async()=>({detail:'Mensagem enviada pelo painel.'}))}));
vi.mock('../../hooks/useQuery',()=>({useQuery:()=>({data:{control:{human_send_enabled:true},pilot:{pending_count:1},conversations:[{id:2,name:'Lead',phone:'5511999999999',stage:'new',paused:true,updated_at:'2026-11-10T12:00:00Z'}],pagination:{page:1,pages:1},selected:{id:2,phone:'5511999999999',name:'Lead',owner_id:1,stage:'new',paused:true,opted_out:false,notes:'',messages:[]}},loading:false,reload:vi.fn()})}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('sends a human message to the selected conversation using the scoped API',async()=>{
 render(<MemoryRouter><CommercialInbox/></MemoryRouter>);
 fireEvent.click(screen.getByRole('button',{name:/Lead/}));
 fireEvent.change(screen.getByLabelText('Responder pelo painel'),{target:{value:'Olá, sou da equipe.'}});
 fireEvent.click(screen.getByRole('button',{name:'Enviar no WhatsApp'}));
 await waitFor(()=>expect(request).toHaveBeenCalledWith('commercial/',expect.objectContaining({method:'POST',body:JSON.stringify({action:'send_human',conversation:2,text:'Olá, sou da equipe.'})})));
});
