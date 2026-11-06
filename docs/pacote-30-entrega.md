# Pacote 30 — painéis, operação, impressão e atendimento comercial

Base exclusiva: `vemdedelivery-work-atualizado-20261105-171706.zip`. Entrega incremental **parcial em relação ao escopo amplo**, com código funcional e testes locais. Não equivale a aprovação em homologação nem a validação física/Evolution.

## Alterações implementadas

- Tokens e estilos exclusivos do painel administrativo, navegação com financeiro separado de integrações, cards compactos e cores por etapa; vitrine/checkout/SSR públicos sem alterações de fonte.
- Kanban com arraste no desktop, gesto pelo controle Mover em dispositivos de toque e alternativa por seletor para teclado. Qualquer movimento abre a confirmação existente. O backend verifica versão do status sob locks na mesma ordem dos marketplaces antes de executar o serviço existente.
- Prontos reúne visualmente entrega e retirada sem renomear os estados no banco. Cancelamento pendente continua em sua própria coluna. Nenhum comando de entrega é forçado.
- Entregues paginado pela data de conclusão, por padrão hoje no fuso ativo Django (`America/Sao_Paulo`); Todos como visão alternativa, com período por criação. Busca, origem, modalidade e status de histórico; ativos não somem pelo filtro de datas. Mais páginas continuam acessíveis, sem truncamento silencioso.
- KDS reaproveitado com cores; atualização WebSocket/polling e tela cheia existentes preservadas.
- SuperAdmin: contadores reais de lojas, assinaturas controladas/suspensas, pedidos por origem, conversas humanas e faturas pagas em produção no mês. Não apresenta estimativa como MRR.
- Agente comercial separado: instância dedicada, listagem sanitizada, criação/vínculo, QR, saúde, reconexão, logout, pausa/ativação; credenciais globais ficam no servidor. Callback autenticado, inbox persistente, deduplicação, filtro de grupos/autoenvio, opt-out, pausa por mensagem humana, CRM com etapas e histórico, auditoria e consulta periódica.
- IA via Ollama separado: usa histórico e seleciona trechos de conhecimento revisado e perguntas de qualificação. Resposta comercial é composta somente com trechos aprovados e preços consultados no banco. **Não é redação generativa livre:** esta versão prioriza fundamentação e pode soar menos natural. Dados ausentes, mídia, falha de geração, orçamento ou divergência de catálogo encaminham ao humano.
- Artigos imutáveis por versão, incluindo rascunhos preparados por comando. Catálogo com impressão digital/revisão: mudança posterior invalida publicação. Planos, faturas e assinaturas não são alterados. Referência `VDD-...` informada pelo contato pode associar atribuição existente, sem inventar Meta Ads como origem.
- Impressão: três vias não fiscais, snapshot dos textos, 58/80 mm, cópias, evento automático, token revogável por loja, fila, histórico e reimpressão da via salva. Estado `spooled` significa enviado ao spool/socket, **não papel comprovadamente impresso**.
- Agente Python local para ESC/POS de rede (TCP 9100) ou spool RAW de impressora instalada no Windows; journal SQLite persistente, sem repetição automática após resultado incerto.

## Matriz de proteção

| Área | Contrato mantido | Risco principal | Proteção |
|---|---|---|---|
| Pedidos | Serviços atuais, allowed_transitions, Outbox | Estado concorrente | Versão do status e lock connection → external order → order |
| Marketplaces | Pacotes 22–29 e ChannelBand | Falsa confirmação de entrega | Nenhum contrato/provider/flag alterado |
| Vitrine | Fontes públicas existentes | CSS administrativo vazar | Folha importada somente no entrypoint do painel |
| Comercial | Instâncias das lojas/OTP/prospecção separadas | Vazamento, loops e repetição | Instância exclusiva, autenticação, inbox e intenção de envio durável |
| Catálogo | Modelos financeiros oficiais | Preço incorreto | Publicação bloqueada em divergência ou alteração |
| Impressão | Dados salvos no pedido | Cobrança/duplicação | Pagamento consultado, snapshot e chave de evento |

## Estado e limitações reais

1. **Catálogo bloqueante:** código-base ainda possui preço 149,00; não houve acesso ao banco de HML para verificar seus registros. É necessário reconciliar o catálogo oficial com 149,90 e descontos 0/5/10/15 antes de publicar. Não executar `seed_commercial_data` para corrigir: ele altera outras configurações. Não se alterou a migration histórica nem contratos financeiros.
2. Evolution e Ollama reais não foram conectados. Criação/vínculo usa contrato v2 já compatível com o cliente existente; versão instalada deve aceitar `webhook/set` e cabeçalhos customizados. Não homologado com provedor.
3. Conhecimento preparado como rascunho: SuperAdmin revisa e publica as afirmações. Há 8 tópicos iniciais; não representam auditoria comercial completa. Disponibilidade por plano/loja ainda depende da revisão humana; não há ferramenta automática consultando habilitações específicas de um futuro cliente.
4. CRM básico implementado; faltam qualificação estruturada completa, agendamento, resumo automático, proprietário editável, notificações fora do inbox, retenção/LGPD automatizada e follow-up. Opt-out impede retomada. Mensagens retidas não são reenviadas ao ativar/retomar.
5. Não há botão de envio arbitrário de teste nem cobrança/contratação por IA. Teste real deve começar com mensagem recebida de contato consentido. Links de demonstração/contratação não são emitidos automaticamente nesta versão.
6. Envios `sending` após queda ou `uncertain` exigem conciliação humana. Não há UI para confirmar/reconciliar esses envios; retomada fica bloqueada, evitando reenvio cego. O lock global serializa atendimentos da plataforma e pode aumentar latência com muitos leads.
7. Impressão suporta **um dispositivo por loja**, com múltiplas vias. Não implementa roteamento de impressoras separadas por setor, instalador Windows de um clique, serviço automático do sistema operacional ou confirmação física. A codificação CP850 e ESC/POS exigem teste do fabricante. Via cozinha omite finanças/telefone/endereço, mas mantém identificador externo.
8. Impressão automática considera eventos ou estado elegível das últimas 24 horas, até 300 pedidos novos por ciclo; não é um sistema de replay histórico. Ativar pode enfileirar pedidos elegíveis desse período. Após claim sem ACK, conferência humana e reimpressão explícita são necessárias. Snapshot começa na primeira solicitação de impressão; não reconstrói alterações anteriores nela.
9. Mesa/comanda não existe no modelo atual (somente entrega/retirada); não foi simulada. Não houve modernização individual completa de todos os formulários genéricos, nem novo tema escuro administrativo. A personalização/tema da vitrine permanece intacta.
10. Sem deploy, push, acesso à VPS, escrita em banco real ou mudança de flags existentes. Overlays da VPS e HML_IMAGE_TAG não foram tocados.

## Migrações e dependências

- `orders/0020_printdevice_printjob.py`: dispositivo e fila.
- `prospecting/0003_commercialcontrol_commercialconversation_and_more.py`: controle, conhecimento, conversas, mensagens e auditoria.
- Nenhuma migration financeira. Nenhuma dependência nova de runtime no projeto ou no frontend; agente de impressão usa Python 3.11+ padrão. Ollama é serviço externo configurável.

## Aplicação no WSL

Extraia o pacote **fora** do projeto e valide antes de aplicar. `aplicar.py` compara hashes da base e recusa arquivos mais novos/diferentes. Não apaga arquivos nem altera ambientes.

```bash
PACOTE="$HOME/Downloads/vdd-pacote-30-homologacao.zip"
DESTINO="$HOME/projects/delivery-whitelabel"
EXTRACAO="$(mktemp -d /tmp/vdd-p30.XXXXXX)"
unzip -q "$PACOTE" -d "$EXTRACAO"
python3 "$EXTRACAO/aplicar.py" "$DESTINO"
python3 "$EXTRACAO/aplicar.py" "$DESTINO" --apply
cd "$DESTINO"
```

Se o download estiver no Windows, ajuste apenas `PACOTE` para o caminho `/mnt/c/...`. O instalador cria backup ao lado do projeto. Não force aplicação em caso de divergência.

Validação usando **o Compose local de desenvolvimento/homologação do repositório**, nunca na VPS:

```bash
cd "$HOME/projects/delivery-whitelabel"
docker compose -f docker/dev/docker-compose.yml config --quiet
docker compose -f docker/dev/docker-compose.yml ps
docker compose -f docker/dev/docker-compose.yml exec -T backend python manage.py migrate --plan
docker compose -f docker/dev/docker-compose.yml exec -T backend python manage.py migrate --noinput
docker compose -f docker/dev/docker-compose.yml exec -T backend python manage.py check
docker compose -f docker/dev/docker-compose.yml exec -T backend python manage.py prepare_commercial_knowledge --apply
bash ./test-critical-back.sh homolog
bash ./test-critical-front.sh
(cd frontend && npm run build)
```

Se os serviços locais ainda não estiverem iniciados e `docker/dev/.env` já estiver configurado:

```bash
docker compose -f docker/dev/docker-compose.yml up -d --build
```

Este comando é **somente WSL/local**. Não usar `dc-homolog.sh deploy` como comando genérico na VPS. Na VPS são necessários o SHA exato publicado e a lista real de overlays (inclusive piloto 99Food), não disponíveis nesta execução. Não há comando de deploy remoto neste pacote.

Rotas: lojista `/painel/orders`, `/painel/cozinha`, `/painel/impressao`; raiz SuperAdmin `/painel/comercial` e `/painel/`.

## Configuração comercial, sem habilitar envio

Configurações novas no backend: `COMMERCIAL_AGENT_ENABLED=0`, `COMMERCIAL_AGENT_WEBHOOK_URL`, `COMMERCIAL_AGENT_WEBHOOK_TOKEN` (mínimo 32 caracteres), `COMMERCIAL_AGENT_OLLAMA_URL`, `COMMERCIAL_AGENT_OLLAMA_MODEL`. Evolution reutiliza `EVOLUTION_API_URL/KEY`; não copiar esses segredos ao navegador ou aos artigos.

O callback é `https://DOMINIO-RAIZ-HML/integracoes/evolution/commercial-webhook/`. A instância deve ser exclusiva, diferente das lojas, OTP e prospecção. O serviço Ollama deve estar acessível ao container, com modelo previamente instalado. Esses valores precisam corresponder ao ambiente real antes de conectar.

Não se forneceu um comando que habilita envio sem essa validação. O código mantém envio desativado por padrão; a aprovação do catálogo, publicação do conhecimento e ativação do controle no painel também são necessárias. A atualização do callback após rotação do segredo no servidor usa a ação `rotate_webhook` da API SuperAdmin. Não há rotação automática da chave global Evolution.

## Agente local de impressão

No computador com impressora configurada, copie `tools/thermal-agent/agent.py`. No painel Impressão, gere o token e salve-o como variável de ambiente local. Exemplo PowerShell, sem gravar o segredo em um arquivo do projeto:

```powershell
$env:VDD_PRINT_TOKEN = Read-Host 'Token gerado no painel'
python .\agent.py --url 'https://SUA-LOJA-HML' --windows-printer 'NOME EXATO DA IMPRESSORA' --journal "$env:LOCALAPPDATA\vdd-print-journal.sqlite3"
```

Para rede, substitua `--windows-printer ...` por `--network IP_LOCAL_DA_IMPRESSORA`. Não apague o journal. Revogue o token no painel se o dispositivo for perdido. Use uma impressão manual com pedido de teste antes de habilitar automática. Reimprima por ação explícita após conferir fisicamente qualquer resultado incerto.

## Referências de implementação

- Referência conceitual de UX e impressão: https://pedimo.com.br/ (não foi copiada sua identidade ou promessa de compatibilidade).
- Evolution: https://github.com/evolution-foundation/evolution-api e cliente existente `apps/integrations/whatsapp_agent/client.py`.
- Formato JSON do Ollama: https://github.com/ollama/ollama/blob/main/docs/api.md.

## Validação executada nesta entrega

| Verificação | Resultado |
|---|---|
| Suítes de backend do script crítico, com `config.settings.test_sqlite` e SSR local | **972 testes: OK, 25 pulados pela configuração existente** |
| Testes direcionados novos, na versão final | **18 testes: OK** (incluídos no total acima) |
| `bash test-critical-front.sh` | **24 arquivos, 91 testes: OK** |
| Última alteração da prévia de catálogo: teste Commercial | **2 testes: OK**, novamente após a alteração |
| `npm run build` | TypeScript + painel + público + SSR: **OK** |
| `makemigrations --check --dry-run` | **No changes detected** |
| Ferramentas operacionais `unittest discover scripts/tests` | **13 testes: OK** |
| Inspeção visual do Kanban com Chromium e API simulada | Desktop 1440 px e celular 390 px examinados; não é prova de integração real |
| Comparação byte a byte com ZIP original | `apps/channels/`, `frontend/src/public/` e `ChannelBand.test.tsx` preservados |
| `test-critical-back.sh homolog` via Docker | **Não executou a suíte: Docker ausente**; a execução SQLite acima não substitui PostgreSQL |
| Impressora, WhatsApp Evolution, modelo Ollama real | **Não validados fisicamente/de ponta a ponta** |

As primeiras tentativas da suíte local tiveram falhas porque o SSR estava inacessível entre processos do ambiente. Após iniciar SSR e testes no mesmo ambiente de rede, a execução integral terminou com sucesso; não houve alteração de testes antigos para contornar as falhas. Uma colisão textual no filtro iFood foi corrigida na interface e os testes antigos passaram sem edição.

Não foram enviados WhatsApps reais. Mensagens de sucesso impressas por testes de integrações correspondem a mocks.
