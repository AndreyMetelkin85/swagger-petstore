# Swagger Petstore — бэкенд учебного магазина «Лапки»

Python/FastAPI API для обучения ручному и автоматизированному тестированию. Реальные HTTP-запросы, PostgreSQL, тестовые письма и платёжный симулятор. Банковских списаний нет.

## Границы проектов

- **Этот репозиторий:** API, бизнес-правила, SQL-миграции, Swagger, серверные тесты и инфраструктура общего стенда.
- **[lapki-frontend](https://github.com/AndreyMetelkin85/lapki-frontend):** React, UI, DTO-адаптеры, браузерные тесты, сборка и отдельный образ фронтенда.

Исходники фронтенда не копируются в бэкенд. Каждый проект имеет собственный Dockerfile и CI. Общий `docker-compose.yml` запускает готовые образы обоих проектов; клонировать фронтенд для запуска не нужно.

## Запуск опубликованного стенда

Нужны Git, Docker Desktop с Linux-контейнерами и Docker Compose.

```powershell
git clone https://github.com/AndreyMetelkin85/swagger-petstore.git
cd swagger-petstore
Copy-Item .env.example .env
docker compose pull
docker compose up -d --wait --wait-timeout 180
```

Перед первым запуском задайте собственный `PETSTORE_TOKEN_SECRET` в `.env`.
Если стенд уже существует, используйте его прежний `.env`: не меняйте секрет, пароль БД и имена томов.

| Приложение | Адрес по умолчанию |
| --- | --- |
| Магазин | http://localhost:8090 |
| Swagger и API | http://localhost:8080 |
| Тестовая почта | http://localhost:8025 |
| PostgreSQL | localhost:5432 |
| SMTP / IMAP | localhost:2525 / localhost:1143 |

Начальные учебные аккаунты: `admin@example.com / admin123` и `test@example.com / password123`. Они создаются в новой базе; изменения существующих аккаунтов сохраняются.

## Сервисы и данные

| Сервис Compose | Ответственность |
| --- | --- |
| `frontend` | React и проксирование `/api/v3` в API |
| `backend` | FastAPI, без встроенных PostgreSQL, React и SMTP |
| `postgres` | Постоянная база данных |
| `mail` | smtp4dev: просмотр писем, SMTP и IMAP |
| `migrations` | Однократный Flyway перед запуском API |

Миграции используют тот же образ, что и API: версии приложения и миграций согласованы. Java-исходников, Maven и Tomcat нет; JRE нужен только CLI Flyway.

База, изображения и письма находятся в **трёх отдельных постоянных томах**. Имена задаются через `PETSTORE_DB_VOLUME`, `PETSTORE_MEDIA_VOLUME` и `PETSTORE_MAIL_VOLUME`.

### Обновление и переход со старого общего контейнера

```powershell
git pull --ff-only
docker compose pull
docker compose up -d --wait --wait-timeout 180
```

Если раньше магазин запускался одним контейнером `swagger-petstore`, сначала остановите его: он занимает прежние порты и держит базу. Сохраните его для отката. Новый PostgreSQL должен использовать **тот же том БД**; у старых установок он мог называться `swagger-petstore-data`, а не `swagger-petstore-db-data`.

Не запускайте два PostgreSQL на одном томе. Не используйте `down -v` для рабочего стенда. Перед переходом сохраните резервную копию БД. Первые 12 SQL-миграций не изменены, их история и контрольные суммы сохраняются.

Для воспроизводимого запуска задайте проверенные теги `sha-...` в `PETSTORE_IMAGE_TAG`, `FRONTEND_IMAGE` и `PETSTORE_MAIL_IMAGE`. `latest` предназначен для обновления учебного стенда; зафиксированные версии подходят для CI и отката.

## Возможности API

Все бизнес-маршруты находятся под `/api/v3`; точные DTO и ошибки — в Swagger.

- Регистрация, подтверждение и повторная отправка ссылки; вход, JWT, роли USER/ADMIN, восстановление пароля.
- Профиль, адрес доставки, административное управление и защита аккаунтов.
- Товары и корма, категории, расширенные питомцы, черновики, публикация, архив, поиск и остатки.
- Проверенная загрузка JPEG, PNG и статичного WebP; удаление EXIF, миниатюры и защищённые обложки заказов.
- Гостевая/серверная корзина, общий заказ товаров и питомцев, резерв на 15 минут.
- Оплата, повторы по Idempotency-Key, отмена, возврат и состояния доставки.
- Совместимые маршруты прежнего Petstore для пользователей, питомцев и одиночных заказов.
- Health, X-Request-ID и ограниченная безопасная телеметрия.

Симулятор карт: `4242424242424242` — успех; `4000000000000002` — отказ; `4000000000009995` — недостаточно средств. Только тестовые реквизиты, например срок `12/2099`, CVV `123`.

Почтовый relay во внешний мир выключен. IMAP-пользователи: `user1`, `user2`, `tests`; учебный пароль `mail-test-only`. Ящики User1/User2 соответствуют `user1@petstore.test` / `user2@petstore.test`; остальные учебные письма доступны в Tests.

## Структура бэкенда

```text
src/petstore/
  api/            маршруты FastAPI, зависимости, транспортные ограничения
  controller/     авторизация и адаптация HTTP-команд
  service/        бизнес-правила и согласование транзакций
  data/           пул PostgreSQL и SQL-операции
  model/          запросы, ответы и перечисления
  notification/   шаблоны писем и SMTP
  utils/          безопасная сериализация
resources/
  openapi.yaml    опубликованный контракт
  db/migration/   неизменённая история Flyway
  web/            Swagger и служебные страницы API
tests/
  unit/           изолированные проверки
  integration/    API с выделенной PostgreSQL
  system/         контейнеры, Swagger, SMTP/IMAP и сохранность данных
  smoke/          проверки контракта выпущенного образа
docker/           инфраструктура, CI и безопасные проверки готовности
```

JavaScript служебных страниц Swagger остаётся в бэкенде: это документация API, а не исходники магазина.

## Разработка и проверки

Python 3.12. Установка и инструменты:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --constraint requirements-runtime.txt -e ".[test,quality]"
.venv\Scripts\ruff check src tests docker
.venv\Scripts\ruff format --check src tests docker
.venv\Scripts\pyright --pythonpath .venv\Scripts\python.exe
.venv\Scripts\python -m pytest tests/unit -q
```

`pyproject.toml` содержит метаданные пакета и настройки инструментов; `requirements-runtime.txt` закрепляет полный набор runtime-зависимостей для Docker. JS-зависимостей здесь нет.

Изолированный тестовый стенд:

```powershell
docker compose -f tests/docker-compose.yml up -d --build --wait
.venv\Scripts\python docker/ci_databases.py --container petstore-python-preview --workers 4
$env:PETSTORE_TEST_DB_URL = "postgresql://127.0.0.1:5433/petstore_python_test"
.venv\Scripts\python -m pytest tests/unit tests/integration -n 4 --dist loadscope -q --cov=petstore --cov-fail-under=90
```

Порты и переменные системных тестов описаны в [документации разработки](docs/DEVELOPMENT.md). Не подключайте тесты очистки к рабочей БД.

CI проверяет Ruff, строгие типы, unit/integration, Swagger Try it out, SMTP/IMAP, оплату и сохранность данных. AMD64 и ARM64 собираются и проверяются отдельно. Публикация продвигает проверенные digest без повторной сборки. UI-сценарии выполняются в CI фронтенда против закреплённых API и почты.

Комментарии и докстринги собственного кода — на русском. Докстринга объясняет действие, параметры, результат и существенные побочные эффекты. Тестовые функции остаются без докстрингов; SQL-история Flyway, сгенерированные файлы и машинные директивы не переводятся.

[История проекта](docs/history.md) · [Процесс выпуска](docs/DELIVERY.md)
