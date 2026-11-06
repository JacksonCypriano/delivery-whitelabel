# Validação visual isolada das lojas

Usa React/SSR reais e **fixtures locais**, sem autenticação, pedidos ou pagamentos reais.
As imagens são públicas da vitrine demonstrativa; contatos e CSRF são fictícios/removidos.
A pasta tem dependências próprias, sem alterar o package.json nem o lock do aplicativo.

Na raiz do projeto, após `cd frontend && npm ci && npm run build && cd ..`:

```bash
(cd frontend/visual-check && npm install && npx playwright install chromium)
node public-ssr/server.mjs &
SSR_PID=$!
node frontend/visual-check/server.mjs &
FIXTURE_PID=$!
trap 'kill "$SSR_PID" "$FIXTURE_PID" 2>/dev/null || true' EXIT
(cd frontend/visual-check && npm test)
```

O servidor utiliza 127.0.0.1:4173 e o SSR 127.0.0.1:3001; encerre instâncias anteriores.
`VISUAL_PORT`, `VISUAL_SSR_URL`, `VISUAL_BASE_URL` permitem outras portas.
`VISUAL_OUTPUT` define a pasta de capturas. `CHROMIUM_PATH` aceita um navegador já instalado.

Asserções em 1440×960, 768×960 e 390×960:
- Ausência de rolagem horizontal e erros JavaScript.
- Contraste básico do texto do carrinho (cor diferente do fundo).
- Tema persistente ao navegar; claro e escuro nas páginas cobertas.
- Busca/limpeza, detalhe/modal, meio a meio, quantidade inválida e Escape.
- Falha ao carregar opções e recuperação por retry.
- Carrinho e atualização do contador/totais com resposta simulada.
- Entrega/retirada e opções de pagamento preservadas.
- Revisão, pagamento pendente, conta, sucesso, catálogo/carrinho vazios e produto indisponível.

As capturas são evidências, não um teste de igualdade de pixels com produção.
Para comparação antes/depois use a mesma fixture e o mesmo Chromium. O fixture server também
aceita `VISUAL_STATIC_ROOT` e `VISUAL_SSR_URL` para servir um build anterior.

O teste não substitui `./test-critical.sh homolog`, o backend real, a homologação dos
pagamentos e a avaliação manual em Safari/iOS. Não aponte o servidor de fixtures ao SSR de produção.
