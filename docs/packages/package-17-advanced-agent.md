# Pacote 17 — Agente avançado

Implementado para homologação, mídia desligada por padrão.

`/painel/atendimento/` e GET/POST `/api/merchant/conversations/`: conversas,
últimas mensagens, contexto preservado na transferência, referência ao carrinho
WhatsApp/pedido, assumir por 24h e retomar para a próxima mensagem.
Respeita MerchantAPI, tenant e CSRF; retomar não repete mensagens nem confirma
carrinho. A consulta de status real já existia no Pacote 13 e foi reutilizada.

ConversationEntry (migration integrations.0006) registra entrada, resposta,
transcrição, contexto de handoff e ação do operador; chave única por conversa e
mensagem protege contra repetição da task. O contexto temporário do agente
continua expirando como antes; o atendente pode consultar o registro preservado.

Áudio: recuperar bytes pelo ID na instância Evolution da loja, validar tipo e
limite, transcrever e entrar no mesmo fluxo textual do agente.
Imagem: identificação restrita a produto; passa pela consulta do catálogo,
NUNCA pelo checkout. Comprovantes não validam pagamento. Mídia inválida ou
serviço indisponível transfere para humano. Binários não são persistidos.

Configurar apenas no ambiente: WHATSAPP_MEDIA_ENABLED=true,
WHATSAPP_MEDIA_API_KEY, WHATSAPP_AUDIO_MODEL e WHATSAPP_IMAGE_MODEL.
Implementação OpenAI: /v1/audio/transcriptions e /v1/chat/completions.
Credenciais, disponibilidade dos modelos, custos e qualidade de áudio precisam
ser conferidos em homologação; nenhum serviço pago foi chamado nesta validação.
Evolution deve suportar /chat/getBase64FromMediaMessage/{instance} com key.id.
Não há download de URL recebida do cliente; limites 5 MB e 16 milhões de pixels.
Referências: https://platform.openai.com/docs/api-reference/audio/createTranscription
https://docs.evoapicloud.com/api-reference/chat-controller/get-base64

Novos arquivos: whatsapp_agent/media.py, merchant/conversations.py,
Conversations.tsx e test_package17_agent.py. Alterações necessárias: models
registra trilha; pause preserva snapshot antes de limpar contexto; task interpreta
mídia e verifica pausa antes de responder; cliente admite limite maior apenas
na chamada de mídia; rotas/navegação/settings expõem recursos.

Limites: textos antigos anteriores à migration não podem ser reconstruídos.
A transferência não envia mensagem manual pelo painel; atendente usa WhatsApp
da loja. Homologação PostgreSQL/Evolution/transcrição real pendente.

Validação do pacote: 795 testes backend OK (22 ignorados), frontend/build
aprovados; mídia testada com mocks. Revalidação final integrada: 806 testes
backend OK (22 ignorados), 34 frontend e migrations check aprovado.
