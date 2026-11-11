FROM python:3.11.18-slim-trixie@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535 AS builder
WORKDIR /build
COPY web-smart-fan-iot/backend/requirements.txt web-smart-fan-iot/backend/requirements.lock ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt
COPY packages/smartfan_common ./packages/smartfan_common
RUN pip wheel --no-cache-dir -c requirements.lock --wheel-dir /wheels './packages/smartfan_common[reliability]'

FROM python:3.11.18-slim-trixie@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535 AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=builder /wheels /wheels
COPY web-smart-fan-iot/backend/requirements.txt web-smart-fan-iot/backend/requirements.lock /tmp/
RUN pip install --no-index --find-links=/wheels -r /tmp/requirements.txt 'smartfan-common[reliability]==0.14.0' && rm -rf /wheels
COPY infra ./infra
COPY services ./services
COPY web-smart-fan-iot/backend/app ./app
USER 10001:10001
CMD ["python", "-m", "infra.bootstrap"]

# Optional test target: production services keep the runtime stage above.
FROM runtime AS qa
USER 0:0
RUN pip install --no-cache-dir --no-deps coverage==7.17.2 pytest-cov==7.1.0
USER 10001:10001
