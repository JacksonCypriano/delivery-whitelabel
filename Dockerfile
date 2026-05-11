FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev curl netcat-openbsd \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala dependências (melhor cache)
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copia o projeto
COPY . .

# Cria diretórios necessários antes de mudar usuário
RUN mkdir -p /app/staticfiles /app/media

# Cria usuário
RUN useradd -m -d /home/appuser appuser

# Ajusta permissões
RUN chown -R appuser:appuser /app

# Garante permissão do entrypoint
RUN chmod +x /app/entrypoint.sh

USER appuser

EXPOSE 8000

CMD ["/app/entrypoint.sh"]