// @vitest-environment jsdom
import {describe,it,expect,vi} from 'vitest';
import {render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {Food99Telemetry} from './Food99Telemetry';

vi.mock('../../hooks/useQuery',()=>({useQuery:()=>({loading:false,error:null,reload:vi.fn(),data:{
  sandbox_only:true,read_only:true,generated_at:'2026-11-05T12:00:00Z',connection_count:1,
  imported_count:2,pilot_enabled:false,remote_confirm_enabled:false,
  inbox:{total:3,states:{blocked:2,processed:1}},outbox:{total:1,states:{uncertain:1}},
  staging:{total:2,states:{review:2}},alerts_limit:50,alert_limit_reached:false,
  message:'Diagnóstico local',
  backlog:{available:true,selected:2,ready:1,invalid:1,has_more:true,events:[
    {event_id:22,code:'orderConfirm',order_id:'123',result:'READY'},
    {event_id:23,code:'orderReady',order_id:'123',result:'INVALID_ENVELOPE'}]},
  readiness:{release_authorized:false,internal_passed:2,internal_total:3,external_pending:1,
    internal_checks:[{key:'sandbox',label:'Sandbox isolado',state:'passed',detail:'Ambiente seguro'}],
    external_checks:[{key:'delivery',label:'Contrato deliveryStatus',state:'external_pending',detail:'Pendente da 99Food'}],
    order_modes:{MERCHANT:2},order_statuses:{pending:2},staged_review_count:0,unresolved_command_count:1,
    summary:'Auditoria local'},
  integrity:{issues:[{code:'UNCERTAIN_REMOTE_POST',severity:'critical',order_pk:12,command_pk:7,event_pk:null,
    recommendation:'Conferir a 99Food'}],truncated:false,warning:'Amostra local'},
  alerts:[{code:'REMOTE_OUTCOME_UNKNOWN',severity:'critical',title:'Resultado remoto incerto',
    detail:'Comando sem confirmação.',action:'Nunca reenviar automaticamente.',order_id:12,external_id:'123',age_seconds:360}],
}})}));

describe('99Food telemetry',()=>{
  it('mostra estados independentes e proíbe interpretação como confirmação remota',()=>{
    render(<MemoryRouter><Food99Telemetry/></MemoryRouter>);
    expect(screen.getByText('Diagnóstico operacional 99Food')).toBeTruthy();
    expect(screen.getByText('Inbox · Webhooks')).toBeTruthy();
    expect(screen.getByText('Outbox · Comandos')).toBeTruthy();
    expect(screen.getByText('Quarentena · Revisões')).toBeTruthy();
    expect(screen.getByText('Resultado remoto incerto')).toBeTruthy();
    expect(screen.getByText(/Nunca reenviar automaticamente/)).toBeTruthy();
    expect(screen.getByText(/Pedido interno #12/)).toBeTruthy();
    expect(screen.getByText(/Produção não autorizada/)).toBeTruthy();
    expect(screen.getByText('Contrato deliveryStatus')).toBeTruthy();
    expect(screen.getByText(/UNCERTAIN_REMOTE_POST/)).toBeTruthy();
    expect(screen.getByText('Webhooks de pedidos importados · Backlog')).toBeTruthy();
    expect(screen.getByText(/Evento #22/)).toBeTruthy();
    expect(screen.getByText(/Há eventos adicionais/)).toBeTruthy();
  });
});
