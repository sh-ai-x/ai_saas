FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY foundation ./foundation
COPY lib ./lib
COPY services ./services
COPY evaluators ./evaluators
COPY packages/contracts ./packages/contracts
COPY config ./config
COPY infra ./infra

RUN python -m foundation.contract_check

RUN addgroup --system app && adduser --system --ingroup app app && chown -R app:app /app
USER app

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)"
CMD ["python", "-m", "foundation.server", "--env-file", "/app/config/profiles/free-portfolio.example.env", "--profile", "free-portfolio", "--host", "0.0.0.0", "--port", "8080"]
