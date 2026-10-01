# Aquisição comercial — WhatsApp / Superadmin / Asaas / GA4

## Objetivo

Associar um contato **manual** do WhatsApp com uma loja criada pelo Superadmin e com o **primeiro pagamento real** de assinatura. O registro local nunca afirma que um clique enviou uma mensagem; o status inicial é **clique no contato (não confirmado)**. Não substitui checkout, webhook Asaas ou a conciliação financeira.

## Instalação, ambientes e privacidade

1. Aplicar pacote no repositório e **rodar testes e migrations em homologação primeiro**: `python manage.py check`, `python manage.py makemigrations --check --dry-run`, `python manage.py migrate`, `python manage.py test apps.marketplace.tests_marketing_acquisition apps.core.tests_critical.test_marketing_landing apps.core.tests_critical.test_store_merchant_onboarding --settings=config.settings.test` e a suíte crítica completa.
2. Em produção, após rodar migrations, definir:

   ```ini
   MARKETING_LEAD_TRACKING_ENABLED=true
   GOOGLE_TAG_MANAGER_ID=GTM-NGQGBHG9
   MARKETING_PUBLIC_URL=https://vemdedelivery.com.br
   MARKETING_WHATSAPP=5511964059470
   MARKETING_DEMO_URL=https://demo.vemdedelivery.com.br/
   ```

3. Em homolog/DEBUG, deixar `MARKETING_LEAD_TRACKING_ENABLED=false`, e não configurar GTM. Os hosts não canônicos também rejeitam a gravação (`404`).
4. O Google Analytics/Tag Manager **não carrega até a escolha explícita `Aceitar métricas`** na landing comercial. A escolha pode ser alterada em **Preferências de métricas** no rodapé; recusando, o WhatsApp e a referência continuam funcionando normalmente. Uma pessoa que já aceitara analytics antes desta versão verá a nova decisão de consentimento, não a antiga. Revisar a aplicação de consentimento no GTM/Google Ads antes de ativar tags adicionais. A política de privacidade comercial foi atualizada.

## Fluxo operacional

- A landing e as páginas SEO geram referência `VDD-XXXXXXXXXX`, sem escrita no banco por mera visualização.
- Um clique abre o WhatsApp com `Referência: VDD-...` pré-preenchida. Um `sendBeacon` protegido por token assinado, validade 30 min e CSRF registra o **clique**, não a mensagem enviada. Se o beacon falhar, o código chega na mensagem e o Superadmin poderá criar o vínculo `manual_unverified` (sem atribuição).
- UTMs, `gclid`, `gbraid`, `wbraid` e Client ID GA4 só são retidos se a pessoa escolher **Aceitar métricas**. A primeira campanha consentida é guardada na aba (sessionStorage), não como dado pessoal em WhatsApp ou Analytics. Não enviar mensagens, e-mail, telefone ou nome aos eventos GA4.
- Ao receber a mensagem comercial e confirmar um atendimento real, entre no **Superadmin → Marketplace → Leads comerciais / WhatsApp**; procure a referência e marque **Qualificado** se o contato for legítimo. O clique isolado não é qualificado.
- No formulário **Superadmin → Cadastrar Loja + Usuário**, preencher `Referência do contato (WhatsApp)` com o código. Também pode vincular na edição de loja. Código desconhecido permanece com origem **manual_unverified**, sem presumir Google Ads. Um código já vinculado não pode ser reutilizado em outra loja.
- `lead_qualified` é registrado apenas após confirmação humana. `signup_completed` é criado localmente no vínculo do cadastro real; `subscription_created` quando há cobrança inicial emitida (PENDING/PAID); `subscription_paid` **somente** na primeira cobrança validada como PAID pela conciliação do billing, em ambiente Asaas production, `months > 0` e não serviço adicional. Cortesia/manual credit, cobrança pendente e renovações não se tornam novas aquisições.
- A persistência é idempotente por `lead + etapa` e por `lead/invoice` do primeiro pagamento. O webhook não envia nada ao Google; o processamento externo é separado do financeiro.
- Estorno/revisão marca o registro local como `retracted_at` e interrompe novos envios. Se já tiver sido enviado ao Google, realizar ajuste/retração no Google Ads/Analytics conforme suas ferramentas (o pacote **não** remove automaticamente eventos já recebidos pelo Google).

## Enviar GA4 por Measurement Protocol (opcional)

No GA4 em **Administrador → Fluxos de dados → VemDeDelivery - Produção → Chaves secretas da API Measurement Protocol**, gerar uma nova chave privada. Configurar apenas no `.env` do servidor:

```ini
MARKETING_GA4_MEASUREMENT_ID=G-4BEY70BSG5
MARKETING_GA4_API_SECRET=<CHAVE_SECRET_API_GA4>
```

Rodar em homolog (sem API secret) somente a conciliação local:

```bash
python manage.py send_marketing_conversions --reconcile-only
```

Após testar eventos de **consentimento real e compra real** em produção, executar:

```bash
python manage.py send_marketing_conversions
```

O comando envia `lead_qualified`, `signup_completed`, `subscription_created` e `subscription_paid` quando existe consentimento e um Client ID GA4 válido. Não envia eventos antigos que excedam ~70h, devido ao limite de retroatividade do GA4. O retorno HTTP 2xx não garante validação do conteúdo: verificar o Measurement Protocol Validation Server/DebugView/relatórios. Erros de rede são retidos para inspeção, sem retry automático de situações ambíguas; após confirmar a situação, existe `--retry-errors`. Somente depois automatizar por cron/beat com periodicidade adequada, fora do processamento do webhook financeiro.

**Atenção:** o envio GA4 por Measurement Protocol não é uma importação automática de conversões offline no Google Ads nem garante atribuição da campanha. Para otimizar Ads por pagamentos reais é necessário criar a conversão offline no Ads e configurar sua importação por identificadores de clique consentidos, observando janela e limites do Google Ads. Atribuição sem `gclid`/consentimento não deve ser inventada.

## Google Ads — preparar exportação manual

Após criar a ação de conversão no Ads, use o mesmo nome e gere CSV de eventos de **primeira assinatura paga** consentidos com `gclid`:

```bash
python manage.py export_marketing_ads --name 'VemDeDelivery - Primeiro pagamento' > ads-conversoes.csv
```

Esse arquivo pode conter IDs de anúncio sensíveis: proteja o acesso. Verifique o formato e restrições do importador Google Ads antes de subir. `gbraid/wbraid` não equivalem diretamente a gclid em todos os fluxos e não são exportados nesse CSV. **Não** automatizar upload de Ads nem configurar otimização por esses eventos antes de validar as campanhas, o consentimento e as conversões reais.

## Retenção, diagnóstico e segurança

```bash
python manage.py purge_marketing_leads
```

Remove cliques **sem loja vinculada** com mais de 90 dias. Leads vinculados e registros fiscais/financeiros seguem suas políticas contratuais/legais; revise a retenção e exclusão conforme LGPD e acordos de terceiros. Sem dados analíticos consentidos não há GA4 Client ID para relacionar o pagamento a sessões.

Se o Google Tag Assistant não conectar depois da implantação, confirme primeiro que o visitante aceitou as métricas na página comercial. Não espere tags em homolog, `/superadmin/`, `/admin/` ou catálogos dos tenants.

**Segurança do projeto ZIP:** nunca incluir `.secrets/`, certificados privados em `deploy/nginx/certs/`, `.env`, dumps ou tokens nos próximos compartilhamentos.
