import typer
from app.config import Settings
from app.logging_config import setup_logging
from app.qsm.repositories import QsmRepository
from app.qsm.services import ImportService
from app.datasources.google_sheets import GoogleSheetsSource

app = typer.Typer(add_completion=False)

@app.command()
def import_from_gsheets():
    """
    Импортировать задания из Google Sheets в QSM (MySQL).
    """
    settings = Settings()
    setup_logging(settings)

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
    )
    service.import_questions_batch(rows)
    print("Импорт завершён.")

def main():
    app()

if __name__ == "__main__":
    main()
