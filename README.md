# Бэкенд учебного магазина Лапки

API локального зоомагазина для изучения ручного и автоматизированного тестирования. Покупатель выбирает товары и питомцев, оформляет общий заказ и оплачивает его симулятором. Администратор управляет каталогом, пользователями и заказами. Реальных банковских списаний нет.

## Проекты и технологии

- **Этот репозиторий:** Python 3.12, FastAPI, Pydantic, psycopg, PostgreSQL, Uvicorn; API, бизнес-правила, миграции Flyway и серверные тесты.
- **[Веб](https://github.com/AndreyMetelkin85/lapki-frontend):** React и TypeScript; покупательский и административный интерфейсы, браузерные тесты.
- **[Android](https://github.com/AndreyMetelkin85/lapki-mobile):** React Native, TypeScript и Expo; покупательский интерфейс и APK.
- **Инфраструктура:** Docker Compose и smtp4dev для локальной почты. pytest, Ruff и Pyright для проверок бэкенда.

Исходники проектов разделены. Общий `docker-compose.yml` здесь запускает готовые образы из Docker Hub: API, веб, PostgreSQL, почту, миграции и сервис скачивания APK. Android-приложение работает в эмуляторе, не в Docker. Java-исходников и Maven нет; JRE используется только Flyway.

## Что можно тестировать

- Регистрацию, подтверждение по письму, вход, JWT, роли, блокировку и восстановление пароля.
- Профиль и адрес, товары и корма, категории, питомцев, фото, поиск, публикацию и остатки.
- Корзину, смешанный заказ, резерв на 15 минут, оплату, отмену, возврат и доставку.
- Валидацию DTO, HTTP-коды, конфликты версий, повторы с `Idempotency-Key`, письма и состояние БД.

Маршруты находятся под `/api/v3`. Контракт и примеры — в Swagger. Письма попадают в локальный smtp4dev, а не во внешний почтовый ящик.

Допустимые теги питомца возвращает `GET /api/v3/catalog/pet-tags`. При создании через `POST /api/v3/pet` передавайте `tags: [{"name": "friendly"}]`, без `id`: UUID назначит сервер. Новое произвольное название отклоняется с `422`. Исторические теги остаются читаемыми; при обновлении их можно сохранить с прежними UUID и названиями.

## Первый запуск на Windows

Нужны Git и запущенный Docker Desktop в режиме Linux containers. Выполните в PowerShell:

```powershell
git clone https://github.com/AndreyMetelkin85/swagger-petstore.git
Set-Location swagger-petstore
Copy-Item .env.example .env
$taskBytes = New-Object byte[] 32
$taskRandom = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$taskRandom.GetBytes($taskBytes)
$taskRandom.Dispose()
$taskSecret = [System.BitConverter]::ToString($taskBytes).Replace('-', '')
(Get-Content .env) -replace '^PETSTORE_TOKEN_SECRET=.*$', "PETSTORE_TOKEN_SECRET=$taskSecret" | Set-Content -Encoding utf8 .env
docker compose pull
docker compose up -d --no-build --wait --wait-timeout 300
```

Сборка исходников не нужна. Для установки без Git используйте выданный учебный архив: все настройки и скрипт запуска уже внутри.

| Приложение | Адрес |
| --- | --- |
| Магазин | http://localhost:8090 |
| Swagger | http://localhost:8080 |
| Почта | http://localhost:8025 |
| Скачивание Android APK | http://localhost:8091 |

APK рассчитан на Android Studio с эмулятором **x86_64**. Скачайте файл и перетащите на экран эмулятора. Адрес API в приложении — `http://10.0.2.2:8080/api/v3`.

## Учебные доступы

| Назначение | Логин | Пароль |
| --- | --- | --- |
| Администратор магазина | `admin@example.com` | `admin123` |
| Покупатель | `test@example.com` | `password123` |
| PostgreSQL, БД `petstore`, `localhost:5432` | `petstore` | `petstore` |
| IMAP, `localhost:1143`, общий ящик Tests | `tests` | `mail-test-only` |

SMTP — `localhost:2525`, без авторизации. Веб-почта также без входа. Для отдельных IMAP-ящиков есть `user1` и `user2` с тем же учебным паролем; получатели — `user1@petstore.test` и `user2@petstore.test`.

Доступы действуют при стандартных настройках новой БД. Изменённые пароли и состояния аккаунтов сохраняются. Стенд предназначен для локального обучения: не выставляйте его в интернет, не используйте реальные персональные данные. Личный JWT-ключ из `.env` не публикуйте.

Карты симулятора: `4242424242424242` — успех; `4000000000000002` — отказ; `4000000000009995` — недостаточно средств. Месяц `12`, год `2099`, CVV `123`, имя `TEST USER`.

## Обновление

В папке установленного стенда:

```powershell
git pull --ff-only
docker compose pull
docker compose up -d --no-build --wait --wait-timeout 300
```

Существующий `.env` не заменяйте и ключ заново не создавайте. База, фото и письма хранятся в отдельных Docker-томах; `docker compose down -v` удалит эти данные. Сервис `migrations` с `Exited (0)` после запуска — норма.

## Код и проверки

Путь запроса: `api → controller → service → data → PostgreSQL`. DTO находятся в `src/petstore/model`, письма — в `notification`. Контракт — `resources/openapi.yaml`, миграции — `resources/db/migration`. Swagger в `resources/web` — документация API, не исходники магазина.

[Разработка и тесты](docs/DEVELOPMENT.md) · [Выпуск](docs/DELIVERY.md) · [История](docs/history.md)
