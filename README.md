# Swagger Petstore API

Учебный API зоомагазина для ручного и автоматизированного тестирования.
Пользователи регистрируются и подтверждают почту, управляют профилем,
выбирают питомцев и зоотовары, собирают общую корзину, оформляют заказ
и проверяют оплату, отмену и возврат.

Стек: Python 3.12+, FastAPI, Pydantic, psycopg 3, Uvicorn, PostgreSQL 16.
Swagger UI позволяет выполнять запросы. Платежи — локальный симулятор, не банковский сервис.

## Запуск

Нужны запущенный Docker Desktop и Docker Compose. Из корня проекта:

```powershell
docker compose up -d --wait
```

Скачивается `andymentor/swagger-petstore:latest`. API и PostgreSQL работают
в одном контейнере; БД и фотографии хранятся в отдельных named volumes.
Порты доступны только на localhost.

| Назначение | Адрес |
|---|---|
| Swagger | http://localhost:8080/ |
| API | http://localhost:8080/api/v3 |
| Готовность API и БД | http://localhost:8080/api/v3/health |
| Контракт | http://localhost:8080/api/v3/openapi.json |
| PostgreSQL | localhost:5432; база/user/password: `petstore` |

Демо-аккаунты создаются один раз при инициализации БД:

| Роль | Email | Username | Password |
|---|---|---|---|
| ADMIN | admin@example.com | admin | admin123 |
| USER | test@example.com | user1 | password123 |

Для сборки из исходников:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build --wait
```

Основной Compose описывает окружение; dev-overlay переключает образ на локальную сборку.
Во всех режимах используется один `Dockerfile`.

## Структура проекта

```text
src/petstore/
  app.py          Lifecycle, обработчики ошибок и безопасные request-логи
  api/            APIRouter, Depends, типизированные параметры и проверка ответов
  config.py       Настройки окружения
  controller/     Endpoint-обработчики и права доступа
  service/        Бизнес-правила и границы транзакций: аккаунты, каталог, корзина, checkout
  data/           SQL-репозитории, pool и общие блокировки строк
  model/          DTO и перечисления
  notification/   SMTP и шаблоны писем
  utils/          Формат публичных ответов

resources/
  openapi.yaml    Контракт API
  db/migration/   SQL-миграции V1–V11
  web/            Swagger-страница и резервная форма сброса пароля

tests/
  unit/           Проверки компонентов без живой БД
  integration/    Операции и конкуренция на отдельном PostgreSQL
  system/         Swagger, почта, рестарт и обновление старой установки
  smoke/          HTTP-сценарии запущенного сервера
  docker-compose.yml  Изолированный тестовый стенд

docker/           Entrypoint контейнера и почтовый overlay
docs/history.md   Архив исправлений
.github/workflows/ Проверки и публикация
```

Поток запроса: api → controller → service → data → PostgreSQL → проверенный DTO ответа.

| Компонент | Ответственность |
|---|---|
| app | Жизненный цикл pool/expiry, единый формат ошибок и безопасные request-логи |
| api | Явные нативные маршруты FastAPI, Depends, Body/Path/Query/Header и response_model |
| controller | Проверяет роль и адаптирует HTTP-команду к доменному действию; общего dispatch по именам операций нет |
| service | Правила аккаунта, каталога, корзины и checkout; один transaction context на команду |
| data | SQL с bound parameters и детерминированные блокировки; не решает бизнес-переходы mixed checkout |
| model | Формат данных и именованные статусы, без сетевых вызовов |
| notification | Отправка писем после сохранения операции; без изменения HTTP-контракта |
| utils | Сериализация UUID/UTC/Decimal и исключение приватных полей из ответа |

Сервис mixed checkout управляет переходами, резервом и refund в одной транзакции,
используя тот же lock заказа, что и существующий платёжный симулятор.
Разделять их на независимые запросы нельзя. Database владеет pool;
успешная операция фиксируется, исключение откатывает транзакцию.

OpenAPI — опубликованный контракт путей, operationId, ролей, схем и примеров ошибок.
Маршруты объявлены в `api/`, а не создаются из YAML во время запуска;
тест проверяет совпадение всех 78 операций с контрактом.
FastAPI проверяет DTO каждого JSON-ответа, включая вложенные объекты:
несовместимые и приватные поля приводят к безопасному 500, а не выдаются клиенту.
Внутренние имена Python — snake_case; внешние operationId и JSON aliases сохранены.
Денежные расчёты выполняются в Decimal, timestamps остаются UTC с миллисекундами.
Бизнес-логика и HTTP-сервер работают на Python. Java-исходников и Maven нет.
JRE нужен только Flyway: он проверяет и применяет SQL до запуска API.
Перенос файлов не меняет SQL/checksums и не пересоздаёт существующую БД.

## Возможности и ограничения API

- Регистрация, одноразовое подтверждение, resend, вход и восстановление пароля.
- Профиль и управление пользователями; статусы PENDING, ACTIVE, BLOCKED.
- Поиск питомцев, административный CRUD и версия записи для защиты от устаревшего PUT.
- Заказы, резервирование, платежи, idempotency, отмена и безопасное удаление.
- Каталог товаров/кормов, категории, фильтры, поиск, сортировка и пагинация.
- Расширенные карточки питомцев; публикация независима от доступности.
- Галереи до 20 фотографий, загрузка, нормализация и миниатюры.
- Общая корзина и заказ с товарами и питомцами; единая оплата симулятором.
- Ограниченная техническая телеметрия без произвольных полей и персональных данных.

Login возвращает `access_token,token_type,expires_in,user`.
Приватные операции требуют `Authorization: Bearer <access_token>`.
USER работает со своим; ADMIN управляет пользователями/питомцами и обработкой заказов.
Сброс пароля и административные изменения отзывают старые токены.

Ошибки: `status,error,message,details`. Details содержит нарушения полей либо пуст
для общей ошибки. Ограничения полей — 422, отсутствующее/непригодное тело — 400;
успех без тела — 204. Подробности каждого endpoint находятся в Swagger.

### Каталог и фотографии

Публичные каталоги: `/products`, `/catalog/pets`, `/catalog/categories`.
Административные карточки: `/admin/products`, `/admin/pets`.
POST/PUT товаров и действия публикации/остатков находятся под `/products`;
все изменения доступны только ADMIN. У карточек состояния DRAFT/PUBLISHED/ARCHIVED,
обновления и действия требуют текущую `version`. Деактивация категории сохраняет товары.

`POST /media` принимает multipart `file`, `sourceType` (OWN/SUPPLIER/DEMO),
необязательный `sourceNote`. Поддерживаются JPEG, PNG и статичный WebP:
до 10 MiB и 40 MP. Проверяется содержимое, EXIF удаляется, создаётся миниатюра до 480 px.
UUID файла используется в `images` карточки; порядок задаётся списком,
обложка — `isCover`, описание — `alt`. Без явной обложки выбирается первое фото.
Непубликованные изображения видит ADMIN, исторические обложки — также владелец заказа.
Используемые карточкой или снимком заказа изображения удалить нельзя.

Файлы сохраняются в `swagger-petstore-media-data`, отдельно от PostgreSQL.
S3/MinIO не требуется; отсутствуют публичная раздача файлов каталога и пути из клиентских имён.

### Корзина и заказ

`GET/PUT /store/cart` работает с собственным аккаунтом. Строка: `kind,id,quantity`;
для питомца quantity=1. Ответ содержит актуальную и сохранённую цену,
доступность и причину недоступности. PUT полностью заменяет состав по `version`.
Для повторного объединения гостевой корзины используется один UUID `Idempotency-Key`:
повтор того же запроса не добавляет количество второй раз.

`POST /store/orders` создаёт черновик по `cartVersion`. Place атомарно проверяет
все цены/профиль/остатки и резервирует весь состав; при ошибке не резервируется ничего.
Draft содержит снимки позиций, но общая сумма, доставка и дедлайн ещё null.
Создание, place и единая оплата требуют UUID `Idempotency-Key`.
Сумму вычисляет сервер; подмена суммы и неопознанные поля команд отклоняются.
Резерв снимается однократно при отмене/истечении; доставка списывает товарный остаток.
Снимки названий, цен, обложек и доставки сохраняются после редактирования каталога.

Старые `/pet`, `/store/order` и их DTO сохранены для существующих автотестов.
История `/store/orders` также показывает прежние одно-питомцевые заказы.

| Статус | Назначение |
|---|---|
| draft | Обновляемый черновик без резерва, цены и доставки |
| placed | Оформлен: резерв и снимок цены/доставки; 15 минут на оплату |
| approved | Оплачен и принят администратором в обработку |
| shipped | Отправлен; отмена запрещена |
| delivered | Доставлен |
| cancelled | Отменён; оплаченная отмена выполняет refund и снимает резерв |
| expired | Время оплаты истекло, резерв снят |

Create создаёт draft; отдельный place требует заполненного профиля.
Для draft `paymentStatus=NOT_STARTED`; сумма/доставка/дедлайн — null.
Оплата разрешена только в placed. Повтор той же попытки использует тот же UUID
в `Idempotency-Key`.

USER отменяет свой placed/approved и удаляет свой draft.
ADMIN принимает оплаченный заказ в обработку, отправляет/доставляет и удаляет draft/терминальные заказы.
Удалять placed/approved/shipped нельзя. Платежи удаляются вместе с терминальным заказом;
отдельно ADMIN удаляет только DECLINED.
ADMIN и демонстрационный USER защищены. Пользователь с заказами не удаляется.

## Почта

```powershell
docker compose -f docker-compose.yml -f docker/compose.mail.yml up -d --wait
```

smtp4dev принимает письма, хранит их в отдельном volume и предоставляет SMTP/IMAP.
Внешняя пересылка выключена. Без overlay отправка выключена, если PETSTORE_SMTP_HOST не задан.

| Назначение | Адрес |
|---|---|
| Интерфейс / Swagger почты | http://localhost:8025/ / http://localhost:8025/api/ |
| SMTP с хоста / внутри Compose | localhost:2525 / mail:25 |
| IMAP | localhost:1143 |

Логины `user1,user2,tests`, пароль `mail-test-only` — публичные учебные данные.
Адреса user1@petstore.test и user2@petstore.test попадают в соответствующие ящики,
остальные — в Tests.

Письма содержат HTML и plain text, без паролей. Confirm/resend действуют 24 часа,
reset — 30 минут; новая ссылка заменяет старую.
Если SMTP недоступен, сохранённая операция не отменяется; пишется безопасный лог.
Автоматического retry/outbox пока нет. Транспорт предназначен для локального SMTP без auth/TLS.

## Конфигурация и данные

Переменные задаются окружением или локальным `.env`, который не коммитится.

| Переменная | Назначение |
|---|---|
| POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD | Инициализация БД |
| PETSTORE_DB_URL / PETSTORE_DB_USER / PETSTORE_DB_PASSWORD | Подключение приложения |
| POSTGRES_PORT | Порт БД на хосте |
| PETSTORE_DB_VOLUME | Существующий volume; default swagger-petstore-db-data |
| PETSTORE_MEDIA_VOLUME | Volume изображений; default swagger-petstore-media-data |
| PETSTORE_MEDIA_ROOT | Директория изображений; контейнер /var/lib/petstore/media |
| PETSTORE_TOKEN_SECRET | Стабильный JWT secret, минимум 32 UTF-8 байта |
| PETSTORE_PUBLIC_BASE_URL | Адрес API для одноразовых ссылок |
| PETSTORE_EXPOSE_TEST_LINKS | Учебный resetUrl в JSON; default true |
| PETSTORE_SMTP_HOST / PETSTORE_SMTP_PORT / PETSTORE_SMTP_FROM / PETSTORE_SMTP_TIMEOUT | Локальный SMTP; default port 25, timeout 5 секунд |
| PETSTORE_MAIL_FRONTEND_URL | Необязательный адрес веб-приложения для ссылок в письмах |
| PETSTORE_RESOURCE_ROOT / PETSTORE_STATIC_ROOT | Переопределение директорий ресурсов и web |

Без JWT secret создаётся ключ процесса: после рестарта старые токены недействительны.
`PETSTORE_EXPOSE_TEST_LINKS=false` скрывает resetUrl в JSON, но не отключает письмо.
Учебные пароли и выдача ссылок не предназначены для публичного сервера.

Обновление:

```powershell
docker compose pull
docker compose up -d --wait
```

Перед обновлением сделать backup и сохранить фактический volume, DB credentials и secret.
Compose по умолчанию использует `swagger-petstore-db-data`; прежний запуск через
docker run мог использовать `swagger-petstore-data`. Не заменяйте его пустой БД:
передайте прежнее имя через PETSTORE_DB_VOLUME. Не запускайте два PostgreSQL на одном volume.

`down` сохраняет данные; `down -v` удаляет их.

## Проверки и разработка

```powershell
py -3.12 -m venv .venv-python
.\.venv-python\Scripts\python.exe -m pip install --constraint requirements-runtime.txt -e ".[test,quality]"
.\.venv-python\Scripts\ruff.exe check src tests
.\.venv-python\Scripts\pyright.exe --pythonpath .venv-python/Scripts/python.exe
.\.venv-python\Scripts\python.exe -m pytest tests/unit -q
```

`pyproject.toml` описывает пакет и инструменты.
`requirements-runtime.txt` фиксирует runtime-зависимости вместе с транзитивными
для воспроизводимых сборок. `.dockerignore` исключает секреты и локальные артефакты.

Изолированный стенд:

```powershell
docker compose -f tests/docker-compose.yml up -d --build --wait
docker exec petstore-python-preview psql -U petstore -d petstore -c "CREATE DATABASE petstore_python_test"
docker exec -e FLYWAY_URL=jdbc:postgresql://127.0.0.1:5432/petstore_python_test -e FLYWAY_USER=petstore -e FLYWAY_PASSWORD=petstore petstore-python-preview /opt/flyway/flyway -locations=filesystem:/app/resources/db/migration migrate
$env:PETSTORE_TEST_DB_URL="postgresql://127.0.0.1:5433/petstore_python_test"
.\.venv-python\Scripts\python.exe -m pytest tests/unit tests/integration --cov=petstore --cov-fail-under=90
```

CREATE DATABASE выполняется только один раз. Стенд: API :8081, БД :5433,
отдельный volume petstore-python-preview-data. Интеграционные тесты защищены
проверкой имени petstore_python_test. Очистка затрагивает только записи, созданные тестом.

Smoke: задать BASE_URL=http://localhost:8081/api/v3 и запустить tests/smoke.
System: задать PETSTORE_UI_URL, BASE_URL, PETSTORE_MAIL_UI_URL и установить
`python -m playwright install chromium`. Опциональные restart/upgrade-проверки
включаются через PETSTORE_RESTART_CONTAINER, PETSTORE_MAIL_RESTART_CONTAINER,
PETSTORE_TEST_UPGRADE_IMAGE. CI задаёт все значения и не пропускает эти проверки.

## CI и выпуск

Ruff, строгий Pyright, unit/integration с покрытием >=90%, smoke, почта,
рестарт/upgrade и браузерный Swagger блокируют выпуск при ошибках.
UI-тест раскрывает все операции и проверяет Try it out, Execute и реальные параметры.

После dev изменения проходят master. CI собирает/тестирует amd64 и arm64,
проверяет исправляемые HIGH/CRITICAL уязвимости Trivy и публикует
`latest` / `sha-<commit>` с SBOM и provenance.
Затем smoke, полный магазин и Swagger проверяются на опубликованном Docker Hub digest.

Это локальная учебная среда. Для публичного сервиса нужны TLS, управление секретами,
SMTP auth/TLS, очередь доставки, распределённый limiter и эксплуатационный аудит.
Сейчас один Uvicorn worker; лимитер входа и development JWT key принадлежат процессу.
