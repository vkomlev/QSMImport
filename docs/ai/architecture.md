# Архитектура QSMImport

## Обзор потока данных

```
Google Sheets ("Задания")
        │
        ▼
GoogleSheetsSource.fetch_rows()  →  List[QuestionInputRow]
        │
        ├── сценарий QSM/WordPress ────────────┐
        │                                       ▼
        │                          ImportService (app/qsm/services.py)
        │                                       │
        │                                       ▼
        │                          QsmRepository (app/qsm/repositories.py)
        │                                       │
        │                                       ▼
        │                              MySQL (QSM/WordPress: quizzes, questions,
        │                                     terms, wp_posts/postmeta)
        │
        └── сценарий LMS ──────────────────────┐
                                                 ▼
                                    LmsImportService (app/services/lms_import_service.py)
                                                 │
                                        row_to_task_upsert_item()
                                        (app/mappers/lms_task_mapper.py)
                                                 │
                                                 ▼
                                    LmsApiClient (app/datasources/lms_api.py)
                                                 │
                                                 ▼
                                    LMS Core API (HTTP: validate → bulk-upsert)
```

## Компоненты

### `app/datasources/`
- `base.py` — абстрактный `QuestionsDataSource` (контракт `fetch_rows()`).
- `google_sheets.py` — `GoogleSheetsSource`: читает лист по имени, ожидает колонки
  `Код вопроса`, `Код курса`, `Текст`, `Варианты ответа и баллы`, `Правильный ответ`,
  `Входные данные`, `Тип задания`, `Тема`, `Сложность`, `Текст подсказки`,
  `Видеоразбор`. Все значения приводятся к строке через `_cell_str`.
- `lms_api.py` — `LmsApiClient`: тонкая обёртка над `requests` для эндпоинтов LMS
  Core API (`get_tasks_meta`, `validate_task`, `bulk_upsert_tasks`,
  `find_tasks_by_external`, `get_task_by_external`). Ключ API передаётся в
  query-параметре `api_key`.

### `app/qsm/` (сценарий прямой записи в QSM/WordPress)
- `repositories.py` — `QsmRepository`: весь SQL к MySQL (SQLAlchemy Core/raw SQL).
  Создание/поиск квиза, гарантирование системных настроек квиза (система
  оценивания, контактная форма, сообщение после теста), upsert вопросов и термов,
  работа с `wp_posts`/`postmeta` для страницы квиза.
- `services.py` — `ImportService`: оркестрирует импорт пачки строк — находит/создаёт
  квиз, гарантирует термы сложности, для каждой строки строит `question_settings`,
  `answer_array` (через `builders.py`), проставляет термы сложности, в конце
  перестраивает страницы квиза (`update_quiz_pages`).
- `builders.py` — построение `question_settings`/`answer_array` под формат QSM
  (сериализованные PHP-структуры).
- `php_serialize.py` — сериализация Python-структур в PHP `serialize()`-формат
  (QSM хранит настройки вопросов как сериализованный PHP в MySQL).

### `app/mappers/` и `app/services/` (сценарий LMS)
- `lms_task_mapper.py` — маппинг `QuestionInputRow` → `TaskUpsertItem`/
  `TaskValidateRequest`: строит `TaskContent` (stem, media, options для SC/MC) и
  `SolutionRules` (разные ветки для SC/MC, SA/SA_COM, TA), сопоставляет сложность
  и курс по meta из LMS (`map_difficulty_ru_to_lms_id`, `map_quiz_title_to_course_id`).
- `difficulty_mapper.py` — маппинг русских названий сложности в term name (для
  сценария QSM).
- `lms_import_service.py` — `LmsImportService.import_from_gsheets()`: полный цикл —
  читает строки, получает meta из LMS, маппит и валидирует каждую строку через
  `/api/v1/tasks/validate`, копит валидные `TaskUpsertItem`, при
  `lms_import_dry_run=False` отправляет их одним запросом в
  `/api/v1/tasks/bulk-upsert`. Ошибки по отдельным строкам логируются и не
  прерывают обработку остальных.

### `app/models/`
- `question_input.py` — `QuestionInputRow` (dataclass, нормализованная строка из
  Google Sheets).
- `enums.py` — `QuestionType` (SC, MC, SA, SA_COM, TA).

### `app/utils/`
- `parsing.py` — разбор ячеек с вариантами ответов (`Текст||баллы` построчно) и
  списков правильных ответов (через `;`).
- `text.py` — нормализация текста, добавление блока "Входные данные" к
  формулировке вопроса.

### `app/cli.py`
Точка входа Typer: три команды — `import-from-gsheets` (QSM), `import-to-lms`
(боевой импорт в LMS), `dry-run-lms-import` (проверка маппинга/валидации без
записи).

## Точки расширения / хрупкие места
- Формат ячеек Google Sheets жёстко завязан на конкретные заголовки колонок
  (см. `google_sheets.py`) — переименование колонок в таблице ломает импорт молча
  (пустые строки вместо ошибки, т.к. `_cell_str` возвращает `""` для отсутствующего
  ключа).
- `map_quiz_title_to_course_id` бросает `ValueError`, если в LMS несколько курсов и
  код курса не совпал ни с одним `course_uid` — это единственная точка, где
  маппинг курса требует явного кода.
- Сериализация PHP (`php_serialize.py`) — формат хранения QSM; несовместимые
  изменения здесь ломают отображение вопросов в WordPress без ошибок на уровне
  Python (ошибка проявится только в консоли QSM).
