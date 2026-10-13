/** Source detail remains on the order; this is the primary sales channel. */
export function ChannelBand({order}:{order:any}) {
 const channel=['ifood','99food'].includes(order.channel || order.source) ? (order.channel || order.source) : 'vemdedelivery';
 const label=channel==='ifood'?'iFood':channel==='99food'?'99Food':'VemDeDelivery';
 const waiting=['pending','sending','awaiting','uncertain'].includes(order.sync_state);
 const cancellationWaiting = Boolean(order.cancellation_pending);
 const minutes = order.cancellation_requested_at ? Math.max(0, Math.floor((Date.now()-new Date(order.cancellation_requested_at).getTime())/60000)) : null;
 return <><div className={`channel-band channel-${channel}`} data-channel={channel}><strong>{label}</strong>{order.channel_simulated?<span>SIMULAÇÃO</span>:order.channel_test?<span>TESTE</span>:null}</div>
 {order.external_id&&<small className="channel-id">Pedido externo: {order.external_display_id||order.external_id}{order.external_display_id&&<span title={order.external_id}> · {order.external_id}</span>}</small>}
 {order.platform_notes&&<p className="operation-note">{order.platform_notes}</p>}
 {order.prepare_after&&<small>Preparar a partir de {new Date(order.prepare_after).toLocaleString('pt-BR')}</small>}
 {order.scheduled_until&&<small>Janela até {new Date(order.scheduled_until).toLocaleString('pt-BR')}</small>}
 {cancellationWaiting&&<p className="channel-notice cancellation-waiting" role="status"><strong>Aguardando cancelamento</strong> · {minutes===null?'solicitação em processamento':`solicitado há ${minutes} min`}. Não preparar nem despachar até a resposta da plataforma.{order.sync_state==='uncertain'&&' Envio sem confirmação: confira no portal; não reenvie.'}{minutes!==null&&minutes>=10&&' Solicitação demorada: verifique o estado no portal.'}</p>}
 {waiting&&!cancellationWaiting&&<p className="channel-notice" role="status">{order.sync_state==='uncertain'?'Envio sem confirmação. Confira na plataforma; não reenvie.':'Aguardando confirmação da plataforma…'}</p>}
 {order.cancellation_error&&!cancellationWaiting&&<p className="channel-notice cancellation-rejected" role="alert"><strong>Cancelamento não confirmado:</strong> {order.cancellation_error} O pedido permanece na operação.</p>}
 {order.sync_error&&!cancellationWaiting&&!order.cancellation_error&&<p className="channel-notice" role="alert">{order.sync_error}</p>}
 {order.channel_warning&&<p className="channel-notice">{order.channel_warning}</p>}</>;
}
