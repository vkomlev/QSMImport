from __future__ import annotations
from typing import Any, Dict, List, Iterable
from .php_serialize import _php_array
from app.models.enums import QuestionType

# -------- answer_array builders --------

def build_answer_array_single(options: List[Dict[str, Any]]) -> str:
    arr = []
    for opt in options:
        arr.append([opt["text"], float(opt.get("points", 0)), 1 if opt.get("correct", False) else 0])
    return _php_array(arr)

def build_answer_array_short(accepted: List[Dict[str, Any]]) -> str:
    arr = []
    for a in accepted:
        pts = float(a.get("points", 0))
        arr.append([a["text"], pts, 1 if pts > 0 else 0])
    return _php_array(arr)

def build_answer_array_textarea(exemplar: str | None = None, points: float | int = 10) -> str:
    if exemplar is None:
        return _php_array([])
    return _php_array([[exemplar, float(points), 1 if points > 0 else 0]])

# -------- question_settings --------

def settings_base(title: str, required: bool, placeholder: str = "") -> Dict[str, Any]:
    return {
        "required": 1 if required else 0,
        "answerEditor": "text",
        "question_title": title,
        "matchAnswer": "random",
        "limit_multiple_response": 0,
        "case_sensitive": 0,
        "placeholder_text": placeholder,
        "min_text_length": 0,
        "file_upload_limit": 4,
        "file_upload_type": "image,application/pdf",
    }

def settings_for_type(qtype: QuestionType, title: str, placeholder: str = "") -> str:
    base = settings_base(title, required=True, placeholder=placeholder)
    if qtype == QuestionType.MC:
        base["limit_multiple_response"] = 1
    return _php_array(base)

# -------- pages (qpages/pages) --------

def build_qpages_single_page(question_ids: List[int]) -> str:
    qpages = [{"page": 1, "title": "", "description": "", "questions": question_ids}]
    return _php_array(qpages)

def build_pages_single_page(question_ids: List[int]) -> str:
    pages = [{"page": 1, "questions": question_ids}]
    return _php_array(pages)
