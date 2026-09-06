FROM maven:3.9-eclipse-temurin-17-alpine@sha256:c7baad7b0d2c869227cda4a574cb4b218781c80632bb5afce2282db8e5f7f0bc AS build

WORKDIR /build

COPY pom.xml ./
COPY inflector.yaml ./
COPY src ./src
RUN --mount=type=cache,target=/root/.m2 mvn -B clean package

FROM tomcat:9.0.121-jre17-temurin-noble@sha256:e04a0353442f403a24763b5112d597aee03af8eb420775deedd039220afbcb35

LABEL org.opencontainers.image.title="Swagger Petstore API" \
      org.opencontainers.image.description="Training pet store API" \
      org.opencontainers.image.source="https://github.com/AndreyMetelkin85/swagger-petstore" \
      org.opencontainers.image.licenses="Apache-2.0"

RUN groupadd --system --gid 10001 petstore \
    && useradd --system --uid 10001 --gid petstore --home-dir /nonexistent \
        --shell /usr/sbin/nologin petstore \
    && rm -rf /usr/local/tomcat/webapps/* /usr/local/tomcat/webapps.dist \
    && mkdir -p /app /licenses \
    && chown -R petstore:petstore /app /licenses /usr/local/tomcat
WORKDIR /app

COPY --from=build --chown=petstore:petstore /build/target/*.war /usr/local/tomcat/webapps/ROOT.war
COPY --from=build --chown=petstore:petstore /build/src/main/resources/openapi.yaml ./openapi.yaml
COPY --from=build --chown=petstore:petstore /build/inflector.yaml ./inflector.yaml
COPY --chown=petstore:petstore LICENSE /licenses/LICENSE

EXPOSE 8080
ENV CATALINA_OPTS="-Dconfig=/app/inflector.yaml -DswaggerUrl=/app/openapi.yaml"
USER petstore

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD curl --fail --silent --show-error http://localhost:8080/api/v3/health >/dev/null || exit 1

CMD ["catalina.sh", "run"]
