# Локальный Swagger Petstore для API-тестирования

## Python / FastAPI

Перенос разрабатывается в `feature/python-fastapi-migration`, созданной от `origin/dev`
(`fbed64b`). Эталон всей логики, OpenAPI и регрессионных тестов — актуальный `origin/master`
(`380e37988b51c4329c3672ed55c62e958569c2be`). Основной `Dockerfile` и release-пайплайн
собирают Python. Java-исходники, Maven и Tomcat удалены из текущего проекта;
предыдущая реализация доступна в истории Git. Рабочая БД не пересоздаётся.
JRE остаётся исключительно для Flyway, не для бизнес-логики или HTTP-сервера.

- Python 3.12, FastAPI, Pydantic, psycopg 3, Uvicorn;
- сохранены 36 операций, `operationId`, роли, ошибки и PostgreSQL-схема;
- Python-слои: `python/petstore/{controller,service,data,model,utils}`;
- исходные SQL-миграции V1–V9 не изменены; их по-прежнему применяет Flyway;
- перенесены master-исправления: details конфликтов регистрации и единая блокировка
  подтверждения/resend/удаления; устаревшие Swagger-примеры убраны как в master;
- Swagger использует относительный `/api/v3`, чтобы Execute не обращался к другому контейнеру;
- тесты: `tests/python/unit`, `tests/python/integration`, `tests/python/system`;
- новый CI проверяет Ruff, строгий Pyright, покрытие не ниже 90%, исходные smoke-тесты,
  все кнопки Swagger и повторный запуск с существующей базой;
- публикация в Docker Hub зависит от успешных Python-проверок, smoke-тестов и
  сканирования образа для обеих архитектур `linux/amd64`, `linux/arm64`;
- runtime-зависимости закреплены в `requirements-runtime.txt`;
- каждый выпуск получает `latest` и неизменяемый тег `sha-<commit>`;
- локально используется один API worker, как один процесс Java: JWT development-key
  и текущий login limiter остаются process-local. Для сохранения JWT между рестартами
  задайте прежний `PETSTORE_TOKEN_SECRET`, не публикуя его в репозитории.

Отдельный тестовый стенд, **не использующий volume рабочей БД**:

```powershell
docker compose -f docker-compose.python.yml up -d --build --wait
```

Swagger: <http://localhost:8081/>. PostgreSQL: `localhost:5433`.
Контейнер: `petstore-python-preview`; volume: `petstore-python-preview-data`.
Демо-аккаунты и их пароли создаются исходными миграциями, как в Java-версии.

Для локальных проверок:

```powershell
py -3.12 -m venv .venv-python
.\.venv-python\Scripts\python.exe -m pip install --constraint requirements-runtime.txt -e ".[test,quality]"
.\.venv-python\Scripts\ruff.exe check python tests/python
.\.venv-python\Scripts\pyright.exe --pythonpath .venv-python/Scripts/python.exe
.\.venv-python\Scripts\python.exe -m pytest tests/python/unit -q
```

Интеграционные тесты требуют отдельно мигрированную БД `petstore_python_test`:
`PETSTORE_TEST_DB_URL=postgresql://127.0.0.1:5433/petstore_python_test`.
Системные smoke-тесты используют `BASE_URL=http://localhost:8081/api/v3`;
UI-тест — `PETSTORE_UI_URL=http://localhost:8081` и установленный Playwright Chromium.
Без явной настройки интеграционные/UI-тесты пропускаются, в CI все настройки обязательны.
Очистка затрагивает только UUID, созданные конкретным прогоном; рабочий контейнер не меняется.

Выпуск проходит PR в `dev`, проверки, затем PR в `master`; публикация выполняется
GitHub Actions только после успешных проверок. До завершения workflow новый образ
не считается выпущенным.

### Локальная почта: SMTP + IMAP + Swagger

В том же тестовом Compose работает `petstore-mail` (smtp4dev 3.15.0, образ закреплён
digest). Рабочие контейнеры не переключаются. Письма хранятся в отдельном volume
`petstore-mail-data`; внешняя пересылка отключена, порты опубликованы только на loopback.

- Почтовый интерфейс: <http://localhost:8025/>.
- Swagger почтового REST API: <http://localhost:8025/api/>.
- SMTP для программ на хосте: `localhost:2525`; для Python API в Compose: `mail:25`.
- IMAP: `localhost:1143`; локальные demo-логины `user1`, `user2`, `tests`, пароль
  `mail-test-only`. Это публичные учебные данные, не production-учётные записи.
- `user1@petstore.test` попадает в `User1`, `user2@petstore.test` — в `User2`, остальные
  адреса — в `Tests`. Адреса остаются локальными; это не аккаунты публичной почтовой службы.

Регистрация и resend отправляют HTML + plain text со ссылкой подтверждения на 24 часа;
forgot password — письмо восстановления на 30 минут. Пароли в письмах отсутствуют.
Отправка реализована в `python/petstore/notification/mail_service.py`, шаблоны —
в `python/petstore/notification/templates.py`. Дополнительные SMTP/шаблонные библиотеки
не нужны: используются стандартные `smtplib`, `email` и `html`.

SMTP включается только при заданном `PETSTORE_SMTP_HOST`. Настройки:
`PETSTORE_SMTP_PORT` (25), `PETSTORE_SMTP_FROM`, `PETSTORE_SMTP_TIMEOUT` (5 секунд).
Текущий транспорт предназначен для локального сервера без SMTP authentication/TLS.
Отправка ограничена timeout и выполняется в существующем worker pool FastAPI.
Если SMTP недоступен, результат уже зафиксированной операции API не меняется;
появляется безопасный `mail_delivery_failed` без паролей, email или одноразовых ссылок.
Автоматической очереди повторной доставки пока нет: подтверждение можно повторно
отправить через resend, восстановление — через forgot password.

Пока React работает с моками, письмо подтверждения ведёт на рабочий API, а письмо
восстановления — на форму Python-стенда `/reset-password.html`. Ответы существующего
API (`confirmationUrl`, `resetUrl`) и схемы БД не изменены. Форма не логирует пароль
или code, очищает code из адресной строки и отправляет `newPassword` в JSON-теле.

После подключения реального auth API во фронте можно задать
`PETSTORE_MAIL_FRONTEND_URL=http://localhost:8088`: ссылки писем станут
`/confirm/{userId}?code=...` и `/reset-password?code=...`. До отключения моков этого
делать не нужно. Фронт не должен получать SMTP/IMAP credentials.

Системные проверки почты находятся в `tests/python/system/test_mail_delivery.py`:
SMTP → отдельные ящики → IMAP; регистрация/resend → письмо → подтверждение;
forgot password → письмо → браузерная форма → вход с новым паролем.
Для запуска нужны `BASE_URL` тестового API и `PETSTORE_MAIL_UI_URL`; CI задаёт их явно.
Тесты удаляют только созданные ими сообщения по точному API ID и пользователей по UUID.

## Учебный Petstore API

Учебный API для практики ручного и автоматизированного API-тестирования. В нём
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
- заказ проходит состояния `draft`, `placed`, `approved`, `shipped`, `delivered`, `cancelled` или `expired`;
- черновик не резервирует питомца; резерв, цена и доставка фиксируются только при оформлении;
- профиль хранит один российский адрес, а заказ — неизменяемый снимок контактов и доставки;
- цена питомца хранится в рублях и фиксируется в заказе на момент оформления;
- добавлен локальный симулятор тестовых платежей с idempotency, отказами, refund и истечением резерва;
- добавлена безопасная очистка тестовых пользователей, черновиков, завершённых заказов и отклонённых платежей;
- операции изменения pets и управления пользователями защищены ролью `ADMIN`;
- отсутствие/ошибка/истечение токена дают `401`, недостаточная роль — `403`;
- ошибки имеют единый JSON-контракт `status`, `error`, `message`, `details`;
- устаревшие зачёркнутые операции удалены из Swagger UI;
- пустой раздел `Parameters / No parameters` скрывается во всех операциях без параметров;
- разделы Swagger имеют английские названия, а операции — нейтральные русские названия;
- OpenAPI содержит подробные описания, `operationId`, примеры, перечисления,
  форматы и ограничения;
- добавлена endpoint-specific runtime-валидация с ответом `422` и `details[]`;
- данные хранятся в PostgreSQL; Python использует psycopg 3;
- идентификаторы users, pets, categories, tags и orders имеют формат UUID;
- статусы аккаунтов, питомцев и заказов представлены PostgreSQL ENUM;
- Flyway применяет версионированные миграции без удаления существующих данных;
- внешние ключи запрещают обход правил удаления, а уникальный индекс не допускает два активных заказа на одного питомца;
- Dockerfile стал multi-stage и не требует локальной установки Python или сборочных инструментов;
- Compose публикует API и PostgreSQL только на loopback и хранит БД в отдельном named volume;
- Python unit/integration/system и Pytest/httpx smoke tests; проверяется обновление старого Docker-образа.

## Стек и структура

- Python 3.12, FastAPI, Pydantic, Uvicorn;
- существующий OpenAPI управляет контрактом и маршрутизацией;
- Swagger UI 5.32.11 без внешних CDN;
- PostgreSQL 16 и psycopg 3;
- OpenAPI 3.0.4: `src/main/resources/openapi.yaml`;
- контроллеры: `python/petstore/controller`;
- auth/validation services: `python/petstore/service`;
- репозитории: `python/petstore/data`;
- единый Docker image API + PostgreSQL: `Dockerfile`;
- версия схемы и seed: `src/main/resources/db/migration`;
- модели: `python/petstore/model`;
- Python tests: `tests/python`;
- AQA smoke tests: `tests/smoke`.

## Быстрый запуск через Docker Compose

Требуются Docker Desktop и Docker Compose. Основной Compose скачивает один проверенный
образ `andymentor/swagger-petstore:latest`, в котором вместе запускаются API и PostgreSQL:

```bash
docker compose up -d
```

Для локальной почты подключите необязательный overlay:

```powershell
docker compose -f docker-compose.yml -f docker-compose.mail.yml up -d --wait
```

Без overlay SMTP выключен по умолчанию. Почта не встроена в API-образ и не пересылает
письма в интернет. При одновременно работающем preview освободите его почтовые порты
или задайте другие `PETSTORE_MAIL_HTTP_PORT`, `PETSTORE_MAIL_SMTP_PORT`,
`PETSTORE_MAIL_IMAP_PORT`. Старый preview не нужно удалять вместе с его данными.

При обновлении существующей установки сохраните **её фактический volume**. Для
запуска через `docker run` из примера ниже это `swagger-petstore-data`, для прежнего
Compose по умолчанию — `swagger-petstore-db-data`. Не подменяйте один другим.
Перед переходом сделайте `pg_dump` своей БД; не используйте `down -v`.

Для разработки из локальных исходников подключите overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Чтобы получить опубликованное обновление и пересоздать контейнер без удаления данных:

```powershell
docker compose pull
docker compose up -d
```

Named volume остаётся прежним, поэтому PostgreSQL продолжает использовать уже
сохранённые данные.

## Запуск без Docker Compose

Для учебного локального запуска API и PostgreSQL доступны в одном контейнере. Docker
автоматически создаст named volume и сохранит в нём данные между перезапусками:

```bash
docker run -d --name swagger-petstore --restart unless-stopped \
  -p 127.0.0.1:8080:8080 \
  -p 127.0.0.1:5432:5432 \
  -v swagger-petstore-data:/var/lib/postgresql/data \
  andymentor/swagger-petstore:latest
```

Остановить и снова запустить тот же контейнер без потери данных:

```bash
docker stop swagger-petstore
docker start swagger-petstore
```

В Docker Desktop внутри Compose-проекта виден один контейнер `swagger-petstore`.
API и PostgreSQL опубликованы только на loopback. Порт PostgreSQL можно переопределить
переменной `POSTGRES_PORT`.

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
docker compose exec petstore psql -U petstore -d petstore -c "SELECT id, username, role FROM users ORDER BY id;"
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

В учебном образе `POST /auth/password/forgot` по умолчанию возвращает `resetUrl`, чтобы
можно было проверить полный сценарий восстановления пароля без почтового сервиса.
Не используйте этот режим с реальными учётными записями или на публичном сервере:
любой, кто знает email, сможет получить ссылку сброса. Для отключения установите
`PETSTORE_EXPOSE_TEST_LINKS=false`. Без почтовой доставки восстановление пароля в
этом режиме будет недоступно.

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
- `POST /auth/password/reset`;
- `GET /pet/findByStatus`;
- `GET /pet/findByTags`;
- `GET /pet/{petId}`.

USER/ADMIN:

- `GET`, `PUT /user/me` (`PUT` изменяет firstName, lastName, phone и address);
- `POST /store/order` (создание `draft`);
- `GET /store/order`;
- `GET`, `PUT`, `DELETE /store/order/{orderId}` (USER управляет только своим `draft`);
- `POST /store/order/{orderId}/place`;
- `POST /store/order/{orderId}/cancel` (USER отменяет только свой заказ).

ADMIN:

- `POST /pet`;
- `PUT`, `DELETE /pet/{petId}`;
- `GET /store/inventory`;
- `POST /store/order/{orderId}/approve`;
- `POST /store/order/{orderId}/ship`;
- `POST /store/order/{orderId}/deliver`;
- `DELETE /store/order/{orderId}` для `draft`, `delivered`, `cancelled` и `expired`;
- `DELETE /store/order/{orderId}/payments/{paymentId}` для платежа `DECLINED`;
- `GET /users`;
- `GET`, `PUT`, `DELETE /users/{userId}`;
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

`POST /store/order` создаёт `draft`, который можно менять и удалять без резерва питомца.
`POST /store/order/{orderId}/place` проверяет профиль и доступность питомца, фиксирует
цену и адрес, переводит заказ в `placed` и запускает 15-минутный срок оплаты. После
оплаты администратор переводит заказ в `approved`, `shipped` и `delivered`. Отмена
разрешена в `placed` и `approved`; оплаченная отмена выполняет refund. Физическое
удаление активных `placed`, `approved` и `shipped` запрещено.

## Проверки

Python unit/integration tests:

```bash
python -m pip install --constraint requirements-runtime.txt -e '.[test,quality]'
python -m pytest tests/python/unit tests/python/integration --cov=petstore --cov-fail-under=90
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

59 smoke-сценариев проверяют health, авторизацию, регистрацию и подтверждение,
восстановление пароля, блокировку, отзыв старых tokens, роли, питомцев, заказы и
платежи, а также единый формат ошибок для некорректных входных данных. Параллельные запросы отдельно
проверяют атомарность подтверждения, сброса пароля, блокировки, разблокировки и
резервирования и оплаты. Также проверяются запрет destructive user/order operations,
невозможность подделать ADMIN token старым публичным secret и optimistic lock питомца.

Для ручной проверки persistence создайте пользователя или pet, перезапустите контейнер и
повторите GET-запрос — запись останется в PostgreSQL:

```bash
docker compose restart petstore
```

## Docker-образ и Docker Hub

Публичный образ публикуется как `andymentor/swagger-petstore:latest`. Он содержит API и
PostgreSQL и собирается только из проверенного commit ветки `master`; upstream-образ
`swaggerapi/petstore3` не используется.

Build image:

```bash
docker build --pull -t andymentor/swagger-petstore:latest .
```

Run image:

```bash
docker run -d --name swagger-petstore --restart unless-stopped \
  -p 127.0.0.1:8080:8080 -p 127.0.0.1:5432:5432 \
  -v swagger-petstore-data:/var/lib/postgresql/data \
  andymentor/swagger-petstore:latest
```

Основной Compose использует этот образ. Локальная разработка выполняется через
`docker-compose.dev.yml`.

GitHub Actions собирает и сканирует image в pull request, но ничего не публикует.
После успешной проверки push в `master` обновляет `latest` и сохраняет
`sha-<commit>` для платформ `linux/amd64` и `linux/arm64`. Image содержит SBOM,
provenance и OCI-label с точным Git commit.

Для публикации в настройках GitHub Actions должны быть заданы:

- variable `DOCKERHUB_USERNAME=andymentor`;
- secret `DOCKERHUB_TOKEN` — отдельный Docker Hub access token с правом Read & Write.

Пароль Docker Hub и access token не сохраняются в Git, README или Docker image.

## Ограничения и дальнейшие TODO

- JWT не имеет refresh flow; для отзыва используется внутренняя версия token;
- при автоматически сгенерированном JWT secret все Bearer tokens отзываются после рестарта API;
- Python использует psycopg connection pool; схема обновляется прежними Flyway migrations;
- recovery-ссылки возвращаются клиенту только в явно включённом учебном режиме;
- демонстрационные credentials и выдача confirmation-ссылки в ответе предназначены только
  для локального обучения;
- перед production-подобным использованием нужны TLS/reverse proxy, secret manager,
  распределённый rate limiting, SMTP authentication/TLS и очередь повторной доставки, аудит;
- локальная почта и development-настройки не предназначены для публичного интернет-сервиса.
