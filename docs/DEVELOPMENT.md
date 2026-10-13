# Разработка и границы ответственности

## Установка и проверки

Нужен Python 3.12. Из корня репозитория в PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --constraint requirements-runtime.txt -e ".[test,quality]"
.venv\Scripts\ruff check src tests docker
.venv\Scripts\ruff format --check src tests docker
.venv\Scripts\pyright --pythonpath .venv\Scripts\python.exe
.venv\Scripts\python -m pytest tests/unit -q
```

`pyproject.toml` описывает пакет и настройки инструментов; `requirements-runtime.txt` закрепляет runtime-зависимости для Docker. Node.js для бэкенда не нужен. Unit-тесты изолированы; интеграционные и системные проверки запускайте только с выделенной тестовой БД:

```powershell
docker compose -f tests/docker-compose.yml up -d --build --wait
.venv\Scripts\python docker/ci_databases.py --container petstore-python-preview --workers 4
$env:PETSTORE_TEST_DB_URL = "postgresql://127.0.0.1:5433/petstore_python_test"
.venv\Scripts\python -m pytest tests/unit tests/integration -n 4 --dist loadscope -q --cov=petstore --cov-fail-under=90
```

Тесты очистки нельзя подключать к рабочей БД. CI дополнительно проверяет Swagger, SMTP/IMAP, оплату и сохранность данных; образы AMD64 и ARM64 проверяются отдельно.

## HTTP → контроллер → сервис → PostgreSQL

Маршрут FastAPI разбирает path/query/body и объявляет модель ответа. Зависимости предоставляют контроллер текущего приложения; глобальные экземпляры клиентов не создаются.

Контроллер проверяет авторизацию и передаёт команду сервису. Бизнес-сервис определяет допустимость операции, транзакцию и порядок блокировок. Слой данных выполняет SQL и использует переданное соединение. В сохранённых маршрутах прежнего API некоторые транзакционные правила находятся в репозиториях; их перенос является отдельной задачей, не частью разделения контейнеров.

`RequestContext` хранит запрос, сервис авторизации, разобранные параметры и тело. `Context` — сокращённая типизированная зависимость FastAPI для этого объекта. `Controller` в модуле маршрута — зависимость конкретного контроллера.

Контроллеры возвращают совместимый HTTP-ответ. `decode_response` переносит его статус и разбирает публичный JSON как Decimal; FastAPI проверяет результат по модели ответа. Этот переходный адаптер не должен принимать приватные строки БД.

## Документирование

Python: русская докстринга с действием, всеми `:param:`, `:return:` либо `:yield:`. Для опасных или транзакционных действий объясняются изменения состояния, блокировки и фиксация. Для исключений описываются реальные причины; HTTP-коды остаются частью OpenAPI.

TypeScript: русские JSDoc в репозитории фронтенда. Идентификаторы Python/TS и внешние JSON-имена не переводятся. Сами тестовые функции — без докстрингов. Исторические SQL не редактируются даже ради перевода комментариев: это изменило бы checksum Flyway. Сгенерированные библиотеки и директивы анализаторов также не переводятся.

## Системные проверки бэкенда

Запустите `tests/docker-compose.yml`. Он создаёт отдельные API, PostgreSQL и почту, не использует рабочие тома. При занятых почтовых портах настройте `PETSTORE_PREVIEW_MAIL_HTTP_PORT`, `PETSTORE_PREVIEW_MAIL_SMTP_PORT` и `PETSTORE_PREVIEW_MAIL_IMAP_PORT`.

```powershell
$env:BASE_URL = "http://127.0.0.1:8081/api/v3"
$env:PETSTORE_UI_URL = "http://127.0.0.1:8081"
$env:PETSTORE_RESTART_CONTAINER = "petstore-python-preview"
$env:PETSTORE_COMMERCE_CONTAINER = "petstore-python-preview"
$env:PETSTORE_COMMERCE_DB_CONTAINER = "petstore-python-db"
$env:PETSTORE_MAIL_UI_URL = "http://127.0.0.1:8025"
$env:PETSTORE_MAIL_RESTART_CONTAINER = "petstore-mail"
$env:PETSTORE_TEST_UPGRADE_IMAGE = "swagger-petstore-python:preview"
.venv\Scripts\python -m pytest tests/smoke tests/system -q
```

Для браузерных проверок установите `python -m playwright install chromium` либо задайте `PLAYWRIGHT_CHROMIUM_EXECUTABLE` на имеющийся Chrome. Тест миграции создаёт собственную базу, проверяет существующих пользователей, заказы, платежи и контрольные суммы, затем удаляет только свои ресурсы.

## Совместимость с фронтендом

UI-отображение проверяет `lapki-frontend`. Его CI запускает браузерные сценарии с закреплёнными API и почтой. Бэкенд не устанавливает Node и не хранит копию исходников UI.

Общий Compose использует отдельные образы. Для релизной пары фиксируются теги `sha-...`; обновление одного проекта не копирует и не пересобирает исходники другого.

## Переход со старого общего контейнера

Перед переходом сохраните резервную копию БД и остановите старый контейнер `swagger-petstore`: он занимает прежние порты и держит базу. Новый PostgreSQL должен использовать прежний том, который мог называться `swagger-petstore-data`, а не `swagger-petstore-db-data`. Не запускайте два PostgreSQL на одном томе и не выполняйте `down -v`, если нужны данные.

Первые 12 исторических SQL-миграций сохраняют контрольные суммы; уже применённые миграции не редактируются. Для воспроизводимого запуска фиксируйте проверенные теги образов API, веба, почты и мобильной доставки вместо `latest`.
