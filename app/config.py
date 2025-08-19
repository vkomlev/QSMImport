# app/config.py
from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Конфиг приложения. В pydantic v2 настройки для .env задаются через model_config,
    а BaseSettings — из пакета pydantic-settings.
    """

    # --------- DB ----------
    db_url: AnyUrl = Field(
        ...,
        description=(
            "SQLAlchemy URL, напр.: "
            "mysql+pymysql://user:pass@host/db?charset=utf8mb4"
        ),
    )

    # --------- Google Sheets ----------
    gsheets_spreadsheet_id: str | None = None
    gsheets_worksheet_name: str = "Задания"
    gsheets_service_account_json: str | None = Field(
        default=None,
        description="Путь к credentials JSON (если используем gspread)",
    )

    # --------- Import behavior ----------
    default_points_short_answer: float = 10.0
    prepend_input_link: bool = True
    input_link_label: str = "Входные данные"

    # --------- Logging ----------
    log_dir: str = "logs"
    log_level: str = "INFO"
    log_file: str = "qsm_import.log"
    log_max_bytes: int = 5 * 1024 * 1024  # 5 MB
    log_backup_count: int = 3

    # posts meta
    site_url: str = "https://victor-komlev.ru/"
    wp_author_id: str = "3"

    # pydantic v2 style config:
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # лишние переменные окружения игнорируем
    )

    
