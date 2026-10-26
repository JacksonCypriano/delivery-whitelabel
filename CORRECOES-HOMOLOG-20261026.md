# VemDeDelivery — Correções de auditoria React e gratuidades (26/10/2026)

Pacote **completo** gerado a partir do ZIP `vemdedelivery-react-gratuidades-homologacao(1).zip`, mantendo backend, frontend React, rotas legadas, migrations, scripts, integrações e demais arquivos originais. Nenhuma alteração foi aplicada em produção.

## Correções implementadas

1. **Gratuidade + pagamento:** uma concessão em dias ajusta o dia-base da assinatura para o novo vencimento exclusivo. Renovações pagas passam a contar meses a partir do vencimento corrigido, sem absorver os dias de cortesia. A renovação mensal sem concessão mantém seu aniversário original nos meses curtos (ex.: 31/01 → 28/02 → 31/03). Assinaturas com cortesias antigas que deixaram o dia-base desatualizado são identificadas, na próxima renovação, pela concessão registrada e pelo vencimento coincidente.
2. **Ações em massa dos dois painéis:** token de seleção só é consumido ao concluir a ação. Se a resposta retornar erro HTTP, a transação volta atrás; se houver uma nova tela de confirmação, a seleção não é consumida. Proteções de permissão, vínculo e idempotência continuam ativas.
3. **Limpeza automática:** tarefa Celery Beat `admin-selection-cleanup` executada a cada 15 minutos remove seleções temporárias expiradas e seus itens, preservando seleções válidas. O comando `python manage.py prune_admin_selections` continua disponível e reutiliza a mesma lógica.
4. **Testes de regressão:** adicionados em `apps/core/tests_critical/test_react_completion.py` para ordens de concessão e pagamento, viradas de mês/ano e fevereiro bissexto, concessões antigas, ações em massa recusadas nos dois painéis, rollback e expiração/limpeza de seleções.

Nenhuma migration nova foi necessária para estas correções. As migrations já incluídas no ZIP de origem devem estar aplicadas em homologação.

## Verificações nesta entrega

- Sintaxe dos módulos Python, `python -m compileall -q apps config`: **sem erros**.
- Testes dos scripts operacionais: **13 passaram** (`python3 -m unittest discover -s scripts/tests -p "test_*.py" -q`).
- Testes isolados de cálculo de meses e finalização de seleções por extração das funções Python (sem Django): **passaram**.
- **Não executados neste ambiente:** suíte Django/PostgreSQL, suíte crítica, Celery Beat, interface React no navegador, integração real Asaas/Evolution/iFood. O ambiente de preparação não possui Docker nem as dependências Django instaladas. Os logs `qa-results` originais foram preservados; não validam as modificações deste pacote.

## Validar em homologação, nunca em produção diretamente

Após aplicar este ZIP à cópia do repositório de homologação, preservando `docker/dev/.env` e dados locais:

```bash
COMPOSE_PARALLEL_LIMIT=1 ./dc-homolog.sh
bash test-critical.sh homolog
docker compose -f docker/dev/docker-compose.yml exec -T backend python manage.py check
docker compose -f docker/dev/docker-compose.yml exec -T backend python manage.py showmigrations billing core
```

Conferir em homologação uma concessão de sete dias seguida de pagamento mensal e o inverso; ações em massa que falham por proteção, tanto no SuperAdmin quanto no lojista; e funcionamento do container `celery-beat`:

```bash
docker compose -f docker/dev/docker-compose.yml logs --tail=100 celery-beat celery
```

**Não desative o Django Admin legado** antes de concluir a validação funcional da matriz de paridade. Este pacote corrige os três achados da última auditoria; não constitui evidência de 100% de equivalência funcional em navegador.
