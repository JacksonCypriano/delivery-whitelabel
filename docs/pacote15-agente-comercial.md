# Pacote 15 — agente comercial para validação

Implementação local determinística, sem testes executados, builds, Django iniciado,
serviços, chamadas externas, mensagens, deploy, commit ou push. A conferência de
sintaxe usa AST, sem importar a aplicação. Não representa validação de produção.

## Alterações e limites

- A política P14 encaminhava praticamente toda dúvida fiscal. P15 distingue NF
  da assinatura/serviço, emissão das vendas e pergunta ambígua; somente questões
  tributárias, procedimentos, prazos e tipos documentais não confirmados exigem humano.
- A interpretação usa a mensagem atual e o contexto recente da própria conversa;
  mensagens humanas, retidas ou incertas interrompem essa memória. Não consulta tenants.
- O novo artigo `notas-fiscais` contém as respostas oficiais, sem prometer emissão
  automática da assinatura. Para vendas informa ausência de integração fiscal e
  diferença dos comprovantes não fiscais. Artigo ausente/rascunho bloqueia a resposta.
- A apresentação geral usa uma unidade editorial concisa de `visao-geral`, mantendo
  condições de configuração e resultados. Artigos antigos continuam suportados.
- Normalização ampliada para NF informal, impressão/comanda e contratação informal.
  Perguntas fiscais não acionam preço/contratação apenas por citarem mensalidade ou
  contratação. Perguntas independentes de preço, iFood e KDS são preservadas.
- Equivalência mensal calculada do catálogo publicado, com Decimal e arredondamento
  de centavos, explicitando pagamento antecipado pelo período completo.
- `prepare_commercial_final --slug` permite preparar somente os dois artigos P15,
  sem sobrescrever propostas de outros assuntos. O comando cria rascunhos, não publica.
- Mantidos os 74 cenários da bateria; 18 expectativas de handoff fiscal foram
  substituídas pela resposta oficial negativa de emissão das vendas. NFS-e sem
  contexto confirmado continua exigindo humano. Acrescentados 21 cenários: total 95.
  A bateria também detecta frases repetidas e termina com código 1 se houver falha.
- Novos testes de composição, contexto, fontes publicadas, informalidade e cálculo;
  expectativas P14 atualizadas apenas onde a regra comercial/editorial mudou.

Não há emissão fiscal nova, ERP/estoque, integração logística nem nova IA.
A evolução da Inbox adiciona uma migration e alterações no frontend, mantendo as integrações existentes. Estoque sem fato publicado continua humano;
99Food mantém necessidade de homologação; iFood e impressão mantêm condições.
Solicitação de contratação segue para equipe, sem links inventados.
Compreensão universal não é prometida: assunto desconhecido pede esclarecimento ou
encaminhamento. A publicação editorial é indispensável para as respostas novas.

## Segurança revisada e preservada

| Controle | Implementação/cobertura existente |
|---|---|
| Duas travas globais | `COMMERCIAL_AGENT_ENABLED` e `CommercialControl.enabled` |
| Autorização por contato | `CommercialPilotContact.active`; ausência nega envio |
| OTP | `CommercialOtpExclusion`, quarentena antes do envio transacional |
| Instância / tenants | `validate_instance`, exclusão de instâncias das lojas; chave conversa `(instance, phone)` |
| Webhook | token constante, instância, evento, mensagens diretas e deduplicação por ID |
| Takeover / opt-out | conversa pausada; itens pendentes retidos; retomada administrativa |
| Concorrência | locks de controle/conversa e intenção `sending` antes do POST |
| Timeout / falha incerta | `uncertain`, pausa e alerta; sem reenvio automático |
| Mídia | `media_requires_human`, sem alegar transcrição/interpretação |
| Regressões existentes | `test_commercial.py`, `test_commercial_release.py`, `test_commercial_pilot_otp.py`, `test_commercial_history_p132.py`, `test_commercial_greetings_p13.py` |

Nenhum número, flag, exclusão, estado de produção ou caminho de envio foi alterado.
Quando a segurança exige transferência integral, a mensagem original permanece no
Inbox e no alerta ligado à mensagem. O trace do motor também registra as intenções
antes do handoff; não se envia resposta parcial potencialmente enganosa.

## Aplicação no WSL

Salve o ZIP em `/home/jacksoncypriano/Downloads/vdd-pacote15-incremental.zip`.
Com a árvore local sem alterações conflitantes:

```bash
cd /home/jacksoncypriano/projects/delivery-whitelabel
unzip -o /home/jacksoncypriano/Downloads/vdd-pacote15-incremental.zip -d .
git diff --stat
git diff --check
```

Versione exclusivamente os caminhos do manifesto (inclui novos arquivos):

```bash
cd /home/jacksoncypriano/projects/delivery-whitelabel
git add --pathspec-from-file=docs/pacote15-arquivos.txt
git diff --cached --stat
git diff --cached
```

Revise também qualquer alteração que já estivesse no staging antes do pacote.
Após revisão, para criar o commit local (nenhum push é feito por estes comandos):

```bash
git commit -m "Finaliza regras fiscais e qualidade do agente comercial P15"
```

Testes a executar por você, no ambiente local apropriado:

```bash
./test-critical-back.sh
./test-critical-front.sh
```

Esses scripts podem usar o Docker local. Eles NÃO foram executados nesta entrega.

## Publicação dos artigos e validação na VPS

Primeiro publique o código em homologação pelo fluxo existente. O comando abaixo
opera no backend já existente; não inicia containers. Execute a prévia:

```bash
cd /opt/vemdedelivery/hml/app
docker compose -f docker/hml/compose.yml exec -T backend python manage.py prepare_commercial_final --slug notas-fiscais --slug visao-geral
```

Pause o agente no painel comercial, depois prepare os rascunhos:

```bash
docker compose -f docker/hml/compose.yml exec -T backend python manage.py prepare_commercial_final --slug notas-fiscais --slug visao-geral --apply
```

Revise e publique os dois artigos no painel existente. O rascunho mais recente
suspende a revisão anterior até publicação; mantenha o agente pausado nesse intervalo.
Não é necessário alterar preços ou republicar um catálogo válido. Confira os quatro
planos: mensal 149,90; trimestral 427,22; semestral 809,46; anual 1.528,98.

Bateria em homologação, após publicação editorial:

```bash
docker compose -f docker/hml/compose.yml exec -T backend python manage.py shell -c "exec(compile(open('scripts/commercial/bateria_p14_vps.py', encoding='utf-8').read(), 'scripts/commercial/bateria_p14_vps.py', 'exec'))"
```

O nome do script foi mantido por compatibilidade. Ele chama somente composição,
com bloqueios dos transportes existentes, sem `receive/process_message`. Os dados
criados ficam em transação revertida. Sequências PostgreSQL podem avançar apesar do
rollback; não há alterações persistentes de conversas, artigos ou autorização.
O resultado tem 95 cenários e deve ser revisado também pelo conteúdo, não só pelos termos.

Depois da aprovação de homologação e do deploy blue/green pelo fluxo existente,
identifique o backend ativo pelo arquivo operacional preservado pelo deploy:

```bash
cd /opt/vemdedelivery/app
VDD_ACTIVE_BACKEND="$(sed -nE 's/.*server (backend-(blue|green)):8000.*/\1/p' docker/prod/nginx/conf.d/active-upstream.conf)"
case "$VDD_ACTIVE_BACKEND" in
  backend-blue|backend-green) ;;
  *) echo 'Backend ativo não identificado; interrompido.' >&2; exit 1 ;;
esac
docker compose -f docker/prod/docker-compose.bluegreen.yml ps "$VDD_ACTIVE_BACKEND"
```

Confirme que o serviço está saudável. Faça a prévia editorial em produção:

```bash
docker compose -f docker/prod/docker-compose.bluegreen.yml exec -T "$VDD_ACTIVE_BACKEND" python manage.py prepare_commercial_final --slug notas-fiscais --slug visao-geral
```

Pause o agente no painel antes do `--apply`; revise/publice os dois artigos e só
então retome o piloto pelo painel, preservando sua autorização atual:

```bash
docker compose -f docker/prod/docker-compose.bluegreen.yml exec -T "$VDD_ACTIVE_BACKEND" python manage.py prepare_commercial_final --slug notas-fiscais --slug visao-geral --apply
```

Bateria de produção, após revisão/publicação (pode permanecer pausado):

```bash
docker compose -f docker/prod/docker-compose.bluegreen.yml exec -T "$VDD_ACTIVE_BACKEND" python manage.py shell -c "exec(compile(open('scripts/commercial/bateria_p14_vps.py', encoding='utf-8').read(), 'scripts/commercial/bateria_p14_vps.py', 'exec'))"
```

Nenhum comando desta seção foi executado nesta entrega.

## Checklist para ampliação gradual

- [ ] Aplicar pacote; revisar diff e rodar testes locais de backend/frontend.
- [ ] Publicar código em homologação, preparar/revisar/publicar os dois artigos.
- [ ] Executar bateria HML: 95 cenários, nenhum erro; auditar respostas reais.
- [ ] Conferir NF da assinatura, negativa das vendas, ambiguidade e questões específicas.
- [ ] Conferir preços, equivalência antecipada, iFood/99Food e impressão sem promessas.
- [ ] Publicar blue/green; conferir backend ativo, workers e integridade do catálogo.
- [ ] Publicar artigos em produção com agente pausado e executar bateria de produção.
- [ ] Retomar somente o piloto atual e testar WhatsApp real com contato autorizado.
- [ ] Confirmar entrega pelo WhatsApp/webhook: `submitted` significa aceitação, não entrega.
- [ ] Validar transferência humana, alerta no Inbox, takeover e retomada explícita.
- [ ] Verificar bloqueios global/banco, número não autorizado e exclusões OTP.
- [ ] Ampliar em pequenos grupos somente após aprovação humana, com capacidade de atendimento.

A implementação NÃO tem modo irrestrito: cada novo contato precisa de autorização
explícita. No painel superadmin comercial, pausar antes de `pilot_allow` ou
`pilot_revoke`; o cadastro usa telefone brasileiro com DDI 55 e bloqueia números OTP.
`enable` exige `confirm_pilot=true`, instância conectada, catálogo publicado e ao menos
um contato ativo, além da flag global já existente. Não remova allowlist ou exclusões.
Mensagens retidas não são reenviadas em massa ao reativar. A ampliação não foi feita.

Interrompa pelo painel (`pause`) se houver resposta fiscal incorreta, duplicação,
contato indevido, interferência OTP, falha de takeover, entrega incerta ou catálogo
inconsistente. Revogue novos contatos com o agente pausado. Não reprocesse mensagens
`uncertain`/`sending` sem reconciliação humana. Para reversão do código use o fluxo
blue/green existente somente com destino saudável; `scripts/prod/blue_green_rollback.sh`
altera o tráfego web, mas não reverte sozinho os workers Celery: mantenha o agente
pausado até os workers também estarem na versão desejada. Artigos são versionados;
revisão editorial corretiva deve ser publicada pelo painel. Não apague histórico/OTP.

## Arquivos entregues

A lista completa está em `docs/pacote15-arquivos.txt`, também usada no `git add`.
O ZIP contém apenas os arquivos desta lista, nos caminhos originais do repositório.


---

## Complemento: Inbox Comercial e alertas de atendimento humano (integrado ao P15)

**Base:** entrega do Work Pacote 15 (13 arquivos), preservada nesta entrega consolidada.
**Status:** código preparado; nenhum teste ou deploy executado. Não aplicar em produção sem
migração, revisão e testes locais/HML.

### Inbox e notificações

- Conversa central mais ampla; lista lateral compacta; mensagens do cliente e do
  agente em lados distintos; cabeçalho e composição reduzidos; disposição responsiva.
- Alertas pendentes na Inbox com `https://wa.me/<telefone-do-cliente>`; contador no
  cabeçalho e menu de superadmin; acesso pelo painel de configuração comercial.
- Assumir o atendimento **não** resolve o aviso. Mensagem humana confirmada na
  instância comercial ou mensagem confirmada pelo painel resolve os avisos pendentes
  da conversa. O histórico fica preservado.
- Respostas enviadas via WhatsApp de **outro número/instância** não geram webhook
  observável na instância comercial. Nesse caso, somente confirmação manual
  explícita no painel após responder ao cliente resolve a notificação.
- Transições e envios conservadores: uma notificação pendente por conversa;
  tentativa de envio WhatsApp no máximo uma vez por alerta. Resultado incerto não
  é reenviado automaticamente; o aviso permanece pendente.
- O encaminhamento WhatsApp é uma **mensagem operacional** do número da instância
  comercial ao administrador, não uma resposta automática a novos contatos;
  não altera a allowlist do piloto nem as exclusões OTP. Somente conversas de
  contatos comercialmente autorizados geram envio operacional; o destinatário
  de aviso não pode coincidir com um contato piloto.
- Não se presume entrega final pelo WhatsApp apenas porque a Evolution aceitou
  a mensagem (status `submitted`).

### Configuração e segurança

A migration `apps/prospecting/migrations/0007_commercial_handoff_notifications.py`
adiciona ao controle comercial:

- Destinatário inicial: `5511983491206`.
- Envio de notificações WhatsApp: **DESATIVADO por padrão**. Ative explicitamente
  em **Agente comercial → Notificações operacionais pelo WhatsApp**, após validação.
- Primeiro período de envio começa na ativação. Alertas anteriores não são
  disparados retroativamente. O contato de aviso não entra na allowlist do piloto.
- O operador pode trocar o número no painel; alteração do destino reinicia o
  marco de envio para não disparar pendências antigas.

A tarefa periódica existente `commercial-human-alerts` executa a distribuição
independente de e-mail e WhatsApp, sem criar uma segunda infraestrutura de agendamento.
Não remover a agenda do Celery Beat. Falha de e-mail não oculta mais um alerta humano
pendente.

### Fluxo de validação obrigatório

1. Aplique **o ZIP consolidado** em uma árvore limpa de `main`/`homolog` apropriada;
   **não** aplique o pacote Work novamente em cima do consolidado.
2. Revise `git diff`, o manifesto, testes e a migration. Execute as suítes críticas
   localmente, incluindo os novos testes de regressão de notificações.
3. Faça deploy somente em HML; execute `python manage.py migrate` dentro do
   backend HML seguindo o procedimento operacional existente. A migration é
   obrigatória antes do uso da nova tela.
4. Prepare, revise e publique os artigos `notas-fiscais` e `visao-geral` do P15
   conforme a seção original deste documento; execute a bateria ampliada de **95**
   cenários, sem mensagens reais.
5. Confirme a Inbox em desktop e celular, alertas no painel, sem duplicações,
   respostas humanas pela mesma instância, takeover, OTP e estados incertos.
6. Só então publique em produção com blue/green; aplique migration no fluxo
   existente, revise/publice os artigos; reteste o piloto autorizado.
7. **Habilite expressamente** o envio de avisos ao número inicialmente cadastrado,
   em produção somente após confirmação do destinatário e autorização operacional.
   Não libere leads adicionais até concluir o piloto e a auditoria.

### Observações operacionais

- O botão **Abrir WhatsApp** utiliza o navegador e pode abrir um WhatsApp pessoal;
  isso não assegura resposta por meio da instância comercial. Se usar outro número,
  marque como atendido na Inbox somente após responder efetivamente.
- A resposta pelo campo da Inbox requer `COMMERCIAL_HUMAN_PANEL_SEND_ENABLED` e
  conversa assumida pelo usuário; não modifique essa flag automaticamente.
- O envio da notificação operacional e o envio de mensagens ao cliente são fluxos
  independentes. Falhas de envio de aviso não devem impedir a Inbox de funcionar.
- Não houve alteração de credenciais, `.env`, branch, flag de produção, autorizados
  ou ambientes remotos nesta entrega.
