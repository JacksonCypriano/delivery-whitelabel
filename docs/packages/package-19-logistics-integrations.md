# Pacote 19 — Logística e integrações

Implementação local da logística; conectores externos pendentes de acesso.

React `/painel/logistica/`; GET/POST `/api/merchant/logistics/`; foto privada em
GET `/api/merchant/logistics/<id>/photo/`. Cadastro e ativação de entregadores,
atribuição de pedido pronto, saída e conclusão. Somente modalidade entrega.
Atribuição é isolada por loja; retirada não permite entregador. Transições usam
transition_order, auditoria, realtime e WhatsApp existentes. Repetir a mesma
ação não duplica conclusão/auditoria; cada troca de entregador mantém histórico.

Comprovação inclui data/hora do servidor, quem recebeu, foto e coordenadas
opcionais. Foto é validada e reencodificada em JPEG sem metadados, até 2 MB na
entrada e dimensão limitada. Bytes privados no banco; nunca em URL pública de
media. Foto, destinatário e localização acessíveis apenas ao painel daquela loja.
O registro é informado pelo operador, não comprova geolocalização independente.

Migration orders.0018: Courier, DeliveryAssignment e DeliveryAudit.
Novos arquivos: logistics_models.py, merchant/logistics.py, Logistics.tsx e
 test_package19_logistics.py. Rotas/menu/model registry alterados para integração.
Nenhuma task externa nova; reutiliza o envio de status.

**iFood e 99Food não estão implementados/ativados nesta entrega.** Sem contratos,
credenciais ou homologação de API fornecidos, não é seguro inventar endpoints,
webhooks, estados externos ou importação. Tela mostra claramente a pendência.
Para concluir conectores: acesso oficial, documentação/versão autorizada,
merchant IDs, sandbox, assinatura dos webhooks e mapeamento real de status,
pagamentos, itens/adicionais e cancelamentos. A central atual mantém fontes web,
WhatsApp e manual; não simula pedidos externos.

Homologar isolamento, foto privada, troca concorrente de entregador,
confirmação repetida e sincronização entre cozinha/operação/logística.

Validação final: 806 testes backend OK (22 ignorados em SQLite), 34 testes
frontend aprovados, build painel/público/SSR, migrations check e 13 testes de
scripts operacionais aprovados. Uma primeira execução falhou por importação
faltante no teste novo de cutover; importação corrigida e suíte reexecutada.
Evidência conclusiva: docs/qa/final-validation.txt e final-frontend.txt.
