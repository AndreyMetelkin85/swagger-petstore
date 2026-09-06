FROM postgres:16.15-alpine@sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685

LABEL org.opencontainers.image.title="Swagger Petstore PostgreSQL" \
      org.opencontainers.image.description="Hardened PostgreSQL runtime for Swagger Petstore" \
      org.opencontainers.image.source="https://github.com/AndreyMetelkin85/swagger-petstore" \
      org.opencontainers.image.licenses="PostgreSQL"

RUN apk upgrade --no-cache \
    && rm -f /usr/local/bin/gosu

USER postgres
