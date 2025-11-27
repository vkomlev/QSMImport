# app/services/lms_import_service.py

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.config import Settings
from app.datasources.google_sheets import GoogleSheetsSource
from app.datasources.lms_api import LmsApiClient
from app.mappers.lms_task_mapper import row_to_task_upsert_item
from app.models.enums import QuestionType

log = logging.getLogger(__name__)


class LmsImportService:
    """
    Сервис импорта заданий из Google Sheets в LMS через HTTP-API.

    Основной сценарий:
      - читает строки из Google Sheets (QuestionInputRow),
      - получает meta (difficulties/courses/…),
      - маппит каждую строку в TaskUpsertItem (через lms_task_mapper),
      - валидирует задачу через /api/v1/tasks/validate,
      - при необходимости (если не dry run) отправляет список задач
        в /api/v1/tasks/bulk-upsert.
    """

    def __init__(
        self,
        settings: Settings,
        gs_source: GoogleSheetsSource,
        lms_client: LmsApiClient,
    ) -> None:
        self.settings = settings
        self.gs_source = gs_source
        self.lms_client = lms_client

    # --- Публичный API ---

    def import_from_gsheets(self, limit: Optional[int] = None) -> None:
        """
        Полный цикл импорта из Google Sheets в LMS.

        :param limit: опционально ограничить количество обрабатываемых строк
                      (удобно для тестов / поэтапной обкатки).
        """
        log.info("Начинаем импорт заданий в LMS из Google Sheets")

        # 1. Читаем строки из таблицы
        rows = self.gs_source.fetch_rows()
        if limit is not None:
            rows = rows[:limit]

        if not rows:
            log.warning("В листе Google Sheets нет строк, импорт отменён")
            return

        log.info("Из Google Sheets получено %d строк(и)", len(rows))

        # 2. Получаем meta из LMS
        meta = self.lms_client.get_tasks_meta()
        difficulties_meta: List[Dict[str, Any]] = meta.get("difficulties", [])
        log.debug(
            "Получены метаданные LMS: %d сложностей, %d курсов, версия=%s",
            len(difficulties_meta),
            len(meta.get("courses", [])),
            meta.get("version"),
        )

        valid_items: List[Dict[str, Any]] = []
        errors: List[str] = []

        # 3. Обрабатываем строки по одной
        for idx, row in enumerate(rows, start=1):
            question_code = getattr(row, "question_code", "")  # безопасно, даже если поле ещё не добавлено
            course_code = getattr(row, "course_code", "")

            log.debug(
                "Обработка строки #%d (question_code=%r, course_code=%r, type=%r)",
                idx,
                question_code,
                course_code,
                row.qtype_code,
            )

            # 3.1. Восстанавливаем тип вопроса
            try:
                qtype = QuestionType((row.qtype_code or "").strip().upper())
            except Exception as e:
                msg = (
                    f"Строка #{idx}: не удалось интерпретировать тип задания "
                    f"qtype_code={row.qtype_code!r}: {e}"
                )
                log.warning(msg)
                errors.append(msg)
                continue

            # 3.2. Маппинг строки в TaskUpsertItem (через общий маппер)
            try:
                item = row_to_task_upsert_item(row=row, meta=meta, settings=self.settings)
            except Exception as e:
                msg = (
                    f"Строка #{idx} (question_code={question_code!r}): "
                    f"ошибка маппинга row_to_task_upsert_item: {e}"
                )
                # Хочется стек-трейс в логах, но пользователю достаточно текста
                log.exception(msg)
                errors.append(msg)
                continue

            # 3.3. Формируем payload для /api/v1/tasks/validate
            validate_payload = self._build_validate_payload(
                item=item,
                row=row,
                qtype=qtype,
                difficulties_meta=difficulties_meta,
            )

            try:
                validate_result = self.lms_client.validate_task(validate_payload)
            except Exception as e:
                msg = (
                    f"Строка #{idx} (question_code={question_code!r}): "
                    f"ошибка HTTP-запроса к /tasks/validate: {e}"
                )
                log.exception(msg)
                errors.append(msg)
                continue

            is_valid = bool(validate_result.get("is_valid"))
            validate_errors = validate_result.get("errors") or []

            if not is_valid:
                msg = (
                    f"Строка #{idx} (question_code={question_code!r}): "
                    f"валидация НЕ пройдена, ошибки: {validate_errors!r}"
                )
                log.warning(msg)
                errors.append(msg)
                continue

            log.info(
                "Строка #%d (question_code=%r): валидация пройдена",
                idx,
                question_code,
            )
            valid_items.append(item)

        log.info(
            "Результат валидации: всего строк=%d, валидных=%d, с ошибками=%d",
            len(rows),
            len(valid_items),
            len(errors),
        )

        # 4. Если включён dry-run — на этом останавливаемся
        if self.settings.lms_import_dry_run:
            log.info(
                "Флаг lms_import_dry_run=True — выполнялась только валидация, "
                "bulk-upsert в LMS не выполняется"
            )
            return

        if not valid_items:
            log.warning("Нет валидных задач для импорта в LMS, bulk-upsert пропущен")
            return

        # 5. Отправляем валидные задачи в bulk-upsert
        try:
            upsert_response = self.lms_client.bulk_upsert_tasks(valid_items)
        except Exception as e:
            log.exception("Ошибка bulk-upsert задач в LMS: %s", e)
            # Здесь разумно пробросить исключение, чтобы CLI увидел ошибку
            raise

        results = upsert_response.get("results", []) or []
        created = sum(1 for r in results if r.get("action") == "created")
        updated = sum(1 for r in results if r.get("action") == "updated")

        log.info(
            "Bulk-upsert в LMS завершён: всего=%d, создано=%d, обновлено=%d",
            len(results),
            created,
            updated,
        )
        log.info(
            "Результат валидации: всего строк=%d, валидных=%d, с ошибками=%d",
            len(rows),
            len(valid_items),
            len(errors),
        )
        if errors:
            log.debug("Список ошибок валидации:\n%s", "\n".join(errors))

    # --- Внутренние помощники ---

    @staticmethod
    def _difficulty_code_from_meta(
        difficulty_id: Optional[int],
        difficulties_meta: List[Dict[str, Any]],
    ) -> Optional[str]:
        """
        Вспомогательная функция: по difficulty_id из TaskUpsertItem
        находим difficulty.code из meta.difficulties.

        Если id не найден или не задан — возвращаем None и даём бэкенду
        решать, как поступить.
        """
        if difficulty_id is None:
            return None

        for d in difficulties_meta:
            try:
                if d.get("id") == difficulty_id:
                    return d.get("code")
            except AttributeError:
                # На случай, если meta приехало в неожиданном формате
                continue
        return None

    def _build_validate_payload(
        self,
        item: Dict[str, Any],
        row: Any,
        qtype: QuestionType,
        difficulties_meta: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Собирает словарь TaskValidateRequest строго по OpenAPI-схеме.

        Основной источник данных — уже собранный TaskUpsertItem (item),
        чтобы не дублировать бизнес-логику маппера.
        """
        question_code = getattr(row, "question_code", "")
        course_code = getattr(row, "course_code", "")

        difficulty_id: Optional[int] = item.get("difficulty_id")
        difficulty_code = self._difficulty_code_from_meta(difficulty_id, difficulties_meta)

        payload: Dict[str, Any] = {
            # Обязательное поле:
            "task_content": item["task_content"],
            # Опциональные:
            "solution_rules": item.get("solution_rules"),
            "external_uid": item.get("external_uid") or question_code or None,
            # Эти поля по схеме не обязательны, но если можем — заполняем:
            "difficulty_code": difficulty_code,
            "course_code": course_code or None,
        }

        # На будущее: если в TaskValidateRequest появятся дополнительные поля,
        # связанные с типом вопроса (например, task_type), их можно заполнить
        # здесь, опираясь на qtype.
        log.debug(
            "Собран TaskValidateRequest для question_code=%r: difficulty_code=%r, course_code=%r",
            question_code,
            payload.get("difficulty_code"),
            payload.get("course_code"),
        )
        return payload
