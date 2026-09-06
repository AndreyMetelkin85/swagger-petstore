# Локальный Swagger Petstore для API-тестирования

Учебный Java API для практики ручного и автоматизированного API-тестирования. В нём
можно регистрировать и подтверждать пользователей, управлять профилем, искать питомцев,
создавать заказы и проверять реалистичные успешные и ошибочные сценарии.

Users, pets, orders и ownership хранятся в PostgreSQL. Named volume сохраняет записи
при перезапуске или пересоздании API-контейнера.

## Что изменено относительно оригинального Petstore

- регистрация и авторизация разделены на самостоятельные группы операций;
- добавлены подтверждение регистрации, повторная выдача ссылки и восстановление пароля;
- учётная запись проходит состояния `PENDING`, `ACTIVE`, `BLOCKED`;
- добавлены Bearer JWT и роли `USER`/`ADMIN`;
- смена пароля и блокировка немедленно отзывают ранее выданные Bearer tokens;
- новые пароли хранятся как BCrypt, старые обновляются при успешной авторизации;
- добавлены self-service методы `/user/me` и просмотр собственных заказов;
- ID новых питомцев и заказов создаются сервером, create-модели отделены от update-моделей;
- один питомец может иметь только один активный заказ, резервирование выполняется атомарно;
- изменения питомца защищены версией записи: устаревший `PUT` получает `409 PET_VERSION_CONFLICT`;
- заказ проходит состояния `placed`, `approved`, `shipped`, `delivered` или `cancelled`;
- создание заказа резервирует питомца, отмена снимает резерв, доставка переводит его в `sold`;
- пользователи и заказы не удаляются через API, поэтому профиль владельца и история покупок не теряются;
- операции изменения pets и управления пользователями защищены ролью `ADMIN`;
- отсутствие/ошибка/истечение токена дают `401`, недостаточная роль — `403`;
- ошибки имеют единый JSON-контракт `status`, `error`, `message`, `details`;
- устаревшие зачёркнутые операции удалены из Swagger UI;
- разделы Swagger имеют английские названия, а операции — нейтральные русские названия;
- OpenAPI содержит подробные описания, `operationId`, примеры, перечисления,
  форматы и ограничения;
- добавлена endpoint-specific runtime-валидация с ответом `422` и `details[]`;
- in-memory хранилища заменены JDBC-репозиториями PostgreSQL;
- идентификаторы users, pets, categories, tags и orders имеют формат UUID;
- статусы аккаунтов, питомцев и заказов представлены PostgreSQL ENUM;
- Flyway применяет версионированные миграции без удаления существующих данных;
- внешние ключи запрещают удаление владельца заказа, а уникальный индекс не допускает два активных заказа на одного питомца;
- Dockerfile стал multi-stage и не требует заранее выполнять Maven на хосте;
- Compose публикует API только на loopback, оставляет PostgreSQL во внутренней сети и хранит БД в отдельном named volume;
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
контейнера: `swagger-petstore` (API, `127.0.0.1:8080`) и `swagger-petstore-db`.
Порт PostgreSQL доступен только контейнерам во внутренней Compose-сети и не публикуется
на хост.

После успешного healthcheck доступны:

- Swagger UI: <http://localhost:8080>
- API base URL: <http://localhost:8080/api/v3>
- health: <http://localhost:8080/api/v3/health>
- OpenAPI JSON: <http://localhost:8080/api/v3/openapi.json>

`GET /health` проверяет и API, и соединение с PostgreSQL. У готового окружения оба поля
`status` и `database` имеют значение `UP`.

Остановка:

```bash
docker compose down
```

Обычный `down` сохраняет named volume `swagger-petstore-db-data`. Имя можно переопределить
через `PETSTORE_DB_VOLUME`, чтобы разные ветки не использовали одну и ту же БД. Для намеренного полного
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

JWT secret, публичный адрес одноразовых ссылок и параметры БД можно передать через
окружение или `.env`. Если `PETSTORE_TOKEN_SECRET` не задан, при каждом запуске создаётся
случайный 256-битный secret: токены прежнего процесса после рестарта становятся
недействительными. Для стабильных токенов задайте собственный secret длиной не менее
32 байт:

```bash
PETSTORE_TOKEN_SECRET=replace-with-a-long-local-secret docker compose up --build
```

В PowerShell:

```powershell
$env:PETSTORE_TOKEN_SECRET = "replace-with-a-long-local-secret"
$env:PETSTORE_PUBLIC_BASE_URL = "http://localhost:8080/api/v3"
docker compose up --build
```

`resetUrl` по умолчанию не возвращается из `POST /auth/password/forgot`. Для изолированных
учебных прогонов, в которых тест должен сам перейти по ссылке, явно установите
`PETSTORE_EXPOSE_TEST_LINKS=true`. Не включайте этот флаг в общем окружении.

## Локальный запуск через Maven

Требуются JDK 8+, Maven 3.9+ и PostgreSQL. Compose по умолчанию не публикует порт БД;
для запуска приложения вне Docker используйте отдельный локальный PostgreSQL или временно
опубликуйте порт только на loopback:

```bash
docker compose run -d --name swagger-petstore-db-dev -p 127.0.0.1:5432:5432 postgres
mvn clean package jetty:run
```

При локальном запуске используются defaults `jdbc:postgresql://localhost:5432/petstore`
и credentials `petstore/petstore`. Их можно заменить переменными `PETSTORE_DB_URL`,
`PETSTORE_DB_USER`, `PETSTORE_DB_PASSWORD`.

Приложение запускается на порту `8080`. Docker-вариант предпочтителен: он фиксирует
среду исполнения и не требует Java/Maven на ноутбуке.

## Предзагруженные демонстрационные пользователи

| Роль | Username | Password | Назначение |
|---|---|---|---|
| ADMIN | `admin` | `admin123` | pets, inventory, управление users/orders |
| USER | `user1` | `password123` | свой профиль и свои orders |

Эти пользователи создаются только при первой инициализации volume. Их исходные пароли
автоматически заменяются BCrypt-хешами при первом успешном входе. Не используйте эти
credentials вне локальной среды.

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
  "access_token": "<signed-jwt>",
  "token_type": "Bearer",
  "expires_in": 3600,
  "user": {
    "id": "b9ec3485-6954-4faf-813b-1c9d25ea750c",
    "username": "user1",
    "email": "test@example.com",
    "userStatus": "ACTIVE",
    "role": "USER"
  }
}
```

Передавайте Bearer token в каждом приватном запросе:

```http
Authorization: Bearer <access_token>
```

PowerShell-пример без ручного копирования token:

```powershell
$login = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8080/api/v3/auth/login" `
  -ContentType "application/json" `
  -Body '{"username":"user1","password":"password123"}'
$headers = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod -Uri "http://localhost:8080/api/v3/user/me" -Headers $headers
```

## Публичные и приватные endpoints

Публичные:

- `GET /health`;
- `POST /auth/register`;
- `GET /auth/confirm/{userId}`;
- `POST /auth/confirmation/resend`;
- `POST /auth/login`;
- `POST /auth/password/forgot`;
- `POST /auth/password/reset/{userId}`;
- `GET /pet/findByStatus`;
- `GET /pet/findByTags`;
- `GET /pet/{petId}`.

USER/ADMIN:

- `GET`, `PUT /user/me`;
- `POST /store/order`;
- `GET /store/order`;
- `GET /store/order/{orderId}` (USER видит только свой заказ).
- `POST /store/order/{orderId}/cancel` (USER отменяет только свой заказ).

ADMIN:

- `POST`, `PUT /pet`;
- `DELETE /pet/{petId}`;
- `GET /store/inventory`;
- `POST /store/order/{orderId}/approve`;
- `POST /store/order/{orderId}/ship`;
- `POST /store/order/{orderId}/deliver`;
- `GET /user/{username}`;
- `POST /admin/users/{userId}/block`;
- `POST /admin/users/{userId}/unblock`.

## Примеры smoke-проверок через curl

### Регистрация

```bash
curl -i -X POST http://localhost:8080/api/v3/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"qa_engineer","password":"SecurePass123","email":"qa.engineer@example.com"}'
```

Ожидается `201 Created`, пользователь со статусом `PENDING` и одноразовая
`confirmationUrl`. После запроса этой ссылки статус станет `ACTIVE`. Повтор регистрации
с тем же username или email даёт `409 Conflict`.

### Вход

```bash
curl -i -X POST http://localhost:8080/api/v3/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user1","password":"password123"}'
```

Ожидается `200 OK` и `access_token`.

### Приватный запрос без токена

```bash
curl -i http://localhost:8080/api/v3/user/me
```

Ожидается `401 Unauthorized`:

```json
{"status":401,"error":"UNAUTHORIZED","message":"Bearer token is required","details":[]}
```

### Приватный запрос с токеном USER

При наличии `jq`:

```bash
USER_TOKEN=$(curl -sS -X POST http://localhost:8080/api/v3/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user1","password":"password123"}' | jq -r .access_token)

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
  -d '{"username":"admin","password":"admin123"}' | jq -r .access_token)

curl -i -X POST http://localhost:8080/api/v3/pet \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Luna","status":"available"}'
```

Ожидается `201 Created`; UUID питомца создаётся сервером. В ответе также приходит
`version`. При `PUT /pet` клиент передаёт текущую версию, а успешное обновление увеличивает
её на единицу. Это предотвращает незаметное перезаписывание чужих параллельных изменений.

### Жизненный цикл заказа

Новый заказ создаётся в состоянии `placed`, после чего администратор последовательно
переводит его в `approved`, `shipped` и `delivered`. Заказ можно отменить из состояний
`placed` и `approved`. Питомец в активном заказе имеет статус `reserved`; после отмены
он снова становится `available`, после доставки — `sold`.

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

31 smoke-сценарий проверяет health, авторизацию, регистрацию и подтверждение,
восстановление пароля, блокировку, отзыв старых tokens, роли, питомцев, заказы и
единый формат ошибок для некорректных входных данных. Параллельные запросы отдельно
проверяют атомарность подтверждения, сброса пароля, блокировки, разблокировки и
резервирования одного питомца. Также проверяются запрет destructive user/order operations,
невозможность подделать ADMIN token старым публичным secret и optimistic lock питомца.

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

docker run --rm --name swagger-petstore --network swagger-petstore-net -p 127.0.0.1:8080:8080 \
  -e PETSTORE_TOKEN_SECRET=replace-with-a-long-local-secret \
  -e PETSTORE_PUBLIC_BASE_URL=http://localhost:8080/api/v3 \
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

- JWT не имеет refresh flow; для отзыва используется внутренняя версия token;
- при автоматически сгенерированном JWT secret все Bearer tokens отзываются после рестарта API;
- JDBC сделан компактно без connection pool; схема обновляется Flyway migrations;
- recovery-ссылки возвращаются клиенту только в явно включённом учебном режиме;
- демонстрационные credentials и выдача confirmation-ссылки в ответе предназначены только
  для локального обучения;
- перед production-подобным использованием нужны TLS/reverse proxy, secret manager,
  rate limiting, connection pool, доставка ссылок через почту, аудит и structured logging;
- Swagger Inflector оставлен для сохранения архитектуры fork; переход на современный
  framework был бы отдельным крупным рефакторингом.
