# VemDeDelivery — pacote multicanal de homologação

Este pacote foi preparado a partir do ZIP enviado. Não foi implantado em produção.

- [Instalação, simulador, credenciais e checklists](docs/INTEGRACOES-MARKETPLACES.md)
- [Relatório de testes e arquivos alterados](docs/marketplaces/RELATORIO-ENTREGA.md)
- [Fontes oficiais e contratos selecionados](docs/marketplaces/FONTES-E-CONTRATOS.md)

**iFood:** implementação testada com mocks, pendente de sandbox/credenciais e homologação oficial.
**99Food:** core e telas simulados; adaptador real bloqueado por falta dos contratos oficiais. Ainda exige implementação após obter esses contratos.

Validação local: 861 testes Django (23 ignorados pelo ambiente), 44 React e 13 scripts. Migrations e build aprovados localmente. PostgreSQL/concorrência e testes em navegador real permanecem gates obrigatórios de homologação.

Não extrair sobre produção. Não substituir o `.env` existente pelo complemento `.env.example`. Não interpretar a simulação como integração certificada ou autorização para publicar.
