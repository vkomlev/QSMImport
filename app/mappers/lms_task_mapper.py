# app/mappers/lms_task_mapper.py
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from app.config import Settings
from app.models.question_input import QuestionInputRow
from app.models.enums import QuestionType
from app.utils import parsing, text

log = logging.getLogger(__name__)


# ------------------------------
# Вспомогательные функции
# ------------------------------

def _map_qtype(raw: str) -> QuestionType:
    """
    Преобразует строковый код типа задания в QuestionType.
    Бросает ValueError при некорректном коде.
    """
    try:
        qtype = QuestionType(raw)
        log.debug("Маппинг типа задания: raw=%r -> %s", raw, qtype)
        return qtype
    except ValueError as e:
        log.error("Неизвестный тип задания qtype_code=%r", raw)
        raise ValueError(f"Unsupported question type code: {raw!r}") from e


def _choice_base_type(qtype: QuestionType) -> str:
    """
    Возвращает базовый type для task_content/solution_rules
    по подтипу QuestionType.
    """
    if qtype in (QuestionType.SC, QuestionType.MC):
        return "choice"
    if qtype in (QuestionType.SA, QuestionType.SA_COM):
        return "short_answer"
    if qtype is QuestionType.TA:
        return "text"
    # На всякий случай
    return "unknown"


def _build_options_and_scoring_for_choice(
    row: QuestionInputRow,
    qtype: QuestionType,
) -> Dict[str, Any]:
    """
    Формирует структуру options[] и scoring для SC/MC,
    а также вычисляет max_score.
    """
    variants = parsing.parse_variants_block(row.variants_and_points)
    correct_list_raw = parsing.parse_correct_list(row.correct_answer)
    correct_set_norm = {text.normalize(c) for c in correct_list_raw}

    options: List[Dict[str, Any]] = []
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    max_score = 0.0

    for idx, (opt_text, raw_points) in enumerate(variants):
        opt_norm = text.normalize(opt_text)
        is_correct = opt_norm in correct_set_norm

        # Если баллы не заданы (0 или пусто) и вариант правильный — даем 1
        points = float(raw_points)
        if is_correct and (points == 0.0):
            points = 1.0

        if is_correct:
            max_score += points

        opt_id = letters[idx] if idx < len(letters) else f"opt_{idx+1}"

        options.append(
            {
                "id": opt_id,
                "text": opt_text,
                "order": idx + 1,
                "is_correct": is_correct,
                "points": points,
            }
        )

    if qtype == QuestionType.SC:
        scoring = {
            "mode": "all_or_nothing",
            "partial_allowed": False,
            "penalize_wrong": False,
        }
    else:  # MC
        scoring = {
            "mode": "sum",
            "partial_allowed": True,
            "penalize_wrong": False,
        }

    return {
        "options": options,
        "scoring": scoring,
        "max_score": max_score,
    }


def _build_accepted_answers_for_short_answer(row: QuestionInputRow) -> List[Dict[str, Any]]:
    """
    Формирует accepted_answers для SA / SA_COM.
    Поддерживает exact и regex через префикс 're:'.
    """
    answers_raw = parsing.parse_correct_list(row.correct_answer)
    accepted: List[Dict[str, Any]] = []

    for raw in answers_raw:
        s = raw.strip()
        if not s:
            continue

        if s.lower().startswith("re:"):
            pattern = s[3:]
            match_type = "regex"

            try:
                re.compile(pattern)
            except re.error as e:
                log.warning("Некорректная regex в правильном ответе %r: %s", raw, e)
                # можно либо пропустить, либо добавить как exact; выберем пропуск
                continue
        else:
            pattern = s
            match_type = "exact"

        accepted.append(
            {
                "pattern": pattern,
                "points": 1.0,
                "match_type": match_type,
            }
        )

    return accepted


# ------------------------------
# Публичные функции маппера
# ------------------------------

def build_task_content(
    row: QuestionInputRow,
    qtype: QuestionType,
    settings: Settings,
) -> Dict[str, Any]:
    """
    Собирает JSON-структуру task_content для LMS из одной строки Google Sheets.
    """
    base_type = _choice_base_type(qtype)

    # Текст условия + добавление ссылки, если включено в настройках
    statement_text = row.text
    if settings.prepend_input_link and row.input_link:
        statement_text = text.add_input_link_to_title(
            title=row.text,
            link=row.input_link,
            label=settings.input_link_label,
        )

    statement: Dict[str, Any] = {
        "text": statement_text,
    }
    if row.input_link:
        statement["input_link"] = {
            "url": row.input_link,
            "label": settings.input_link_label,
        }

    task_content: Dict[str, Any] = {
        "version": 1,
        "type": base_type,
        "subtype": qtype.value,
        "statement": statement,
        "hint": row.hint or None,
        "attachments": {},
        "ui": {},
        "tags": [],
    }

    # Видеоразбор
    if row.video_url:
        task_content["attachments"]["video"] = [
            {"url": row.video_url, "label": "Видеоразбор"}
        ]

    # UI-настройки
    if qtype in (QuestionType.SC, QuestionType.MC):
        task_content["ui"] = {
            "shuffle_options": True,
            "layout": "vertical",
            "show_hint_button": bool(row.hint),
        }
    else:
        task_content["ui"] = {
            "show_hint_button": bool(row.hint),
        }

    # Для SC/MC добавляем options (без is_correct/points — это в solution_rules)
    if qtype in (QuestionType.SC, QuestionType.MC):
        variants = parsing.parse_variants_block(row.variants_and_points)
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        options_for_content: List[Dict[str, Any]] = []

        for idx, (opt_text, _pts) in enumerate(variants):
            opt_id = letters[idx] if idx < len(letters) else f"opt_{idx+1}"
            options_for_content.append(
                {
                    "id": opt_id,
                    "text": opt_text,
                    "order": idx + 1,
                }
            )

        task_content["options"] = options_for_content

    # Формат ответа для SA/SA_COM/TA
    if qtype in (QuestionType.SA, QuestionType.SA_COM):
        task_content["answer_format"] = {
            "placeholder": "Введите краткий ответ",
            "comment_required": qtype is QuestionType.SA_COM,
            "comment_multiline": True,
        }
    elif qtype is QuestionType.TA:
        task_content["answer_format"] = {
            "placeholder": "Опишите решение подробно",
            "min_length": 0,
            "max_length": 5000,
        }

    return task_content


def build_solution_rules(
    row: QuestionInputRow,
    qtype: QuestionType,
) -> Dict[str, Any]:
    """
    Собирает JSON-структуру solution_rules для LMS.
    """
    base_type = _choice_base_type(qtype)

    # SC / MC: выбор вариантов
    if qtype in (QuestionType.SC, QuestionType.MC):
        data = _build_options_and_scoring_for_choice(row, qtype)
        options = data["options"]
        scoring = data["scoring"]
        max_score = data["max_score"]

        return {
            "version": 1,
            "type": base_type,
            "subtype": qtype.value,
            "max_score": max_score,
            "scoring": scoring,
            # В rules храним полную информацию по вариантам
            "options": [
                {
                    "id": opt["id"],
                    "is_correct": opt["is_correct"],
                    "points": opt["points"],
                }
                for opt in options
            ],
        }

    # SA / SA_COM: короткий ответ
    if qtype in (QuestionType.SA, QuestionType.SA_COM):
        accepted_answers = _build_accepted_answers_for_short_answer(row)

        return {
            "version": 1,
            "type": base_type,
            "subtype": qtype.value,
            "max_score": 1.0,
            "scoring": {
                "mode": "first_match",
                "case_sensitive": False,
                "trim_spaces": True,
                "normalize_spaces": True,
            },
            "accepted_answers": accepted_answers,
        }

    # TA: развёрнутый ответ, ручная проверка
    if qtype is QuestionType.TA:
        return {
            "version": 1,
            "type": base_type,
            "subtype": qtype.value,
            "max_score": 5.0,
            "scoring": {
                "mode": "manual",
                "rubric": [],
            },
        }

    # На всякий случай
    raise ValueError(f"Unsupported question type in build_solution_rules: {qtype!r}")


def map_difficulty_ru_to_lms_id(
    row: QuestionInputRow,
    meta_difficulties: List[Dict[str, Any]],
) -> int:
    """
    Сопоставляет row.difficulty_ru с name_ru в meta_difficulties.
    При отсутствии совпадения возвращает id сложности Easy (code='Easy') или 2.
    """
    target = (row.difficulty_ru or "").strip().lower()
    log.debug(
        "Маппинг сложности: source=%r (нормализовано=%r)", row.difficulty_ru, target
    )

    for d in meta_difficulties:
        name_ru = (d.get("name_ru") or "").strip().lower()
        if name_ru == target:
            return int(d["id"])

    # Fallback: ищем code == 'Easy'
    for d in meta_difficulties:
        if (d.get("code") or "").strip() == "Easy":
            log.warning(
                "Сложность %r не найдена, использую fallback 'Easy' (id=%s)",
                row.difficulty_ru,
                d.get("id"),
            )
            return int(d["id"])

    # Второй fallback — просто 2, как ты указал
    log.warning(
        "Сложность %r не найдена и 'Easy' отсутствует в meta, использую id=2 по умолчанию",
        row.difficulty_ru,
    )
    return 2


def map_quiz_title_to_course_id(
    row: QuestionInputRow,
    meta_courses: List[Dict[str, Any]],
) -> int:
    """
    Находит course_id в LMS по коду курса из строки Google Sheets (row.course_code).

    В meta_courses ожидается поле 'course_uid', по которому и маппим:
        row.course_code == course['course_uid'].
    """
    code = (row.course_code or "").strip()
    log.debug("Маппинг курса: course_code=%r", code)
    for c in meta_courses:
        uid = (c.get("course_uid") or "").strip()
        if uid == code:
            log.debug(
                "Курс найден: course_code=%r совпал с course_uid=%r (id=%s, title=%r)",
                code,
                uid,
                c.get("id"),
                c.get("title"),
            )
            return int(c["id"])

    log.error(
        "Не найден курс для course_code=%r в meta_courses (всего курсов=%d)",
        code,
        len(meta_courses),
    )
    raise ValueError(
        f"Не найден курс для course_code={code!r} в meta_courses. "
        "Проверьте 'Код курса' в таблице и настройки LMS."
    )


def row_to_task_upsert_item(
    row: QuestionInputRow,
    meta: Dict[str, Any],
    settings: Settings,
) -> Dict[str, Any]:
    """
    Преобразует одну строку Google Sheets в dict формата TaskUpsertItem
    для bulk-upsert в LMS.
    """
    if not row.question_code:
        log.error("Пустой 'Код вопроса' (question_code) в строке Google Sheets")
        raise ValueError("Пустой 'Код вопроса' (question_code) в строке Google Sheets")

    qtype = _map_qtype(row.qtype_code)

    difficulties_meta = meta.get("difficulties", []) or []
    courses_meta = meta.get("courses", []) or []

    difficulty_id = map_difficulty_ru_to_lms_id(row, difficulties_meta)
    course_id = map_quiz_title_to_course_id(row, courses_meta)
    log.debug(
        "Маппинг строки question_code=%r -> course_id=%s, difficulty_id=%s, qtype=%s",
        row.question_code,
        course_id,
        difficulty_id,
        qtype,
    )
    task_content = build_task_content(row, qtype, settings)
    solution_rules = build_solution_rules(row, qtype)

    max_score: Optional[float] = None
    if isinstance(solution_rules, dict):
        max_score = solution_rules.get("max_score")

    item: Dict[str, Any] = {
        "external_uid": row.question_code,
        "course_id": course_id,
        "difficulty_id": difficulty_id,
        "task_content": task_content,
        "solution_rules": solution_rules,
        "max_score": max_score,
    }
    log.debug(
        "Сформирован TaskUpsertItem для question_code=%r (course_id=%s, difficulty_id=%s, max_score=%s)",
        row.question_code,
        course_id,
        difficulty_id,
        max_score,
    )
    return item
