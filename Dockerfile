FROM maven:3.9-eclipse-temurin-17-alpine AS build

WORKDIR /build

COPY pom.xml ./
COPY inflector.yaml ./
COPY src ./src
RUN --mount=type=cache,target=/root/.m2 mvn -B clean package

FROM eclipse-temurin:8-jre-alpine

RUN addgroup -S petstore && adduser -S petstore -G petstore
WORKDIR /app

COPY --from=build /build/target/lib/jetty-runner.jar ./jetty-runner.jar
COPY --from=build /build/target/*.war ./server.war
COPY --from=build /build/src/main/resources/openapi.yaml ./openapi.yaml
COPY --from=build /build/inflector.yaml ./inflector.yaml

EXPOSE 8080
USER petstore

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD wget -q -O - http://localhost:8080/api/v3/health >/dev/null || exit 1

CMD ["java", "-Dconfig=/app/inflector.yaml", "-DswaggerUrl=/app/openapi.yaml", "-jar", "/app/jetty-runner.jar", "/app/server.war"]
