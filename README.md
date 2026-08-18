# 🍕 Delivery White-label

Plataforma de **cardápio digital e delivery white-label** (multi-tenant): cada
lojista tem a sua própria loja, com marca, cores, logo e catálogo próprios.
As vendas são finalizadas via **WhatsApp** — o cliente monta o pedido no site e,
ao finalizar, é redirecionado para o WhatsApp da loja com um resumo completo já
formatado (itens, adicionais, endereço, forma de pagamento e total).

> Sem gateway de pagamento online: o fechamento acontece diretamente na conversa
> do WhatsApp entre cliente e lojista.

---

## ✨ Principais recursos

- **Multi-tenant por subdomínio** — cada loja é um `Tenant` identificado pelo
  subdomínio (ex.: `minhaloja.seudominio.com`).
- **White-label** — nome, logo, banner, cores (primária, secundária, destaque,
  fundo e texto) configuráveis por loja.
- **Catálogo** — categorias, produtos, produtos em destaque, imagens,
  adicionais/customizações e **pizza meio a meio**.
- **Carrinho e checkout** — subtotal, taxa de entrega configurável e total.
- **Venda via WhatsApp** — mensagem de pedido pronta, sem pagamento externo.
- **Painel administrativo** ([django-unfold](https://github.com/unfoldadmin/django-unfold)):
  - `admin/` — painel do **lojista** (produtos, categorias, pedidos e
    configurações da loja).
  - `superadmin/` — painel do **super administrador** (gestão de todas as lojas).
- **Gestão de pedidos** — pedidos ficam registrados no admin com filtros por
  status/data e ações em massa (confirmar, entregar, cancelar).

---

## 🧱 Stack

- **Backend:** Django 5.2 + Django REST Framework
- **Admin:** django-unfold
- **Frontend:** templates Django + Tailwind CSS (via CDN) + JavaScript modular
- **Banco de dados:** PostgreSQL
- **Fila/assíncrono:** Celery + Redis
- **Servidor:** Gunicorn (workers Uvicorn)
- **Infra:** Docker + Docker Compose

---

## 🚀 Como rodar localmente

### Pré-requisitos
- Python 3.11+
- PostgreSQL e Redis (ou use o Docker Compose, que já sobe ambos)

### Opção A — Docker Compose (recomendado)

```bash
# 1. Configure as variáveis de ambiente
cp .env.example docker/dev/.env
#   edite docker/dev/.env conforme necessário

# 2. Suba os containers (web, db, redis, celery, celery-beat)
./dc.sh up dev

# 3. Rode as migrações
./dc.sh migrate dev

# 4. Crie um superusuário
./dc.sh shell dev
#   dentro do container:
python manage.py createsuperuser
```

A aplicação ficará disponível em `http://localhost:8000`.

Comandos úteis do `dc.sh`: `up`, `down`, `rebuild`, `logs`, `shell`,
`makemigrations`, `migrate`, `restart` (ex.: `./dc.sh logs dev web`).

### Opção B — Ambiente Python local

```bash
# 1. Crie e ative um virtualenv
python -m venv venv
source venv/bin/activate

# 2. Instale as dependências
pip install -r requirements.txt

# 3. Configure as variáveis de ambiente
cp .env.example .env
#   defina DJANGO_SETTINGS_MODULE=config.settings.dev e os dados do Postgres/Redis

# 4. Exporte as variáveis (ou use um utilitário como direnv/dotenv)
export $(grep -v '^#' .env | xargs)

# 5. Migre e crie o superusuário
python manage.py migrate
python manage.py createsuperuser

# 6. Rode o servidor de desenvolvimento
python manage.py runserver
```

---

## ⚙️ Variáveis de ambiente

Todas as variáveis estão documentadas em [`.env.example`](./.env.example).
As principais:

| Variável | Descrição |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.dev` ou `config.settings.prod` |
| `DJANGO_SECRET_KEY` | Chave secreta do Django (gere uma nova) |
| `ALLOWED_HOSTS` | Hosts permitidos, separados por vírgula |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Credenciais do banco |
| `DATABASE_HOST` / `DATABASE_PORT` | Host e porta do PostgreSQL |
| `REDIS_URL` | URL do Redis (broker do Celery) |
| `SESSION_COOKIE_DOMAIN` | (Prod) domínio compartilhado entre subdomínios |

---

## 🏪 Como configurar uma loja e começar a vender

1. **Acesse o super admin** em `/superadmin/` e faça login com o superusuário.
2. **Crie um Tenant (loja)** informando `slug` (subdomínio), nome, número de
   WhatsApp, endereço, horário de funcionamento, estimativa de entrega e a
   taxa de entrega (deixe `0` para entrega grátis).
3. **Configure a marca** (BrandConfig): logo, banner e cores da loja.
4. **Acesse o painel do lojista** em `/admin/` (no subdomínio da loja) e:
   - cadastre **categorias** e **produtos** (marque "Em destaque" para destacar
     no catálogo e "Disponível" para exibir);
   - adicione imagens e adicionais/customizações;
   - para pizzas, cadastre a categoria como "Pizza"/"Pizzas" para habilitar o
     recurso de **meio a meio**.
5. **Ajuste as configurações da loja** (nome, WhatsApp, endereço, horário e taxa
   de entrega) na seção de configurações do painel.
6. **Pronto!** O cliente acessa o catálogo no subdomínio da loja, monta o pedido
   e finaliza. Ao clicar em **"Enviar Pedido via WhatsApp"**, ele é levado ao
   WhatsApp da loja com a mensagem do pedido já pronta para enviar.

### Como funciona a venda pelo WhatsApp
- O pedido é **criado no servidor** (fica registrado no admin) e, em seguida, o
  cliente é redirecionado para `https://wa.me/<numero>` com o resumo do pedido.
- O lojista recebe a mensagem, confirma com o cliente e combina o pagamento
  (Pix, dinheiro/troco, cartão na entrega) e a entrega.
- Atualize o **status do pedido** no admin (confirmado, entregue, cancelado).

---

## 📁 Estrutura do projeto

```
apps/
  accounts/    Autenticação/usuários
  core/        Modelos e utilidades base (ex.: TenantModel)
  tenants/     Multi-tenant, middleware, BrandConfig e configurações da loja
  stores/      Catálogo: categorias, produtos, imagens, adicionais
  orders/      Pedidos, itens e regras de combinação (meio a meio)
  checkout/    Carrinho e finalização (mensagem de WhatsApp)
  frontend/    Views/páginas do front público
config/
  settings/    base.py, dev.py, prod.py
  urls.py      Rotas principais
templates/     Templates Django (base, catálogo, carrinho, checkout)
static/        CSS/JS (Tailwind via CDN + JS modular)
docker/        Compose para dev e prod
```

---

## 🧪 Testes e verificações

```bash
python manage.py check          # verificação do projeto
python manage.py makemigrations --check --dry-run
pytest                          # testes (quando disponíveis)
```

---

## 📦 Deploy (produção)

- Use `DJANGO_SETTINGS_MODULE=config.settings.prod`.
- Configure `ALLOWED_HOSTS`, `DJANGO_SECRET_KEY` e, se usar subdomínios,
  `SESSION_COOKIE_DOMAIN`.
- Suba com `./dc.sh up prod` (Compose de produção em `docker/prod/`).
- O `entrypoint.sh` pode rodar migrações (`RUN_MIGRATIONS=true`) e coletar
  estáticos (`COLLECTSTATIC=true`) automaticamente.
