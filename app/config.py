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

        # --------- LMS API ----------
    lms_api_base_url: AnyUrl | None = Field(
        default=None,
        description="Базовый URL LMS Core API, например: http://localhost:8000 или https://lms.example.com",
    )

    lms_api_key: str | None = Field(
        default=None,
        description="API ключ, передаваемый в query-параметре ?api_key=...",
    )

    lms_api_timeout: float = Field(
        default=10.0,
        description="Таймаут HTTP-запросов к LMS API, сек.",
    )

    lms_import_dry_run: bool = Field(
        default=False,
        description="Режим 'только валидация', без записи задач в LMS.",
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
    wp_author_id: int = 3

    # pydantic v2 style config:
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # лишние переменные окружения игнорируем
    )

    
