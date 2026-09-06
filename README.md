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
- сброс пароля, блокировка и административное изменение профиля немедленно отзывают ранее выданные Bearer tokens;
- новые пароли хранятся как BCrypt, старые обновляются при успешной авторизации;
- добавлены self-service методы `/user/me`, административное управление профилями и просмотр заказов с учётом роли;
- email, username и роль меняет только администратор; пароль меняется исключительно через восстановление пароля;
- ID новых питомцев и заказов создаются сервером, create-модели отделены от update-моделей;
- один питомец может иметь только один активный заказ, резервирование выполняется атомарно;
- изменения питомца защищены версией записи: устаревший `PUT` получает `409 PET_VERSION_CONFLICT`;
- заказ проходит состояния `placed`, `approved`, `shipped`, `delivered` или `cancelled`;
- создание заказа резервирует питомца, отмена снимает резерв, доставка переводит его в `sold`;
- профиль хранит один российский адрес, а заказ — неизменяемый снимок контактов и доставки;
- цена питомца хранится в рублях и фиксируется в заказе на момент оформления;
- добавлен локальный симулятор тестовых платежей с idempotency, отказами, refund и истечением резерва;
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
- Compose публикует API и PostgreSQL только на loopback и хранит БД в отдельном named volume;
- добавлены Java contract tests и Pytest/httpx smoke tests.

## Стек и структура

- Java 17, Maven, WAR;
- Tomcat 9 и Swagger Inflector (OpenAPI управляет маршрутизацией);
- Swagger UI 5.32.11, упакованный внутрь WAR без внешних CDN;
- PostgreSQL 16 и JDBC;
- OpenAPI 3.0.4: `src/main/resources/openapi.yaml`;
- контроллеры: `src/main/java/io/swagger/petstore/controller`;
- auth/validation services: `src/main/java/io/swagger/petstore/service`;
- JDBC repositories: `src/main/java/io/swagger/petstore/data`;
- Docker image БД: `docker/postgres/Dockerfile`;
- единый Docker image API + PostgreSQL: `Dockerfile.all-in-one`;
- версия схемы и seed: `src/main/resources/db/migration`;
- модели: `src/main/java/io/swagger/petstore/model`;
- Java tests: `src/test/java`;
- AQA smoke tests: `tests/smoke`.

## Быстрый запуск через Docker Compose

Требуются Docker Desktop и Docker Compose. Основной Compose скачивает проверенные
`andymentor/swagger-petstore:dev` и `andymentor/swagger-petstore-db:16.15`, ждёт
готовности БД и только затем запускает API:

```bash
docker compose up -d
```

Для разработки из локальных исходников подключите overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

## Запуск одним Docker-образом

Для учебного локального запуска API и PostgreSQL доступны в одном контейнере. Docker
автоматически создаст named volume и сохранит в нём данные между перезапусками:

```bash
docker run -d --name swagger-petstore-all-in-one --restart unless-stopped \
  -p 127.0.0.1:8080:8080 \
  -p 127.0.0.1:5432:5432 \
  -v swagger-petstore-all-in-one-data:/var/lib/postgresql/data \
  andymentor/swagger-petstore:dev-all-in-one
```

Остановить и снова запустить тот же контейнер без потери данных:

```bash
docker stop swagger-petstore-all-in-one
docker start swagger-petstore-all-in-one
```

All-in-one предназначен для быстрого учебного запуска. Основной Compose-вариант
оставляет API и PostgreSQL отдельными сервисами.

В Docker Desktop внутри Compose-проекта `swagger-petstore` должны быть видны два
контейнера: `swagger-petstore` (API, `127.0.0.1:8080`) и `swagger-petstore-db`.
PostgreSQL опубликован только на loopback: `127.0.0.1:${POSTGRES_PORT:-5432}`. Он
недоступен из внешней сети; порт можно переопределить переменной `POSTGRES_PORT`.

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
docker compose up -d
```

Посмотреть таблицы напрямую:

```bash
docker compose exec postgres psql -U petstore -d petstore -c "SELECT id, username, role FROM users ORDER BY id;"
```

Параметры подключения к PostgreSQL с хоста:

| Параметр | Значение |
|---|---|
| Host | `localhost` |
| Port | `5432` или значение `POSTGRES_PORT` |
| Database | `petstore` |
| Username | `petstore` |
| Password | `petstore` |
| JDBC URL | `jdbc:postgresql://localhost:5432/petstore` |

Это учебные credentials. Порт привязан к `127.0.0.1` и не доступен извне компьютера.

JWT secret, публичный адрес одноразовых ссылок и параметры БД можно передать через
окружение или `.env`. Если `PETSTORE_TOKEN_SECRET` не задан, при каждом запуске создаётся
случайный 256-битный secret: токены прежнего процесса после рестарта становятся
недействительными. Для стабильных токенов задайте собственный secret длиной не менее
32 байт:

```bash
PETSTORE_TOKEN_SECRET=replace-with-a-long-local-secret docker compose up -d
```

В PowerShell:

```powershell
$env:PETSTORE_TOKEN_SECRET = "replace-with-a-long-local-secret"
$env:PETSTORE_PUBLIC_BASE_URL = "http://localhost:8080/api/v3"
docker compose up -d
```

`resetUrl` по умолчанию не возвращается из `POST /auth/password/forgot`. Для изолированных
учебных прогонов, в которых тест должен сам перейти по ссылке, явно установите
`PETSTORE_EXPOSE_TEST_LINKS=true`. Не включайте этот флаг в общем окружении.

## Сборка через Maven

Для проверки без запуска контейнеров требуются JDK 17 и Maven 3.9+:

```bash
mvn clean package
```

Для запуска приложения используйте Docker Compose: runtime стандартизован на Tomcat 9
и не требует локальной настройки application server.

## Предзагруженные демонстрационные пользователи

| Роль | Email | Username | Password | Назначение |
|---|---|---|---|---|
| ADMIN | `admin@example.com` | `admin` | `admin123` | pets, inventory, управление users/orders |
| USER | `test@example.com` | `user1` | `password123` | свой профиль и свои orders |

Эти пользователи создаются только при первой инициализации volume. Их исходные пароли
автоматически заменяются BCrypt-хешами при первом успешном входе. Не используйте эти
credentials вне локальной среды.

## Авторизация

Получение USER token:

```bash
curl -sS -X POST http://localhost:8080/api/v3/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}'
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
  -Body '{"email":"test@example.com","password":"password123"}'
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

- `GET`, `PUT /user/me` (`PUT` изменяет только firstName, lastName и phone);
- `POST /store/order`;
- `GET /store/order`;
- `GET /store/order/{orderId}` (USER видит только свой заказ).
- `POST /store/order/{orderId}/cancel` (USER отменяет только свой заказ).

ADMIN:

- `POST /pet`;
- `PUT`, `DELETE /pet/{petId}`;
- `GET /store/inventory`;
- `POST /store/order/{orderId}/approve`;
- `POST /store/order/{orderId}/ship`;
- `POST /store/order/{orderId}/deliver`;
- `GET /users`;
- `GET`, `PUT /users/{userId}`;
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
  -d '{"email":"test@example.com","password":"password123"}'
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
  -d '{"email":"test@example.com","password":"password123"}' | jq -r .access_token)

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
  -d '{"email":"admin@example.com","password":"admin123"}' | jq -r .access_token)

curl -i -X POST http://localhost:8080/api/v3/pet \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Luna","status":"available"}'
```

Ожидается `201 Created`; UUID питомца создаётся сервером. В ответе также приходит
`version`. При `PUT /pet/{petId}` клиент передаёт текущую версию, а успешное обновление увеличивает
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

44 smoke-сценария проверяют health, авторизацию, регистрацию и подтверждение,
восстановление пароля, блокировку, отзыв старых tokens, роли, питомцев, заказы и
платежи, а также единый формат ошибок для некорректных входных данных. Параллельные запросы отдельно
проверяют атомарность подтверждения, сброса пароля, блокировки, разблокировки и
резервирования и оплаты. Также проверяются запрет destructive user/order operations,
невозможность подделать ADMIN token старым публичным secret и optimistic lock питомца.

Для ручной проверки persistence создайте пользователя или pet, перезапустите только API и
повторите GET-запрос — запись останется в PostgreSQL:

```bash
docker compose restart petstore
```

## Docker-образ и Docker Hub

Публичные dev-образы публикуются в `andymentor/swagger-petstore` и
`andymentor/swagger-petstore-db`. Они собираются только из проверенного commit ветки
`dev`; upstream-образы `swaggerapi/petstore3` не используются.

Build image:

```bash
docker build --pull -t andymentor/swagger-petstore:dev .
docker build --pull -t andymentor/swagger-petstore-db:16.15 docker/postgres
```

Run image:

```bash
docker network create swagger-petstore-net
docker volume create swagger-petstore-db-data
docker run -d --name swagger-petstore-db --network swagger-petstore-net \
  -e POSTGRES_DB=petstore -e POSTGRES_USER=petstore -e POSTGRES_PASSWORD=petstore \
  -v swagger-petstore-db-data:/var/lib/postgresql/data \
  -p 127.0.0.1:5432:5432 \
  andymentor/swagger-petstore-db:16.15

docker run --rm --name swagger-petstore --network swagger-petstore-net -p 127.0.0.1:8080:8080 \
  -e PETSTORE_TOKEN_SECRET=replace-with-a-long-local-secret \
  -e PETSTORE_PUBLIC_BASE_URL=http://localhost:8080/api/v3 \
  -e PETSTORE_DB_URL=jdbc:postgresql://swagger-petstore-db:5432/petstore \
  -e PETSTORE_DB_USER=petstore -e PETSTORE_DB_PASSWORD=petstore \
  andymentor/swagger-petstore:dev
```

Основной Compose использует этот образ. Локальная разработка выполняется через
`docker-compose.dev.yml`.

Push image:

```bash
docker login
docker push andymentor/swagger-petstore:dev
docker push andymentor/swagger-petstore-db:16.15
```

Multi-arch build and push из проверенного `dev`:

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t andymentor/swagger-petstore:dev --push .
docker buildx build --platform linux/amd64,linux/arm64 \
  -t andymentor/swagger-petstore-db:16.15 --push docker/postgres
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
