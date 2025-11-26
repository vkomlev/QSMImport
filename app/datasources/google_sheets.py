# app/datasources/google_sheets.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import gspread  # как и было

from app.models.question_input import QuestionInputRow


def _cell_str(row: dict, key: str) -> str:
    """
    Безопасно достаём значение из строки Google Sheets и приводим к строке.
    Любые типы (int, float, None) → str(...).strip().
    """
    value = row.get(key)
    if value is None:
        return ""
    return str(value).strip()


@dataclass
class GoogleSheetsSource:
    spreadsheet_id: str
    worksheet_name: str
    service_account_json: str

    def fetch_rows(self) -> List[QuestionInputRow]:
        """
        Читает лист и возвращает нормализованные строки.
        Ожидаемые колонки:
        - "Код вопроса"
        - "Код курса"
        - "Текст"
        - "Варианты ответа и баллы"
        - "Правильный ответ"
        - "Входные данные"
        - "Тип задания"
        - "Тема"
        - "Сложность"
        - "Текст подсказки"
        - "Видеоразбор"
        """
        gc = gspread.service_account(filename=self.service_account_json)
        sh = gc.open_by_key(self.spreadsheet_id)
        ws = sh.worksheet(self.worksheet_name)

        records = ws.get_all_records()
        rows: List[QuestionInputRow] = []

        for r in records:
            rows.append(
                QuestionInputRow(
                    question_code=_cell_str(r, "Код вопроса"),
                    course_code=_cell_str(r, "Код курса"),
                    text=_cell_str(r, "Текст"),
                    variants_and_points=_cell_str(r, "Варианты ответа и баллы"),
                    correct_answer=_cell_str(r, "Правильный ответ"),
                    input_link=_cell_str(r, "Входные данные"),
                    qtype_code=_cell_str(r, "Тип задания"),
                    quiz_title=_cell_str(r, "Тема"),
                    difficulty_ru=_cell_str(r, "Сложность"),
                    hint=_cell_str(r, "Текст подсказки"),
                    video_url=_cell_str(r, "Видеоразбор"),
                )
            )

        return rows
