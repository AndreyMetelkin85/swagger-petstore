# Локальный Swagger Petstore для API-тестирования

Учебный Java API для практики ручного и автоматизированного API-тестирования. Проект
основан на оригинальном Swagger Petstore, но дополнен тестоориентированным OpenAPI
контрактом, HS256 JWT, ролями, единым форматом ошибок, серверной валидацией,
PostgreSQL, Docker Compose и smoke-тестами на Python + Pytest + httpx.

Users, pets, orders и ownership хранятся в PostgreSQL. Named volume сохраняет записи
при перезапуске или пересоздании API-контейнера.

## Что изменено относительно оригинального Petstore

- добавлены public `POST /auth/register`, `POST /auth/login` и `GET /health`;
- добавлены Bearer JWT и роли `USER`/`ADMIN`;
- добавлены self-service методы `/user/me` и просмотр собственных заказов;
- операции изменения pets и управления пользователями защищены ролью `ADMIN`;
- отсутствие/ошибка/истечение токена дают `401`, недостаточная роль — `403`;
- ошибки имеют единый JSON-контракт `status`, `error`, `message`, `details`;
- устаревшие зачёркнутые операции удалены из Swagger UI;
- все пользовательские заголовки и описания OpenAPI переведены на русский язык;
- OpenAPI содержит подробные описания, `operationId`, примеры, перечисления,
  форматы и ограничения;
- добавлена серверная runtime-валидация с единым ответом `422` и `details[]`;
- in-memory хранилища заменены JDBC-репозиториями PostgreSQL;
- идентификаторы users, pets, categories, tags и orders имеют формат UUID;
- Flyway применяет версионированные миграции без удаления существующих данных;
- Dockerfile стал multi-stage и не требует заранее выполнять Maven на хосте;
- Compose поднимает отдельные API и PostgreSQL containers с healthcheck и volume;
- добавлены Java contract tests и Pytest/httpx smoke tests.

## Стек и структура

- Java 8, Maven, WAR;
- Jetty 9 и Swagger Inflector (OpenAPI управляет маршрутизацией);
- Swagger UI 5.32.11, упакованный внутрь WAR без внешних CDN;
- PostgreSQL 16 и JDBC;
- OpenAPI 3.0.4: `src/main/resources/openapi.yaml`;
- контроллеры: `src/main/java/io/swagger/petstore/controller`;
- auth/validation services: `src/main/java/io/swagger/petstore/service`;
- JDBC repositories: `src/main/java/io/swagger/petstore/data`;
- Docker image БД: `docker/postgres/Dockerfile`;
- версия схемы и seed: `src/main/resources/db/migration`;
- модели: `src/main/java/io/swagger/petstore/model`;
- Java tests: `src/test/java`;
- AQA smoke tests: `tests/smoke`.

## Быстрый запуск через Docker Compose

Требуются Docker Desktop и Docker Compose. Команда собирает два image —
`swagger-petstore:local` и `swagger-petstore-db:local`, запускает PostgreSQL, ждёт
готовности БД и только затем запускает API:

```bash
docker compose up --build
```

В Docker Desktop внутри Compose-проекта `swagger-petstore` должны быть видны два
контейнера: `swagger-petstore` (API, порт `8080`) и `swagger-petstore-db`
(PostgreSQL, порт `5432`).

После успешного healthcheck доступны:

- Swagger UI: <http://localhost:8080>
- API base URL: <http://localhost:8080/api/v3>
- health: <http://localhost:8080/api/v3/health>
- OpenAPI JSON: <http://localhost:8080/api/v3/openapi.json>
- PostgreSQL: `localhost:5432`, database/user/password — `petstore` по умолчанию

`GET /health` проверяет и API, и соединение с PostgreSQL. У готового окружения оба поля
`status` и `database` имеют значение `UP`.

Остановка:

```bash
docker compose down
```

Обычный `down` сохраняет named volume `swagger-petstore-db-data`. Для намеренного полного
сброса локальной БД вместе со всеми тестовыми записями используйте команду ниже.
Это единственный штатный сценарий, при котором сохранённые данные удаляются:

```bash
docker compose down -v
docker compose up --build
```

Посмотреть таблицы напрямую:

```bash
docker compose exec postgres psql -U petstore -d petstore -c "SELECT id, username, role FROM users ORDER BY id;"
```

JWT secret и параметры БД можно передать через окружение или `.env`. Значения по умолчанию
предназначены только для локальной практики:

```bash
PETSTORE_TOKEN_SECRET=replace-with-a-long-local-secret docker compose up --build
```

В PowerShell:

```powershell
$env:PETSTORE_TOKEN_SECRET = "replace-with-a-long-local-secret"
docker compose up --build
```

## Локальный запуск через Maven

Требуются JDK 8+, Maven 3.9+ и PostgreSQL. БД можно оставить в Docker:

```bash
docker compose up -d postgres
mvn clean package jetty:run
```

При локальном запуске используются defaults `jdbc:postgresql://localhost:5432/petstore`
и credentials `petstore/petstore`. Их можно заменить переменными `PETSTORE_DB_URL`,
`PETSTORE_DB_USER`, `PETSTORE_DB_PASSWORD`.

Приложение запускается на порту `8080`. Docker-вариант предпочтителен: он фиксирует
среду исполнения и не требует Java/Maven на ноутбуке.

## Тестовые пользователи

| Роль | Username | Password | Назначение |
|---|---|---|---|
| ADMIN | `admin` | `admin123` | pets, inventory, управление users/orders |
| USER | `user1` | `password123` | свой профиль и свои orders |

Seed-пользователи создаются SQL-скриптом при первой инициализации volume. Пароли хранятся
открыто только потому, что это локальный disposable test service. Не
используйте эти credentials и dev JWT secret вне локальной среды.

## Авторизация

Получение USER token:

```bash
curl -sS -X POST http://localhost:8080/api/v3/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user1","password":"password123"}'
```

Ответ:

```json
{
  "accessToken": "<signed-jwt>",
  "tokenType": "Bearer",
  "expiresIn": 3600,
  "user": {
    "id": 2,
    "username": "user1",
    "email": "test@example.com",
    "role": "USER"
  }
}
```

Передавайте `accessToken` в каждом private request:

```http
Authorization: Bearer <accessToken>
```

PowerShell-пример без ручного копирования token:

```powershell
$login = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8080/api/v3/auth/login" `
  -ContentType "application/json" `
  -Body '{"username":"user1","password":"password123"}'
$headers = @{ Authorization = "Bearer $($login.accessToken)" }
Invoke-RestMethod -Uri "http://localhost:8080/api/v3/user/me" -Headers $headers
```

## Публичные и приватные endpoints

Публичные:

- `GET /health`;
- `POST /auth/register`;
- `POST /auth/login`;
- `GET /pet/findByStatus`;
- `GET /pet/findByTags`;
- `GET /pet/{petId}`.

USER/ADMIN:

- `GET`, `PUT`, `DELETE /user/me`;
- `POST /store/order`;
- `GET /store/order`;
- `GET /store/order/{orderId}` (USER видит только свой заказ).

ADMIN:

- `POST`, `PUT /pet`;
- `DELETE /pet/{petId}`;
- `GET /store/inventory`;
- `DELETE /store/order/{orderId}`;
- `GET`, `DELETE /user/{username}`.

## Примеры smoke-проверок через curl

### Регистрация

```bash
curl -i -X POST http://localhost:8080/api/v3/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"qa_engineer","password":"SecurePass123","email":"qa.engineer@example.com"}'
```

Ожидается `201 Created`. Повтор запроса с тем же username даёт `409 Conflict`.

### Вход

```bash
curl -i -X POST http://localhost:8080/api/v3/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user1","password":"password123"}'
```

Ожидается `200 OK` и `accessToken`.

### Приватный запрос без токена

```bash
curl -i http://localhost:8080/api/v3/user/me
```

Ожидается `401 Unauthorized`:

```json
{"status":401,"error":"UNAUTHORIZED","message":"Bearer access token is required","details":[]}
```

### Приватный запрос с токеном USER

При наличии `jq`:

```bash
USER_TOKEN=$(curl -sS -X POST http://localhost:8080/api/v3/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user1","password":"password123"}' | jq -r .accessToken)

curl -i http://localhost:8080/api/v3/user/me \
  -H "Authorization: Bearer $USER_TOKEN"
```

Ожидается `200 OK`.

### USER вызывает операцию, доступную только ADMIN

```bash
curl -i -X POST http://localhost:8080/api/v3/pet \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Luna","status":"available"}'
```

Ожидается `403 Forbidden`.

### Запрос с ролью ADMIN

```bash
ADMIN_TOKEN=$(curl -sS -X POST http://localhost:8080/api/v3/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | jq -r .accessToken)

curl -i -X POST http://localhost:8080/api/v3/pet \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"id":"44444444-4444-4444-8444-444444444444","name":"Luna","status":"available"}'
```

Ожидается `201 Created`.

## Проверки

Java unit/contract tests вместе со сборкой:

```bash
mvn clean test
```

Pytest/httpx smoke tests для уже запущенного приложения:

```bash
python -m pip install -r tests/smoke/requirements.txt
python -m pytest tests/smoke -v
```

Другой URL можно передать через `BASE_URL`:

```bash
BASE_URL=http://localhost:8080/api/v3 python -m pytest tests/smoke -v
```

Smoke-набор проверяет health, login, 401 без токена, 401 с неверным токеном, 403 для
USER на ADMIN endpoint, ADMIN create/delete pet и USER create/read own order.

Для ручной проверки persistence создайте пользователя или pet, перезапустите только API и
повторите GET-запрос — запись останется в PostgreSQL:

```bash
docker compose restart petstore
```

## Docker-образ и Docker Hub

Замените `<dockerhub_login>` на свой Docker Hub login. Самостоятельная публикация из
этого репозитория не выполняется.

Build image:

```bash
docker build -t <dockerhub_login>/swagger-petstore:latest .
```

Run image:

```bash
docker network create swagger-petstore-net
docker volume create swagger-petstore-db-data
docker run -d --name swagger-petstore-db --network swagger-petstore-net \
  -e POSTGRES_DB=petstore -e POSTGRES_USER=petstore -e POSTGRES_PASSWORD=petstore \
  -v swagger-petstore-db-data:/var/lib/postgresql/data \
  postgres:16-alpine

docker run --rm --name swagger-petstore --network swagger-petstore-net -p 8080:8080 \
  -e PETSTORE_TOKEN_SECRET=replace-with-a-long-local-secret \
  -e PETSTORE_DB_URL=jdbc:postgresql://swagger-petstore-db:5432/petstore \
  -e PETSTORE_DB_USER=petstore -e PETSTORE_DB_PASSWORD=petstore \
  <dockerhub_login>/swagger-petstore:latest
```

Для ежедневной локальной работы используйте `docker compose up --build`: Compose уже
содержит сеть, порядок старта, healthchecks, volume и SQL initialization.

Push image:

```bash
docker login
docker push <dockerhub_login>/swagger-petstore:latest
```

Multi-arch build and push:

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t <dockerhub_login>/swagger-petstore:latest --push .
```

## Ограничения и дальнейшие TODO

- JWT не имеет refresh/revocation flow; logout является stateless;
- локальные пароли не хешируются, а dev secret известен — это осознанно только для AQA;
- JDBC сделан компактно без connection pool; схема обновляется Flyway migrations;
- перед production-подобным использованием нужны password hashing, secret manager,
  connection pool, миграции, structured logging и полноценный security filter;
- Swagger Inflector оставлен для сохранения архитектуры fork; переход на современный
  framework был бы отдельным крупным рефакторингом.
