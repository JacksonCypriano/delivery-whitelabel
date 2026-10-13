/** Source detail remains on the order; this is the primary sales channel. */
export function ChannelBand({order}:{order:any}) {
 const channel=['ifood','99food'].includes(order.channel || order.source) ? (order.channel || order.source) : 'vemdedelivery';
 const label=channel==='ifood'?'iFood':channel==='99food'?'99Food':'VemDeDelivery';
 const waiting=['pending','sending','awaiting','uncertain'].includes(order.sync_state);
 return <><div className={`channel-band channel-${channel}`} data-channel={channel}><strong>{label}</strong>{order.channel_simulated?<span>SIMULAÇÃO</span>:order.channel_test?<span>TESTE</span>:null}</div>
 {order.external_id&&<small className="channel-id">Pedido externo: {order.external_display_id||order.external_id}{order.external_display_id&&<span title={order.external_id}> · {order.external_id}</span>}</small>}
 {order.platform_notes&&<p className="operation-note">{order.platform_notes}</p>}
 {order.prepare_after&&<small>Preparar a partir de {new Date(order.prepare_after).toLocaleString('pt-BR')}</small>}
 {order.scheduled_until&&<small>Janela até {new Date(order.scheduled_until).toLocaleString('pt-BR')}</small>}
 {waiting&&<p className="channel-notice" role="status">{order.sync_state==='uncertain'?'Envio sem confirmação. Confira na plataforma; não reenvie.':'Aguardando confirmação da plataforma…'}</p>}
 {order.sync_error&&<p className="channel-notice" role="alert">{order.sync_error}</p>}
 {order.channel_warning&&<p className="channel-notice">{order.channel_warning}</p>}</>;
}
