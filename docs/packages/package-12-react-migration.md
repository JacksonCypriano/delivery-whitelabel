# Pacote 12 — Migração do painel do lojista para React

## Estado

Implementação candidata à homologação. **Não aprovada para cutover definitivo nem produção.** Os critérios finais dependem da suíte crítica em PostgreSQL/homologação, validação Docker e aceite manual das integrações. Nenhum deploy realizado, nenhuma migration nova.

| Etapa | Entregas | Situação |
|---|---|---|
| 12.0 Fundação | React/TypeScript/Vite/Router, cliente HTTP, sessão/CSRF, login/logout/senha, layout, componentes, Docker Node 22, CI sem deploy | Implementado; testes locais aprovados, Docker/CI externos pendentes |
| 12.1 Dashboard | Checklist original, contadores, assinatura, atalhos React e loja pública | Implementado; aceite manual pendente |
| 12.2 Minha loja | Configuração, identidade, horários/intervalos, modo de atendimento, zonas/taxas, perfil/publicação e CEP | Implementado; aceite de homolog e ViaCEP real pendentes |
| 12.3 Catálogo | Produtos, categorias, imagens, disponibilidade/destaque, dias, promoções, estoque, grupos/rótulos/opções, meio a meio, edição rápida em lista e ações | Implementado; concorrência PostgreSQL pendente |
| 12.4 Pedidos | Consulta/detalhes/itens, filtros, métricas originais de 30 dias, cancelamento confirmado com devolução de estoque | Implementado; validação operacional em homolog pendente |
| 12.5 Clientes/cupons | Clientes da loja somente leitura, campanhas, seleção de clientes, públicos/validade/limites, ativação/desativação e utilizações | Implementado; matriz manual pendente |
| 12.6 Financeiro | Assinatura, planos/adicionais, cotações, cobranças/consulta, histórico, taxas, notas PDF/XML, solicitação de subconta e aceite | Implementado; testes de serviços simulados, sandbox Asaas real pendente |
| 12.7 WhatsApp | Conectar/QR/verificar/desconectar/toggle, diagnóstico/eventos, leitura periódica do status, QR ocultado após 60 segundos | Implementado; pareamento real em homolog pendente |
| 12.8 Paridade | Forms/formsets/querysets/hooks preservados, validação por tenant, erros, responsividade, testes locais backend/frontend e navegador | Validação local realizada; aceite integral pendente |
| 12.9 Cutover | Flag, redirects de `/admin/` e dashboard antigo, bloqueio POST legado, `/painel/` no domínio raiz para SuperAdmin e `/superadmin-legacy/` somente como fallback técnico | Mecanismo implementado; padrão false; cutover definitivo NÃO executado |

## Preservação

Regras continuam no Django. Não foram acrescentados status de pedido, WebSocket, KDS, fidelidade, CRM, recuperação de carrinho, ERP/NFC-e ou automações do agente. Não houve alteração dos cálculos, modelos, migrations, serviços de estoque, pagamento ou fiscal.

React renderiza campos e componentes próprios; não usa iframe nem templates HTML injetados. Downloads fiscais e checkout externo Asaas são links para arquivo/pagamento. Os templates antigos permanecem para dependências compartilhadas e fallback técnico de homologação.

## Histórico e referências

Base: `vemdedelivery-atual-20261005-1817.zip`.

- `docs/react-migration-inventory.md`: matriz das 13 entidades e telas especiais, models/forms/rotas/permissões.
- `docs/react-migration.md`: arquitetura, execução, validação, riscos e pendências.
- `docs/package-12-files.json`: lista exata de arquivos criados/modificados.

O ZIP inclui código completo e build estático. node_modules, venvs, caches e banco de teste não fazem parte da entrega.

## Aceite obrigatório

Validar somente no checkout de homologação, com duas lojas, PostgreSQL e integrações de teste. Registrar os gates descritos em react-migration.md. A autorização de produção permanece exclusivamente com o responsável pelo projeto, depois dos testes e migrations aprovados.
