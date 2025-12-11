# app/cli.py
import json

import typer
import logging

from app.config import Settings
from app.logging_config import setup_logging
from app.qsm.repositories import QsmRepository
from app.qsm.services import ImportService
from app.datasources.google_sheets import GoogleSheetsSource

# LMS
from app.datasources.lms_api import LmsApiClient
from app.mappers.lms_task_mapper import row_to_task_upsert_item
from app.services.lms_import_service import LmsImportService

log = logging.getLogger(__name__)
app = typer.Typer(add_completion=False)


@app.command()
def import_from_gsheets():
    """
    Импортировать задания из Google Sheets в QSM (MySQL).
    """
    settings = Settings()
    setup_logging(settings)
    log.info("Запуск команды import_from_gsheets (QSM)")
    repo = QsmRepository(str(settings.db_url))

    src = GoogleSheetsSource(
        spreadsheet_id=settings.gsheets_spreadsheet_id or "",
        worksheet_name=settings.gsheets_worksheet_name,
        service_account_json=settings.gsheets_service_account_json or "",
    )
    rows = src.fetch_rows()

    service = ImportService(
        repo,
        default_points_short_answer=settings.default_points_short_answer,
        prepend_input_link=settings.prepend_input_link,
        input_link_label=settings.input_link_label,
        wp_site_url=settings.site_url,
        wp_author_id=settings.wp_author_id,
        wp_post_status='publish',
    )
    service.import_questions_batch(rows)
    print("Импорт завершён.")
    log.info("Команда import_from_gsheets завершена")


# НОВАЯ КОМАНДА ДЛЯ LMS (боевой импорт)
@app.command()
def import_to_lms():
    """
    Импортировать задания из Google Sheets в LMS через API.

    Логика:
      - читает все строки из Google Sheets,
      - валидирует их через /api/v1/tasks/validate,
      - если Settings.lms_import_dry_run == False — отправляет валидные задачи
        в /api/v1/tasks/bulk-upsert.
    """
    settings = Settings()
    setup_logging(settings)
    log.info("Запуск команды import_to_lms (LMS)")
    # Проверка настроек LMS
    if not settings.lms_api_base_url:
        typer.echo("❌ lms_api_base_url не задан в настройках (.env).")
        raise typer.Exit(code=1)
    if not settings.lms_api_key:
        typer.echo("❌ lms_api_key не задан в настройках (.env).")
        raise typer.Exit(code=1)

    typer.echo(f"Используем LMS API: {settings.lms_api_base_url}")
    if settings.lms_import_dry_run:
        typer.echo("Режим: DRY-RUN (lms_import_dry_run=True) — данные не будут записаны в LMS.")

    # Источник данных Google Sheets
    gs_source = GoogleSheetsSource(
        spreadsheet_id=settings.gsheets_spreadsheet_id or "",
        worksheet_name=settings.gsheets_worksheet_name,
        service_account_json=settings.gsheets_service_account_json or "",
    )

    # Клиент и сервис LMS
    lms_client = LmsApiClient(settings)
    service = LmsImportService(
        settings=settings,
        gs_source=gs_source,
        lms_client=lms_client,
    )

    # Полный цикл импорта (внутри сервиса уже есть dry-run логика)
    service.import_from_gsheets()
    log.info("Команда import_to_lms завершена")
    typer.echo("Импорт в LMS завершён.")


# СУЩЕСТВУЮЩАЯ КОМАНДА DRY-RUN ОСТАЁТСЯ
@app.command()
def dry_run_lms_import(
    limit: int = typer.Option(3, help="Сколько первых строк из Google Sheets проверять"),
):
    """
    Dry-run импорт в LMS:
    - читает первые N строк из Google Sheets
    - получает meta/tasks из LMS
    - маппит строки в TaskUpsertItem
    - валидирует каждую задачу через /api/v1/tasks/validate
    - печатает итоговые JSON-структуры и результат валидации

    Ничего в LMS не записывается.
    """
    settings = Settings()
    setup_logging(settings)
    log.info("Запуск команды dry_run_lms_import (limit=%d)", limit)

    if not settings.lms_api_base_url:
        typer.echo("❌ lms_api_base_url не задан в настройках (.env).")
        raise typer.Exit(code=1)
    if not settings.lms_api_key:
        typer.echo("❌ lms_api_key не задан в настройках (.env).")
        raise typer.Exit(code=1)

    typer.echo(f"Используем LMS API: {settings.lms_api_base_url}")

    src = GoogleSheetsSource(
        spreadsheet_id=settings.gsheets_spreadsheet_id or "",
        worksheet_name=settings.gsheets_worksheet_name,
        service_account_json=settings.gsheets_service_account_json or "",
    )
    rows = src.fetch_rows()

    if not rows:
        typer.echo("❌ В листе Google Sheets нет строк.")
        raise typer.Exit(code=1)

    rows_sample = rows[:limit]

    lms_client = LmsApiClient(settings)

    typer.echo("Запрашиваю метаданные задач (difficulties, courses, ...) из LMS...")
    meta = lms_client.get_tasks_meta()
    typer.echo(
        f"Получены метаданные: difficulties={len(meta.get('difficulties', []))}, "
        f"courses={len(meta.get('courses', []))}"
    )

    typer.echo(f"\nПроверяем первые {len(rows_sample)} строк(и) из Google Sheets:\n")

    for idx, row in enumerate(rows_sample, start=1):
        typer.echo("-" * 80)
        typer.echo(f"Строка #{idx}")
        typer.echo(f"  Код вопроса: {row.question_code!r}")
        typer.echo(f"  Код курса:   {row.course_code!r}")
        typer.echo(f"  Тип:         {row.qtype_code!r}")
        typer.echo(f"  Сложность:   {row.difficulty_ru!r}")
        typer.echo(f"  Тема:        {row.quiz_title!r}")

        try:
            upsert_item = row_to_task_upsert_item(row, meta, settings)
        except Exception as e:
            typer.echo(f"❌ Ошибка маппинга row_to_task_upsert_item: {e}")
            continue

        validate_payload = {
            "task_content": upsert_item["task_content"],
            "solution_rules": upsert_item["solution_rules"],
            "max_score": upsert_item["max_score"],
            "difficulty_id": upsert_item["difficulty_id"],
            "course_id": upsert_item["course_id"],
            "course_code": row.course_code.strip() if row.course_code else None,
            "external_uid": upsert_item["external_uid"],
        }

        typer.echo("Сформированный TaskUpsertItem:")
        typer.echo(json.dumps(upsert_item, ensure_ascii=False, indent=2))

        typer.echo("\nРезультат валидации через /api/v1/tasks/validate:")
        try:
            validation_result = lms_client.validate_task(validate_payload)
            typer.echo(json.dumps(validation_result, ensure_ascii=False, indent=2))
        except Exception as e:
            typer.echo(f"❌ Ошибка при валидации задачи в LMS: {e}")

    typer.echo("\n✅ Dry-run завершён.")
    log.info("Команда dry_run_lms_import завершена")


def main():
    app()


if __name__ == "__main__":
    main()
