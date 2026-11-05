/** Source detail remains on the order; this is the primary sales channel. */
export function ChannelBand({order}:{order:any}) {
 const channel=['ifood','99food'].includes(order.channel || order.source) ? (order.channel || order.source) : 'vemdedelivery';
 const label=channel==='ifood'?'iFood':channel==='99food'?'99Food':'VemDeDelivery';
 const waiting=['pending','sending','awaiting','uncertain'].includes(order.sync_state);
 const cancellationWaiting = Boolean(order.cancellation_pending);
 const deliveryPending = channel==='99food' && !order.channel_simulated && (order.food99_delivery_pending || (order.sync_target==='delivered' && waiting));
 const ownCourier = order.delivery_responsibility==='merchant' || order.delivery_by==='MERCHANT';
 const platformCourier = order.delivery_responsibility==='platform' || ['PLATFORM','IFOOD'].includes(order.delivery_by);
 const minutes = order.cancellation_requested_at ? Math.max(0, Math.floor((Date.now()-new Date(order.cancellation_requested_at).getTime())/60000)) : null;
 return <><div className={`channel-band channel-${channel}`} data-channel={channel}><strong>{label}</strong>{order.channel_simulated?<span>SIMULAÇÃO</span>:order.channel_test?<span>TESTE</span>:null}</div>
 {order.external_id&&<small className="channel-id">Pedido externo: {order.external_display_id||order.external_id}{order.external_display_id&&<span title={order.external_id}> · {order.external_id}</span>}</small>}
 {order.platform_notes&&<p className="operation-note">{order.platform_notes}</p>}
 {order.prepare_after&&<small>Preparar a partir de {new Date(order.prepare_after).toLocaleString('pt-BR')}</small>}
 {order.scheduled_until&&<small>Janela até {new Date(order.scheduled_until).toLocaleString('pt-BR')}</small>}
 {cancellationWaiting&&<p className="channel-notice cancellation-waiting" role="status"><strong>Aguardando cancelamento</strong> · {minutes===null?'solicitação em processamento':`solicitado há ${minutes} min`}. Não preparar nem despachar até a resposta da plataforma.{order.sync_state==='uncertain'&&' Envio sem confirmação: confira no portal; não reenvie.'}{minutes!==null&&minutes>=10&&' Solicitação demorada: verifique o estado no portal.'}</p>}
 {deliveryPending&&<p className="channel-notice food99-delivery-pending" role="status"><strong>Entrega pendente na 99Food.</strong> O pedido continua em rota até a confirmação oficial. {ownCourier?'Na entrega própria, o motoboy deve obter a confirmação pelo procedimento oficial da 99Food; a loja apenas acompanha.':platformCourier?'A confirmação cabe ao entregador da plataforma; a loja deve acompanhar o retorno oficial.':'Confira a responsabilidade pela entrega antes de orientar qualquer confirmação.'} Não invente códigos nem reenvie a finalização.{order.sync_state==='uncertain'&&' Resultado incerto: conferência manual obrigatória.'}</p>}
 {channel!=='vemdedelivery' && order.delivery_type==='delivery' && !deliveryPending && <p className="channel-delivery-owner"><small>{ownCourier?'Entrega própria: confirmação pelo motoboy no fluxo oficial da plataforma.':platformCourier?'Entrega pela plataforma: motorista confirma no aplicativo da plataforma.':'Responsabilidade pela entrega não identificada: confira na plataforma.'}</small></p>}
 {waiting&&!cancellationWaiting&&!deliveryPending&&<p className="channel-notice" role="status">{order.sync_state==='uncertain'?'Envio sem confirmação. Confira na plataforma; não reenvie.':'Aguardando confirmação da plataforma…'}</p>}
 {order.cancellation_error&&!cancellationWaiting&&<p className="channel-notice cancellation-rejected" role="alert"><strong>Cancelamento não confirmado:</strong> {order.cancellation_error} O pedido permanece na operação.</p>}
 {order.sync_error&&!cancellationWaiting&&!order.cancellation_error&&<p className="channel-notice" role="alert">{order.sync_error}</p>}
 {order.channel_warning&&<p className="channel-notice">{order.channel_warning}</p>}</>;
}
