# Project Memory

Project: QSMImport
Path: `d:\Work\QSMImport`
Created: 2026-05-26

## Purpose

- What this project is responsible for: читать строки заданий из Google Sheets и
  импортировать их либо напрямую в БД QSM/WordPress (MySQL), либо в LMS через
  HTTP API (`/api/v1/tasks/validate`, `/api/v1/tasks/bulk-upsert`).
- What it is not responsible for: не хранит контент заданий сам по себе (источник
  истины — Google Sheets), не управляет схемой БД QSM/LMS, не публикует контент
  на сайт напрямую (кроме постов квизов QSM, куда пишет через `wp_posts`/`postmeta`).

## Durable Context

- Product/domain facts that should survive across sessions: типы вопросов — SC
  (single choice), MC (multiple choice), SA (short answer), SA_COM (short answer +
  комментарий, требует ручной проверки), TA (развёрнутый ответ, всегда ручная
  проверка). Сложности заданий маппятся из русских названий (`Сложность` в таблице)
  в term/id целевой системы.
- Important integration partners and contracts: Google Sheets (через `gspread`,
  сервис-аккаунт), LMS Core API (`app/datasources/lms_api.py`, эндпоинты
  `/api/v1/meta/tasks`, `/api/v1/tasks/validate`, `/api/v1/tasks/bulk-upsert`,
  `/api/v1/tasks/find-by-external`, `/api/v1/tasks/by-external/{uid}`), MySQL QSM
  (прямые SQL через SQLAlchemy, `app/qsm/repositories.py`).
- Operational constraints: LMS-импорт по умолчанию должен идти через `dry-run`
  (флаг `LMS_IMPORT_DRY_RUN` или команда `dry-run-lms-import`) перед боевой
  записью — `import-to-lms` пишет реальные задачи в LMS.

## Commands

- Setup: `pip install -r requirements.txt`
- Test: выделенного тестового набора нет; `test_gsheets.py` — ручная проверка чтения листа
- Lint/typecheck: не настроены (нет конфигов ruff/mypy в репозитории)
- Run locally: `python main.py <команда>` (см. `docs/usage.md` / README)
- Smoke checks: `python -m compileall app`, `python main.py dry-run-lms-import --limit 20`

## Architecture Notes

- Core modules: `app/cli.py` (Typer-команды), `app/datasources/` (Google Sheets,
  LMS API), `app/qsm/` (репозиторий и сервис прямой записи в MySQL QSM),
  `app/mappers/` (маппинг строк в LMS `TaskUpsertItem` и сложности), `app/services/`
  (`LmsImportService` — оркестрация HTTP-импорта), `app/models/` (`QuestionInputRow`,
  enum `QuestionType`), `app/utils/` (парсинг ячеек, нормализация текста). Подробнее —
  `docs/ai/architecture.md`.
- Data/storage: MySQL (QSM/WordPress, прямые SQL-запросы через SQLAlchemy) для
  сценария `import-from-gsheets`; для LMS-сценария локального хранилища нет — все
  данные идут транзитом Google Sheets → LMS API.
- External services: Google Sheets API (`gspread` + сервис-аккаунт JSON), LMS Core
  API (HTTP, `requests`, авторизация по `api_key` в query-параметре).
- Trust boundaries: содержимое Google Sheets — внешний вход, не валидируется на
  уровне схемы до маппинга; для LMS-сценария валидация происходит на стороне LMS
  API (`/api/v1/tasks/validate`) перед записью.

## Known Risks

- Reliability: `import-to-lms` без `dry-run` пишет боевые данные в LMS одним
  проходом по всем строкам таблицы — ошибка маппинга отдельной строки логируется
  и пропускается, не прерывает импорт остальных (см. `LmsImportService.import_from_gsheets`).
- Security/privacy: сервис-аккаунт Google (`gscapi-*.json`) и `.env` с ключами БД/LMS
  лежат в корне проекта — оба в `.gitignore`, не коммитить.
- Data/encoding: `requirements.txt` ранее был сохранён в UTF-16 LE с BOM (нетипично
  для этого формата, могло ломать некоторые парсеры) — пересохранён в UTF-8
  (2026-07-18).
- Cross-project contract drift: `TaskUpsertItem`/`TaskValidateRequest` — контракт
  LMS API (проект LMS, `d:\Work\LMS`); при изменении схемы на стороне LMS нужно
  синхронно обновлять `app/mappers/lms_task_mapper.py`.

## Current Decisions

| Date | Decision | Why | Owner/Source |
| --- | --- | --- | --- |

## Prevention Register

| Date | Incident/Risk | Prevention Rule | Related Skill |
| --- | --- | --- | --- |

## Handoff Notes

- Current focus:
- Blockers:
- Follow-ups:

## Maintenance Rules

- Keep durable facts here; keep transient task notes in session summaries or issue docs.
- Do not store credentials, tokens, cookies, personal secrets, or private keys.
- When implementation intentionally diverges from specs, record the decision and update the relevant specs/docs in the same task.
- Prefer links to canonical docs over duplicating long content.
