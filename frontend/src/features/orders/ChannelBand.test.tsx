// @vitest-environment jsdom
import {render,screen,cleanup} from '@testing-library/react';
import {afterEach,it,expect} from 'vitest';
import {ChannelBand} from './ChannelBand';
afterEach(cleanup);
it.each(['web','whatsapp','manual'])('mantém %s dentro de VemDeDelivery',source=>{const {container}=render(<ChannelBand order={{source}}/>);expect(screen.getByText('VemDeDelivery')).toBeTruthy();expect(container.querySelector('.channel-vemdedelivery')).toBeTruthy();});
it.each([['ifood','iFood'],['99food','99Food']])('identifica %s e o número externo', (source,label)=>{const {container}=render(<ChannelBand order={{source,external_id:'externo-123',channel_simulated:true}}/>);expect(screen.getByText(label)).toBeTruthy();expect(screen.getByText(/externo-123/)).toBeTruthy();expect(screen.getByText('SIMULAÇÃO')).toBeTruthy();expect(container.querySelector(`[data-channel="${source}"]`)).toBeTruthy();});
it('informa comando pendente e erro sem alegar sucesso',()=>{render(<ChannelBand order={{source:'ifood',sync_state:'uncertain',sync_error:'Aguardando conciliação'}}/>);expect(screen.getByRole('status').textContent).toContain('não reenvie');expect(screen.getByRole('alert').textContent).toContain('conciliação');});
it('destaca cancelamento pendente e o tempo sem considerar o pedido cancelado',()=>{
 render(<ChannelBand order={{source:'ifood',cancellation_pending:true,cancellation_requested_at:new Date(Date.now()-120000).toISOString(),sync_state:'awaiting'}}/>);
 expect(screen.getByRole('status').textContent).toContain('Aguardando cancelamento');
 expect(screen.getByRole('status').textContent).toContain('2 min');
});
it('exibe a recusa de cancelamento na etapa original',()=>{
 render(<ChannelBand order={{source:'ifood',cancellation_pending:false,cancellation_error:'iFood recusou o cancelamento.'}}/>);
 expect(screen.getByRole('alert').textContent).toContain('Cancelamento não confirmado');
});

it('pedido 99Food pendente de entrega mostra orientação específica e não declara entrega',()=>{
 render(<ChannelBand order={{source:'99food',status:'out_for_delivery',sync_state:'awaiting',sync_target:'delivered',food99_delivery_pending:true,delivery_by:'MERCHANT'}}/>);
 const notice=screen.getByRole('status');expect(notice.textContent).toContain('Entrega pendente na 99Food');expect(notice.textContent).toContain('nem reenvie');expect(notice.textContent).not.toContain('entrega concluída');
});
it('iFood e outros comandos 99Food não recebem aviso de código de entrega',()=>{
 const {rerender}=render(<ChannelBand order={{source:'ifood',sync_state:'awaiting',sync_target:'delivered'}}/>);
 expect(screen.getByRole('status').textContent).toContain('Aguardando confirmação');
 rerender(<ChannelBand order={{source:'99food',sync_state:'awaiting',sync_target:'ready'}}/>);
 expect(screen.getByRole('status').textContent).toContain('Aguardando confirmação');
});

it('marketplace com motorista da plataforma não orienta operador a digitar código',()=>{
 render(<ChannelBand order={{source:'99food',delivery_type:'delivery',delivery_by:'PLATFORM',sync_state:'awaiting',sync_target:'ready'}}/>);
 expect(screen.getByText(/motorista confirma no aplicativo da plataforma/)).toBeTruthy();
 expect(screen.queryByText(/motoboy deve obter/)).toBeNull();
});
it('entrega merchant orienta motoboy no fluxo oficial, não o operador',()=>{
 render(<ChannelBand order={{source:'99food',delivery_type:'delivery',delivery_by:'MERCHANT',sync_state:'awaiting',sync_target:'delivered'}}/>);
 expect(screen.getByRole('status').textContent).toContain('motoboy');
 expect(screen.getByRole('status').textContent).toContain('Não invente códigos');
});
