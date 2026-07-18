# QSMImport

Импорт вопросов из Google Sheets в Quiz and Survey Master (QSM/WordPress) и в LMS API.

## Что делает проект

QSMImport читает строки заданий из Google Sheets и превращает их в вопросы/задачи
в одной из двух целевых систем:

- **QSM/WordPress** — пишет напрямую в MySQL (таблицы QSM: квизы, вопросы, термы,
  постметы), создаёт вопрос целиком со всеми настройками (тип, варианты, сложность,
  видеоразбор).
- **LMS API** — маппит строку в `TaskUpsertItem`, валидирует через
  `/api/v1/tasks/validate` и записывает через `/api/v1/tasks/bulk-upsert`
  (боевой импорт, с защитой через `dry-run`).

## Быстрый старт

```powershell
# Установка зависимостей
pip install -r requirements.txt

# Настройка окружения — скопировать шаблон и заполнить значения
cp .env.example .env

# Проверка, что модули импортируются без ошибок
python -m compileall app
```

## Режимы запуска

Все команды — через `python main.py <команда>`:

| Команда | Назначение |
| --- | --- |
| `import-from-gsheets` | Импорт вопросов из Google Sheets в QSM (MySQL) |
| `dry-run-lms-import --limit N` | Проверка первых N строк: маппинг + валидация в LMS, ничего не пишет |
| `import-to-lms` | Полный импорт из Google Sheets в LMS через API (валидация + bulk-upsert) |

Режим dry-run для LMS также управляется флагом `LMS_IMPORT_DRY_RUN=true` в `.env` —
тогда `import-to-lms` тоже остановится после валидации, не записывая задачи.

Логи пишутся в `logs/qsm_import.log`.

## Документация

- `.claude/CLAUDE.md` — стек, команды, guardrails для AI-агента
- `docs/ai/PROJECT_MEMORY.md` — назначение, архитектура, риски
- `docs/ai/architecture.md` — компоненты и потоки данных
- `docs/ai/errors.md` — известные проблемы и антипаттерны
- `.env.example` — список переменных окружения
