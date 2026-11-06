// @vitest-environment jsdom
import {render,screen,fireEvent,cleanup,waitFor} from '@testing-library/react';
import {afterEach,it,expect,vi} from 'vitest';
import {Monitor} from './Monitor';
afterEach(()=>{cleanup();vi.restoreAllMocks();});
it('keeps monitor content visible if fullscreen is unavailable',async()=>{render(<Monitor><p>Pedido #1</p></Monitor>);fireEvent.click(screen.getByText('Tela cheia'));await waitFor(()=>expect(screen.getByRole('status').textContent).toContain('indisponível'));expect(screen.getByText('Pedido #1')).toBeTruthy();});
