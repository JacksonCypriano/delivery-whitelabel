// @vitest-environment jsdom
import {render,screen,cleanup} from '@testing-library/react';
import {afterEach,it,expect,vi} from 'vitest';
import {MemoryRouter} from 'react-router-dom';
import {Finance} from './Finance';
vi.mock('../../hooks/useQuery',()=>({useQuery:()=>({data:{notes:[],total:0,authorized:0,processing:0,page:1,pages:1},loading:false,reload:vi.fn()})}));
afterEach(cleanup);
it('keeps the fiscal structure with no documents and no outlet context',()=>{render(<MemoryRouter><Finance mode="notas"/></MemoryRouter>);expect(screen.getByRole('heading',{name:'Notas fiscais'})).toBeTruthy();expect(screen.getByText('0 autorizadas')).toBeTruthy();expect(screen.getByText('Nenhuma nota fiscal emitida para esta loja.')).toBeTruthy();expect(screen.getByLabelText('Registros por página')).toBeTruthy();});
