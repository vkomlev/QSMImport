from __future__ import annotations
from typing import List
from dataclasses import dataclass
import gspread  # pip install gspread oauth2client
from app.models.question_input import QuestionInputRow


@dataclass
class GoogleSheetsSource:
    spreadsheet_id: str
    worksheet_name: str
    service_account_json: str

    def fetch_rows(self) -> List[QuestionInputRow]:
        """
        Читает лист и возвращает нормализованные строки.
        Ожидаемые колонки: см. описание (Текст, Варианты..., Правильный..., ...)
        """
        gc = gspread.service_account(filename=self.service_account_json)
        sh = gc.open_by_key(self.spreadsheet_id)
        ws = sh.worksheet(self.worksheet_name)

        # Предполагаем, что в первой строке — заголовки.
        records = ws.get_all_records()
        rows: List[QuestionInputRow] = []
        for r in records:
            rows.append(
                QuestionInputRow(
                    text=(r.get("Текст") or "").strip(),
                    variants_and_points=(r.get("Варианты ответа и баллы") or "").strip(),
                    correct_answer=(r.get("Правильный ответ") or "").strip(),
                    input_link=(r.get("Входные данные") or "").strip(),
                    qtype_code=(r.get("Тип задания") or "").strip(),
                    quiz_title=(r.get("Тема") or "").strip(),
                    difficulty_ru=(r.get("Сложность") or "").strip(),
                    hint=(r.get("Текст подсказки") or "").strip(),
                    video_url=(r.get("Видеоразбор") or "").strip(),
                )
            )
        return rows
