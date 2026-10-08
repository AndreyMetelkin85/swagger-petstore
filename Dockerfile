# Бэкенд FastAPI. Java используется только для неизменённых миграций Flyway.
ARG FLYWAY_DISTRIBUTION_PLATFORM=linux/amd64
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS python-runtime
FROM --platform=${FLYWAY_DISTRIBUTION_PLATFORM} python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS migration-artifacts
COPY docker/fetch_migration_artifacts.py /fetch_migration_artifacts.py
RUN python /fetch_migration_artifacts.py
FROM --platform=${FLYWAY_DISTRIBUTION_PLATFORM} redgate/flyway:13.5.0@sha256:b4452f1052daf6c365352257a8b9d9aa927be00e8f3c1ac9a031ef9dd5e819d7 AS flyway
# Только CLI миграций PostgreSQL и необходимые ему зависимости.
RUN mkdir -p /minimal/lib/flyway /minimal/drivers /minimal/conf \
    && cp /flyway/flyway /minimal/flyway \
    && cp -r /flyway/licenses /minimal/licenses \
    && for module in core core-utilities commandline command-mcp mcp-server database-postgresql verb-info verb-migrate verb-validate verb-baseline; do \
         cp "/flyway/lib/flyway/flyway-${module}-13.5.0.jar" /minimal/lib/flyway/; \
       done \
    && cp -r /flyway/lib/mcp /minimal/lib/mcp \
    && cp /flyway/drivers/postgresql-42.7.12.jar /minimal/drivers/ \
    && cp /flyway/lib/jackson-annotations-2.22.jar \
          /flyway/lib/commons-text-1.10.0.jar /flyway/lib/jansi-4.3.1.jar \
          /flyway/lib/slf4j-nop-1.7.30.jar /minimal/lib/
# Обновляем JSON-парсер CLI без изменения Flyway, SQL и контрольных сумм миграций.
COPY --from=migration-artifacts /migration-artifacts/ /minimal/lib/
RUN chmod 0644 /minimal/lib/*.jar
# JAR не зависит от платформы; JVM соответствует архитектуре конечного образа.
FROM eclipse-temurin:21-jre-jammy@sha256:f04fb34e053148344e83317976114ec3f37e4b830ec8bdab5a2fe3cecd7d010b AS migration-runtime
FROM swaggerapi/swagger-ui:v5.32.11@sha256:e43eb34b978af58d8cb78e5da9c12d605cf43d113ad3a96b18f9b028d6479d68 AS swagger-ui
FROM python-runtime

ARG SECURITY_UPDATE_EPOCH=local
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    tini util-linux \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system petstore && useradd --system --gid petstore --home-dir /app petstore

LABEL org.opencontainers.image.title="Lapki FastAPI backend" \
      org.opencontainers.image.description="Python API and compatible Flyway migration tools" \
      org.opencontainers.image.source="https://github.com/AndreyMetelkin85/swagger-petstore" \
      org.opencontainers.image.licenses="Apache-2.0 AND PostgreSQL AND CC0-1.0 AND CC-BY-SA-2.0 AND LicenseRef-Public-Domain"

# Миграции запускает отдельный сервис Compose из этого же образа.
COPY --from=flyway /minimal /opt/flyway
COPY --from=migration-runtime /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PETSTORE_RESOURCE_ROOT=/app/resources \
    PETSTORE_STATIC_ROOT=/app/resources/web \
    PETSTORE_MEDIA_ROOT=/var/lib/petstore/media \
    PETSTORE_DEMO_CATALOG=true

WORKDIR /app
COPY --chown=petstore:petstore pyproject.toml /app/
COPY requirements-runtime.txt /app/
RUN python -m pip install --no-cache-dir --requirement requirements-runtime.txt
COPY --from=swagger-ui --chown=petstore:petstore /usr/share/nginx/html/ /app/resources/web/
COPY --chown=petstore:petstore src /app/src
RUN python -m pip install --no-cache-dir --no-deps .
COPY --chown=petstore:petstore resources /app/resources
COPY docker/entrypoint.sh /usr/local/bin/petstore-entrypoint
COPY docker/api_health.py /usr/local/bin/petstore-api-health.py
COPY LICENSE /licenses/LICENSE
RUN chmod 0755 /usr/local/bin/petstore-entrypoint \
    && mkdir -p /var/lib/petstore/media \
    && chown petstore:petstore /var/lib/petstore/media

EXPOSE 8080
VOLUME ["/var/lib/petstore/media"]
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=10s --timeout=5s --start-period=120s --retries=12 \
    CMD python /usr/local/bin/petstore-api-health.py
ENTRYPOINT ["tini", "--", "/usr/local/bin/petstore-entrypoint"]
