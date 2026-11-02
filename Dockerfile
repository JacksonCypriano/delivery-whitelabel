FROM node:22-alpine AS merchant-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Por padrão, builds diretos e builds de produção continuam executando o Vitest.
# Apenas o fluxo local dc-homolog.sh passa 0 após validar cada teste isoladamente.
ARG VDD_RUN_FRONTEND_TESTS=1
RUN if [ "$VDD_RUN_FRONTEND_TESTS" = "1" ]; then npm run test; fi && npm run build

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt

COPY . .
COPY --from=merchant-build /static/merchant /app/static/merchant
COPY --from=merchant-build /static/public /app/static/public

RUN mkdir -p /app/staticfiles /app/media \
    && chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["backend"]