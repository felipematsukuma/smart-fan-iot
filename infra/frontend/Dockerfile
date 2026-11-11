FROM node:24.22.2-alpine@sha256:a34ab6d7f6f4813f4d0c5469d74685604b962fbdbf5793a7bc7b4998ecb867c8 AS builder
WORKDIR /build
COPY web-smart-fan-iot/frontend/package.json web-smart-fan-iot/frontend/package-lock.json ./
RUN npm ci
COPY web-smart-fan-iot/frontend ./
ENV VITE_APP_MODE=aiot
ARG VITE_COVERAGE=0
ENV VITE_COVERAGE=$VITE_COVERAGE
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.30.6-alpine@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03
USER 0:0
RUN apk add --no-cache --upgrade brotli-libs=1.2.1-r0
COPY --from=builder --chown=101:101 /build/dist /usr/share/nginx/html
COPY infra/frontend/nginx.conf /etc/nginx/nginx.conf
USER 101:101
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
