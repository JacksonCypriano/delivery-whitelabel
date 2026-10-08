# VemDeDelivery — pacotes 14 a 19 — candidato para homologação

Versão 19.0.0-rc.1. Projeto completo, não apenas patch. Não aplicar em produção.

## O que está incluído

| Pacote | Entrega |
|---|---|
| 14 | Interfaces públicas React/SSR, SEO, conta, checkout e operação ativa |
| 15 | Cozinha/KDS com prioridade, tempo, ações e sincronização |
| 16 | Agendamento no checkout, recuperação opt-in, avaliação e reativação |
| 17 | Histórico/handoff/retomada, áudio e imagem com interpretação configurável |
| 18 | CRM, segmentos, pontos, resgate em cupom, campanhas e métricas |
| 19 | Entregadores, atribuição, saída e comprovação privada de entrega |

Não estão concluídos: conectores iFood/99Food (sem acesso oficial fornecido),
ativação/homologação real de mídia e Meta Pixel/CAPI (sem credenciais), revisão
visual final e remoção física de templates legados. Não afirmar que todos os
requisitos externos já funcionam. A implementação local usa mocks de provedores.

Documentação funcional, arquitetura, arquivos, migrations, rotas, tasks,
limitações e alterações anteriores: docs/packages/package-14 até package-19.
Manifesto completo de arquivos novos/alterados comparado ao ZIP original:
docs/packages/changed-files-14-19.json.

## Validação executada

- Backend: 806 testes, OK; 22 ignorados em SQLite (784 aprovados).
- Frontend: 34 testes aprovados e builds painel/público/SSR concluídos.
- Migrations check: nenhuma alteração sem migration.
- Scripts operacionais: 13 testes aprovados.
- Evidências completas em docs/qa/final-validation.txt e final-frontend.txt.

## Aplicar SOMENTE na cópia de homologação

Antes de substituir arquivos, faça backup da cópia e do banco de homologação.
O ZIP não contém .env, certificados, chaves, banco, node_modules ou caches.
Preserve o .env atual e media local. Não copie segredos para este pacote.

Na raiz do projeto de homologação, confira docker/dev/.env:

```dotenv
MERCHANT_REACT_ENABLED=true
LEGACY_ADMIN_ENABLED=false
PUBLIC_REACT_SSR_URL=http://public-ssr:3001
WHATSAPP_MEDIA_ENABLED=false
```

Suba infraestrutura, construa serviços e aplique migrations:

```bash
docker compose -f docker/dev/docker-compose.yml up -d --build db redis public-ssr backend celery celery-prospecting celery-beat
docker compose -f docker/dev/docker-compose.yml exec -T backend python manage.py migrate --noinput
docker compose -f docker/dev/docker-compose.yml exec -T backend python manage.py collectstatic --noinput
docker compose -f docker/dev/docker-compose.yml exec -T backend python manage.py check
docker compose -f docker/dev/docker-compose.yml exec -T backend python manage.py makemigrations --check --dry-run
bash test-critical.sh homolog
```

Não usar test-critical.sh sem argumento: o comportamento antigo desse script
assume prod. O comando acima passa homolog explicitamente.

O compose dev monta o código em /app, por isso os assets compilados e o servidor
SSR estão incluídos no ZIP. Para reconstruir assets no checkout local:

```bash
cd frontend
npm ci
npm test
npm run build
```

Node 22+ necessário. Volte à raiz antes dos comandos Docker.

## Validar antes de qualquer promoção

1. Execute a suíte PostgreSQL inteira sem falhas. Confira migrations orders
   0014–0018 e integrations 0006; nenhuma migration anterior foi reescrita.
2. Abra `slug.dominio/painel/` como lojista e `dominio/painel/` como SuperAdmin.
   Confirme bloqueio de credenciais cruzadas e de outra loja.
3. Teste catálogo/adicionais/meio a meio, cadastro/OTP, endereços, checkout,
   cupom, estoque, Pix e pagamento na entrega; confira desktop e celular.
4. Abra operação e cozinha em duas telas; conclua entrega e retirada, com
   prazos/mensagens editados. Confira auditoria e envio sem duplicidade.
5. Teste agendamento nos limites e ao atravessar meia-noite.
6. Autorize mensagens com um cliente de teste verificado. Habilite apenas
   automação necessária e teste cancelamento do consentimento/compra anterior.
   Worker e beat devem estar ativos. Automação começa desativada por loja.
7. Handoff mantém histórico/contexto, carrinho e pedido. Retomar atende somente
   próximas mensagens. Para áudio/imagem, configure chave/modelos no ambiente e
   homologue com Evolution. Há custos de API; não foi ativado automaticamente.
8. Ative pontos, entregue compra nova, resgate benefício e aplique cupom. Teste
   resgates simultâneos. Campanhas começam desativadas e precisam de ativação.
9. Cadastre entregador, atribua, despache e conclua com prova opcional. Confira
   foto inacessível por outra loja e que retirada não aceita entregador.
10. Confira HTML/SEO sem JavaScript, consentimento e queda/retorno do SSR.

A validação local SQLite não exerce todas as travas/concorrência PostgreSQL.
Produção continua dependendo de autorização explícita do proprietário.
