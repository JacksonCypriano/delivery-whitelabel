FROM node:22-alpine AS merchant-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Vitest roda no job frontend-tests do GitHub Actions antes do deploy de produção.
# O build conserva tsc e Vite; não duplica testes durante docker build.
ARG VDD_RUN_FRONTEND_TESTS=0
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
