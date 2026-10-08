# Pacote 14 — Interfaces React e operação

Estado: implementação para homologação, ampliada além da etapa 1 já validada.
Não confundir validação local SQLite com aceite em PostgreSQL e revisão visual.

## Interfaces

- Loja, catálogo, produto, adicionais/meio a meio, carrinho, checkout, revisão,
  pagamento e conta do cliente usam componentes React públicos.
- Login, cadastro, contato/OTP, endereços, pedidos e recuperação de senha usam
  os mesmos forms/validações Django; somente a apresentação foi substituída.
- Marketplace, landing, páginas SEO, termos e privacidade usam React SSR.
- Painel lojista e SuperAdmin mantêm as interfaces React anteriores.
- Operação `/painel/operacao/`: apenas ativos, realtime/fallback existentes,
  retirada com estado real, confirmação/mensagem editável, prazos e auditoria.

## Arquitetura

Views e serviços Django preservados. `apps/public_ui` monta DTOs por allowlist;
Accept: application/json retorna DTO, HTML chama renderer Node interno. React
renderiza documento com conteúdo, title, canonical, robots, OG/Twitter e JSON-LD
no servidor e hidrata no navegador. Sessão, CSRF, tenant, validação de preços,
estoque, cupons, OTP, Asaas e fiscal continuam no backend. Nenhum pagamento é
confirmado pela imagem de comprovante ou por informação do navegador.

`public-ssr` é serviço Docker privado, sem porta pública. URL no backend:
PUBLIC_REACT_SSR_URL=http://public-ssr:3001. Serviço indisponível retorna 503,
não uma página SEO vazia. Dockerfile constrói os assets públicos e do painel;
Dockerfile.public-ssr constrói o servidor de renderização.

## Corte e templates

MERCHANT_REACT_ENABLED=true por padrão; `/admin/` GET redireciona para React,
POST antigo bloqueado. LEGACY_ADMIN_ENABLED=false por padrão faz o mesmo para
`/superadmin-legacy/`. Credenciais e escopo dos painéis continuam separados por
host, conforme requisitos anteriores. Ajustar explicitamente o .env existente,
pois um valor antigo false pode sobrescrever o novo padrão.

O shell mínimo Django de montagem do painel não contém a interface funcional.
Templates de emails permanecem necessários. Arquivos legados e componentes
compartilhados foram preservados para comparar paridade e para o fallback
administrativo explícito; nenhum arquivo foi removido sem comprovação.
A matriz JSON/Markdown explica a permanência de cada template. A remoção física
final depende da homologação visual e da aprovação do fim do fallback; portanto
não se declara eliminada toda existência de templates no repositório.

## Alterações e validação

Novos módulos em apps/public_ui e frontend/src/public, configs Vite público/SSR,
Dockerfile.public-ssr e testes test_package14_public.py/Commerce.test.tsx.
Views públicas importam render_public no lugar do render Django. Infraestrutura
Docker recebeu serviço SSR e dependência correspondente. O corte legado é
necessário para manter uma única interface administrativa ativa por padrão.
A suíte de legado mantém flags próprias em config.settings.test para testar
as proteções preservadas; ReactCutoverTests testa o padrão novo explicitamente.
Nenhuma asserção antiga foi removida para aprovar a suíte.

Migration orders.0014 da etapa inicial: pronto para retirada, estimativas e
preferências de mensagens. Demais migrations estão nos pacotes seguintes.

Evidências: docs/qa/package-14-public-validation.txt e final-validation.txt.
Pendências: PostgreSQL, navegador desktop/mobile, SEO/analytics reais, prova de
paridade das jornadas e teste de falha/recuperação do renderer em homologação.

CI de React ajustado para construir/iniciar SSR também no job backend, que agora
depende do renderer. Workflow não executado remotamente neste desenvolvimento.
