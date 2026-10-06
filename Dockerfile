# Released Python API; Java is used only by the unchanged Flyway migrations.
ARG FLYWAY_DISTRIBUTION_PLATFORM=linux/amd64
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS python-runtime
FROM --platform=${FLYWAY_DISTRIBUTION_PLATFORM} redgate/flyway:13.5.0@sha256:b4452f1052daf6c365352257a8b9d9aa927be00e8f3c1ac9a031ef9dd5e819d7 AS flyway
# Only the PostgreSQL migration CLI and its required loader dependencies.
# No cloud JDBC drivers, SQLFluff or .NET comparison tools are copied into the runtime.
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
# Patch the CLI's JSON parser without changing Flyway or any SQL/checksum.
ADD --checksum=sha256:7608c367fd8a92666d28711519599543c180298259963184ce04d2947a8f71e7 https://repo.maven.apache.org/maven2/tools/jackson/core/jackson-core/3.1.7/jackson-core-3.1.7.jar /minimal/lib/jackson-core-3.1.7.jar
ADD --checksum=sha256:48c781de87e2016e1f0d973748a27130f11643e7ac080173f40e2d9669d84be3 https://repo.maven.apache.org/maven2/tools/jackson/core/jackson-databind/3.1.7/jackson-databind-3.1.7.jar /minimal/lib/jackson-databind-3.1.7.jar
ADD --checksum=sha256:ad24a4f51c9a2dcb397dd1f89938fdf3c38ff48f61b85c4a4edd02fe7671fdf0 https://repo.maven.apache.org/maven2/tools/jackson/dataformat/jackson-dataformat-toml/3.1.7/jackson-dataformat-toml-3.1.7.jar /minimal/lib/jackson-dataformat-toml-3.1.7.jar
RUN chmod 0644 /minimal/lib/*.jar
# The migration distribution contains platform-independent jars; the JVM matches the target architecture.
FROM eclipse-temurin:21-jre-jammy@sha256:f04fb34e053148344e83317976114ec3f37e4b830ec8bdab5a2fe3cecd7d010b AS migration-runtime
FROM swaggerapi/swagger-ui:v5.32.11@sha256:e43eb34b978af58d8cb78e5da9c12d605cf43d113ad3a96b18f9b028d6479d68 AS swagger-ui
FROM postgres:16.15-bookworm@sha256:bb3e1a57e5407e0a5280b4211980a5e537f4abd234a87014ac979849a78dd825

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    tini util-linux libffi8 libsqlite3-0 libbz2-1.0 libexpat1 liblzma5 \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /usr/local/bin/gosu \
    && groupadd --system petstore && useradd --system --gid petstore --home-dir /app petstore

LABEL org.opencontainers.image.title="Swagger Petstore Python API" \
      org.opencontainers.image.description="Training FastAPI pet store with PostgreSQL" \
      org.opencontainers.image.source="https://github.com/AndreyMetelkin85/swagger-petstore" \
      org.opencontainers.image.licenses="Apache-2.0 AND PostgreSQL"

COPY --from=python-runtime /usr/local/ /usr/local/
# Flyway is a migration tool, not an application server; keep the existing history/checksums.
COPY --from=flyway /minimal /opt/flyway
COPY --from=migration-runtime /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PETSTORE_RESOURCE_ROOT=/app/resources \
    PETSTORE_STATIC_ROOT=/app/resources/web \
    PETSTORE_MEDIA_ROOT=/var/lib/petstore/media

WORKDIR /app
COPY pyproject.toml /app/
COPY requirements-runtime.txt /app/
COPY src /app/src
RUN python -m pip install --no-cache-dir --constraint requirements-runtime.txt .
COPY resources /app/resources
COPY --from=swagger-ui /usr/share/nginx/html/ /app/resources/web/
COPY resources/web/index.html /app/resources/web/index.html
COPY resources/web/reset-password.html /app/resources/web/reset-password.html
COPY docker/entrypoint.sh /usr/local/bin/petstore-entrypoint
COPY LICENSE /licenses/LICENSE
RUN chmod 0755 /usr/local/bin/petstore-entrypoint \
    && mkdir -p /var/lib/petstore/media \
    && chown petstore:petstore /var/lib/petstore/media \
    && chown -R petstore:petstore /app

EXPOSE 8080 5432
VOLUME ["/var/lib/petstore/media"]
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=10s --timeout=5s --start-period=120s --retries=12 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v3/health', timeout=3)"
ENTRYPOINT ["tini", "--", "/usr/local/bin/petstore-entrypoint"]
