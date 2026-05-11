FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev curl netcat-openbsd \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala dependências primeiro (cache inteligente)
COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copia apenas o necessário
COPY . .

# Ajustes finais em uma camada
RUN chmod +x /entrypoint.sh \
    && useradd -m appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["/entrypoint.sh"]
