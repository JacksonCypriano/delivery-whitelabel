FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git libpq-dev curl netcat-openbsd \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY . /app

# Copiar e ajustar permissões ANTES de trocar de usuário
COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Criar usuário e ajustar permissões
RUN useradd -m -d /home/appuser appuser || true
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
ENV PORT=8000

CMD ["/entrypoint.sh"]
