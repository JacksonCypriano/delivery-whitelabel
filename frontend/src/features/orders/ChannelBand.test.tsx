// @vitest-environment jsdom
import {render,screen,cleanup} from '@testing-library/react';
import {afterEach,it,expect} from 'vitest';
import {ChannelBand} from './ChannelBand';
afterEach(cleanup);
it.each(['web','whatsapp','manual'])('mantém %s dentro de VemDeDelivery',source=>{const {container}=render(<ChannelBand order={{source}}/>);expect(screen.getByText('VemDeDelivery')).toBeTruthy();expect(container.querySelector('.channel-vemdedelivery')).toBeTruthy();});
it.each([['ifood','iFood'],['99food','99Food']])('identifica %s e o número externo', (source,label)=>{const {container}=render(<ChannelBand order={{source,external_id:'externo-123',channel_simulated:true}}/>);expect(screen.getByText(label)).toBeTruthy();expect(screen.getByText(/externo-123/)).toBeTruthy();expect(screen.getByText('SIMULAÇÃO')).toBeTruthy();expect(container.querySelector(`[data-channel="${source}"]`)).toBeTruthy();});
it('informa comando pendente e erro sem alegar sucesso',()=>{render(<ChannelBand order={{source:'ifood',sync_state:'uncertain',sync_error:'Aguardando conciliação'}}/>);expect(screen.getByRole('status').textContent).toContain('não reenvie');expect(screen.getByRole('alert').textContent).toContain('conciliação');});
