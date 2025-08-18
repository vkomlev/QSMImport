from __future__ import annotations
from typing import List
from app.models.question_input import QuestionInputRow

class QuestionsDataSource:
    """
    Абстрактный источник строк заданий.
    """
    def fetch_rows(self) -> List[QuestionInputRow]:
        raise NotImplementedError
