FROM postgres:15.19-alpine@sha256:aae6554de426ae1990f1a939ff183a0299146cf7142a6f4c379c3357af9cc2d8
# Entrypoint never changes UID: Compose starts postgres as 70:70.
# Removing the unused Go privilege helper removes its vulnerable runtime entirely.
USER 0:0
RUN rm /usr/local/bin/gosu
USER 70:70
