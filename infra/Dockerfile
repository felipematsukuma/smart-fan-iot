FROM python:3.11.18-slim-bookworm@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39 AS builder
WORKDIR /build
COPY web-smart-fan-iot/backend/requirements.txt web-smart-fan-iot/backend/requirements.lock ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt
COPY packages/smartfan_common ./packages/smartfan_common
RUN pip wheel --no-cache-dir -c requirements.lock --wheel-dir /wheels './packages/smartfan_common[reliability]'

FROM python:3.11.18-slim-bookworm@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=builder /wheels /wheels
COPY web-smart-fan-iot/backend/requirements.txt web-smart-fan-iot/backend/requirements.lock /tmp/
RUN pip install --no-index --find-links=/wheels -r /tmp/requirements.txt 'smartfan-common[reliability]==0.8.0' && rm -rf /wheels
COPY infra ./infra
COPY services ./services
COPY web-smart-fan-iot/backend/app ./app
USER 10001:10001
CMD ["python", "-m", "infra.bootstrap"]
