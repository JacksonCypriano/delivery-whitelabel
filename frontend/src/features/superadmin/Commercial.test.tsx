// @vitest-environment jsdom
import {afterEach,it,expect,vi} from 'vitest';
import {render,screen,cleanup,fireEvent} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {Commercial} from './Commercial';

vi.mock('../../api/client',()=>({request:vi.fn(async()=>({detail:'OK'}))}));
vi.mock('../../hooks/useQuery',()=>({useQuery:()=>({data:{control:{instance:'sales',enabled:false,server_enabled:false},catalog:{valid:false,fingerprint:'x',data:{plans:[],services:[],payments:[],terms:''}},published:false,articles:[],metrics:[],events:[],conversations:[],pagination:{page:1,pages:1},selected:null},loading:false,reload:vi.fn()})}));

afterEach(()=>{cleanup();vi.clearAllMocks();});

it('separates commercial configuration and inbox without publishing invalid prices',()=>{
  render(<MemoryRouter><Commercial/></MemoryRouter>);

  // The commercial configuration is organized into dedicated tabs.
  fireEvent.click(screen.getByRole('tab',{name:'Catálogo'}));
  expect(screen.getByRole('tab',{name:'Catálogo'}).getAttribute('aria-selected')).toBe('true');
  expect((screen.getByRole('button',{name:'Aprovar versão atual para o agente'}) as HTMLButtonElement).disabled).toBe(true);

  fireEvent.click(screen.getByRole('tab',{name:'Atendimento e atividade'}));
  expect(screen.getByRole('tab',{name:'Atendimento e atividade'}).getAttribute('aria-selected')).toBe('true');
  expect(screen.getByRole('link',{name:'Abrir inbox comercial'}).getAttribute('href')).toContain('comercial/inbox');
});
