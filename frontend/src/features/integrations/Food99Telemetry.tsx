import {Link} from 'react-router-dom';
import {request} from '../../api/client';
import {useQuery} from '../../hooks/useQuery';
import {Feedback} from '../../components/Feedback';
import {panelUrl} from '../../panel';
import './Food99Telemetry.css';

type Alert = {code:string;severity:string;title:string;detail:string;action:string;order_id:number|null;external_id:string|null;age_seconds:number|null};
type Group = {total:number;states:Record<string,number>};
type Check = {key:string;label:string;state:'passed'|'blocked'|'external_pending';detail:string};
type Readiness = {release_authorized:boolean;internal_checks:Check[];external_checks:Check[];internal_passed:number;internal_total:number;external_pending:number;order_modes:Record<string,number>;order_statuses:Record<string,number>;staged_review_count:number;unresolved_command_count:number;summary:string};
type IntegrityIssue = {code:string;severity:string;order_pk:number|null;command_pk:number|null;event_pk:number|null;recommendation:string};
type Integrity = {issues:IntegrityIssue[];truncated:boolean;warning:string};
type Backlog = {available:boolean;reason?:string;selected?:number;ready?:number;invalid?:number;has_more?:boolean;events?:{event_id:number;code:string;order_id:string;result:string}[]};
type Telemetry = {backlog?:Backlog;integrity?:Integrity;readiness?:Readiness;sandbox_only:boolean;read_only:boolean;generated_at:string;connection_count:number;imported_count:number;inbox:Group;outbox:Group;staging:Group;alerts:Alert[];alerts_limit:number;alert_limit_reached:boolean;pilot_enabled:boolean;remote_confirm_enabled:boolean;message:string};

function StatusCounts({title, data}: {title:string;data:Group}) {
  return <section className="food99-telemetry-count" aria-label={title}>
    <h3>{title}</h3><strong>{data.total}</strong>
    <ul>{Object.entries(data.states).sort(([a],[b])=>a.localeCompare(b)).map(([key,num])=><li key={key}><span>{key}</span><b>{num}</b></li>)}</ul>
  </section>;
}

export function Food99Telemetry() {
  const state = useQuery<Telemetry>(()=>request('integrations/99food/telemetry/'));
  return <div className="food99-telemetry">
    <div className="page-heading"><div>
      <p className="eyebrow"><Link to={panelUrl('integracoes/99food')}>99Food</Link> · Homologação</p>
      <h1>Diagnóstico operacional 99Food</h1>
      <p>Somente leitura. Nenhuma confirmação, cancelamento ou finalização é enviada por esta tela.</p>
    </div><button className="secondary" type="button" onClick={state.reload}>Atualizar</button></div>
    <Feedback loading={state.loading} error={state.error}>
      {state.data && <>
        <p role="status">{state.data.connection_count} conexão(ões) sandbox · {state.data.imported_count} pedido(s) importado(s) ·
        {' '}Piloto {state.data.pilot_enabled?'habilitado':'desabilitado'} · Confirmação remota {state.data.remote_confirm_enabled?'habilitada':'desabilitada'}</p>
        <div className="food99-telemetry-grid"><StatusCounts title="Inbox · Webhooks" data={state.data.inbox}/><StatusCounts title="Outbox · Comandos" data={state.data.outbox}/><StatusCounts title="Quarentena · Revisões" data={state.data.staging}/></div>
        {state.data.backlog && <section className="card" aria-label="Backlog local 99Food">
          <h2>Webhooks de pedidos importados · Backlog</h2>
          {!state.data.backlog.available ? <p>{state.data.backlog.reason}</p> : <>
            <p role="status">Primeira página: {state.data.backlog.selected} eventos · {state.data.backlog.ready} elegíveis · {state.data.backlog.invalid} envelopes inválidos.</p>
            <p>Prévia somente leitura. A aplicação exige comando administrativo explícito; nenhum POST é enviado à 99Food.</p>
            <ul>{(state.data.backlog.events || []).map(event=><li key={event.event_id}>
              <strong>Evento #{event.event_id} · {event.code}</strong> · {event.result==='READY'?'Elegível para sincronização local':'Revisão de assinatura/metadados'}
            </li>)}</ul>
            {state.data.backlog.has_more && <p>Há eventos adicionais; use a paginação pelo comando administrativo.</p>}
          </>}
        </section>}
        {state.data.readiness && <section className="card" aria-label="Critérios de liberação 99Food">
          <h2>Critérios de liberação · 99Food</h2>
          <p role="status">{state.data.readiness.internal_passed}/{state.data.readiness.internal_total} verificações locais atendidas · {state.data.readiness.external_pending} pendências externas. <strong>Produção não autorizada.</strong></p>
          <div className="food99-telemetry-grid">
            <div><h3>Verificações locais</h3><ul>{state.data.readiness.internal_checks.map(check=><li key={check.key}><strong>{check.state==='passed'?'✓':'Pendente'} · {check.label}</strong><p>{check.detail}</p></li>)}</ul></div>
            <div><h3>Dependências de homologação externa</h3><ul>{state.data.readiness.external_checks.map(check=><li key={check.key}><strong>{check.label}</strong><p>{check.detail}</p></li>)}</ul></div>
          </div>
          <h3>Pedidos por modalidade reportada</h3>
          <ul>{Object.entries(state.data.readiness.order_modes).map(([mode,total])=><li key={mode}>{mode}: {total}</li>)}</ul>
          <p><small>{state.data.readiness.summary}</small></p>
        </section>}
        {state.data.integrity && <section className="card" aria-label="Auditoria de integridade 99Food">
          <h2>Auditoria de integridade ({state.data.integrity.issues.length} achados)</h2>
          {!state.data.integrity.issues.length && <p>Nenhuma inconsistência encontrada na amostra local.</p>}
          <ul>{state.data.integrity.issues.map((issue,i)=><li key={`${issue.code}-${issue.order_pk}-${issue.command_pk}-${issue.event_pk}-${i}`}>
            <strong>{issue.severity==='critical'?'Crítico':'Atenção'} · {issue.code}</strong>
            <p>{issue.recommendation}</p>
            <small>{issue.order_pk!=null?`Pedido #${issue.order_pk} · `:''}{issue.command_pk!=null?`Comando #${issue.command_pk} · `:''}{issue.event_pk!=null?`Evento #${issue.event_pk}`:''}</small>
          </li>)}</ul>
          {state.data.integrity.truncated && <p>Limite de resultados atingido. Execute a auditoria pelo backend.</p>}
          <small>{state.data.integrity.warning}</small>
        </section>}
        <section className="card"><h2>Alertas que exigem atenção ({state.data.alerts.length})</h2>
          {!state.data.alerts.length && <p>Nenhum alerta identificado pelas regras locais.</p>}
          <div className="food99-telemetry-alerts">{state.data.alerts.map((alert,i)=><article className={`food99-telemetry-alert severity-${alert.severity}`} key={`${alert.code}-${alert.order_id||alert.external_id}-${i}`}>
            <strong>{alert.title}</strong><span>{alert.severity==='critical'?'Crítico':alert.severity==='warning'?'Atenção':'Revisão'}</span>
            <p>{alert.detail}</p><p><strong>Ação:</strong> {alert.action}</p>
            <small>{alert.order_id!=null?`Pedido interno #${alert.order_id} · `:''}{alert.external_id?`Pedido externo ${alert.external_id} · `:''}Origem 99Food{alert.age_seconds!=null?` · Há ${Math.floor(alert.age_seconds/60)} min`:''}</small>
          </article>)}</div>
          {state.data.alert_limit_reached && <p>Exibindo somente os primeiros {state.data.alerts_limit} alertas. Consulte a auditoria completa para outros registros.</p>}
        </section>
        <p><small>{state.data.message} · Atualizado em {new Date(state.data.generated_at).toLocaleString('pt-BR')}</small></p>
      </>}
    </Feedback>
  </div>;
}
