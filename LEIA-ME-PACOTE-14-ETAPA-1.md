> Documento histórico da entrega anterior. A entrega atual está em LEIA-ME-PACOTES-14-A-19.md.

# VemDeDelivery — Pacote 14, etapa 1

**Este ZIP contém o projeto completo, mas a implementação do Pacote 14 é parcial.**

Entrega: tela de pedidos ativos em `/painel/operacao/`, status real de retirada, prazos por modalidade, confirmação/editável de mensagem, auditoria e inventário inicial de templates. O frontend público ainda não foi migrado. Pacotes 15–19 não foram iniciados.

Documentação: `docs/packages/package-14-react-everywhere.md`.
Evidências: `docs/qa/package-14-etapa-1-validation.txt`.
Arquivos: `docs/package-14-etapa-1-files.json`.

## Validar apenas em homologação

Extraia este projeto em uma cópia de trabalho de homologação e mantenha os arquivos de configuração locais. O ZIP não contém `.env`, certificados, chaves privadas, `node_modules` ou caches. Os `.env.example` são modelos, não configuração ativa.

Na raiz do projeto de homologação:

```bash
cd frontend
npm ci
npm test
npm run build
cd ..
docker compose -f docker/dev/docker-compose.yml up -d db redis
docker compose -f docker/dev/docker-compose.yml build backend
docker compose -f docker/dev/docker-compose.yml run --rm --no-deps --entrypoint python backend manage.py migrate --noinput
docker compose -f docker/dev/docker-compose.yml run --rm --no-deps --entrypoint python backend manage.py makemigrations --check --dry-run
docker compose -f docker/dev/docker-compose.yml up -d backend celery celery-beat
bash test-critical.sh homolog
```

O build local também é necessário porque o compose de homologação monta a raiz do projeto por volume. A migration nova é `orders.0014_operational_pickup`.

Abrir no host da loja: `https://SLUG.DOMINIO/painel/operacao/` (em desenvolvimento, use o host/porta já configurados, por exemplo `http://SLUG.lvh.me:8000/painel/operacao/`). A raiz sem slug continua sendo o painel SuperAdmin.

Validar entrega e retirada, alteração por outro operador, pedido entregue saindo da operação, reconexão, som/notificação, prazos, mensagem efetiva na auditoria e envio com Evolution de homologação. Não utilizar clientes reais nos testes de mensagem.

Produção continua dependendo da validação completa e de autorização explícita do responsável.
