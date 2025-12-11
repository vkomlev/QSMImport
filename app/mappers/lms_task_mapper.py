# app/mappers/lms_task_mapper.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import logging

from app.config import Settings
from app.models.enums import QuestionType
from app.models.question_input import QuestionInputRow
from app.utils.parsing import parse_correct_list, parse_variants_block
from app.utils.text import add_input_link_to_title, normalize

log = logging.getLogger(__name__)


# --- Вспомогательные структуры ------------------------------------------------


@dataclass
class ChoiceOption:
    id: str          # "A", "B", ...
    text: str        # текст варианта
    is_correct: bool
    points: float    # "сырой" вес варианта (из правой части || или 1)


# --- Построение TaskContent ---------------------------------------------------


def _build_stem_text(row: QuestionInputRow, settings: Settings) -> str:
    """
    Формируем основной текст задания (TaskContent.stem).

    Логика:
      - нормализуем текст;
      - по флагу prepend_input_link добавляем блок "Входные данные" внутрь формулировки;
      - оставляем без HTML-структуры, чистый markdown/текст.
    """
    base = normalize(row.text or "")

    if settings.prepend_input_link and row.input_link:
        # ВАЖНО: вызываем позиционно, без именованных аргументов
        stem = add_input_link_to_title(
            base,
            row.input_link,
            settings.input_link_label,
        )
    else:
        stem = base

    return stem


def _build_media(row: QuestionInputRow) -> Optional[Dict[str, Any]]:
    """
    TaskMedia по схеме TaskMedia из OpenAPI. 

    media = {
        "image_url": ... | None,
        "audio_url": ... | None,
        "video_url": ... | None,
    }
    """
    # В исходной таблице точно есть video_url, медиа-URL (картинка)
    image_url = getattr(row, "media_url", None) or None
    video_url = (row.video_url or "").strip() or None

    if not image_url and not video_url:
        return None

    return {
        "image_url": image_url,
        "audio_url": None,
        "video_url": video_url,
    }


def _parse_choice_options(
    row: QuestionInputRow,
    qtype: QuestionType,
) -> Tuple[List[ChoiceOption], List[str]]:
    """
    Разобрать блок «Варианты ответа и баллы» и «Правильный ответ» для SC/MC.

    Возвращает:
      - список ChoiceOption (уже с буквенными id "A", "B", ...),
      - список правильных id (["A", "C"] и т.п.).
    """
    # Табличные варианты вида "Текст||0.5" построчно
    raw_variants = row.variants_and_points or ""
    parsed = parse_variants_block(raw_variants)

    # parsed: list[tuple[str, Optional[float]]]
    # Если баллы не заданы -> будем считать points=1 для всех правильных
    options: List[ChoiceOption] = []

    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for idx, (text, pts) in enumerate(parsed):
        option_id = letters[idx]
        options.append(
            ChoiceOption(
                id=option_id,
                text=normalize(text),
                is_correct=False,   # пока не знаем, заполним ниже
                points=float(pts) if pts is not None else 0.0,
            )
        )

    # Правильные ответы в таблице — текст вариантов через ';'
    # Маппим по тексту, чтобы не зависеть от позиции
    correct_texts = [normalize(t) for t in parse_correct_list(row.correct_answer)]

    correct_ids: List[str] = []
    for opt in options:
        if opt.text in correct_texts:
            opt.is_correct = True
            correct_ids.append(opt.id)

    return options, correct_ids


def build_task_content(
    row: QuestionInputRow,
    qtype: QuestionType,
    settings: Settings,
) -> Dict[str, Any]:
    """
    Построить JSON в формате TaskContent по схеме бекенда. 

    Обязательные поля:
      - type: "SC"|"MC"|"SA"|"SA_COM"|"TA"
      - stem: формулировка задания

    Дополнительные:
      - code: внешний код задачи (совпадает с external_uid)
      - title: можно взять тему / краткий заголовок
      - prompt: текст подсказки
      - media: TaskMedia
      - options: список TaskOption для SC/MC
      - tags: пока пустой список
      - difficulty_code, course_uid: не заполняем, так как у нас есть id.
    """
    stem = _build_stem_text(row, settings)
    media = _build_media(row)

    # Заголовок можно взять как тему или укороченный stem
    title = row.quiz_title or stem[:120]

    content: Dict[str, Any] = {
        "type": qtype.value,
        "code": (row.question_code or "").strip() or None,
        "title": title,
        "stem": stem,
        "prompt": (row.hint or "").strip() or None,
        "media": media,
        "options": None,          # ниже заполним для SC/MC
        "tags": [],
        "difficulty_code": None,
        "course_uid": None,
    }

    if qtype in (QuestionType.SC, QuestionType.MC):
        options, _ = _parse_choice_options(row, qtype)

        content["options"] = [
            {
                "id": opt.id,
                "text": opt.text,
                "explanation": None,
                "is_active": True,
            }
            for opt in options
        ]
    else:
        content["options"] = None

    log.debug(
        "build_task_content: external_uid=%r, type=%s",
        row.question_code,
        qtype.value,
    )

    return content


# --- Построение SolutionRules -------------------------------------------------


def _build_penalties() -> Dict[str, int]:
    """
    PenaltiesRules по умолчанию. 
    """
    return {
        "wrong_answer": 0,
        "missing_answer": 0,
        "extra_wrong_mc": 0,
    }


def _build_solution_for_choice(
    row: QuestionInputRow,
    qtype: QuestionType,
) -> Tuple[Dict[str, Any], int]:
    """
    SolutionRules для SC/MC.

    Возвращает:
      - dict SolutionRules (без short_answer/text_answer),
      - max_score.
    """
    options, correct_ids = _parse_choice_options(row, qtype)

    # Если баллы не заданы — points=1 для всех правильных.
    # Если заданы — суммируем points по правильным.
    has_explicit_points = any(opt.points > 0 for opt in options)
    if not has_explicit_points:
        for opt in options:
            if opt.is_correct:
                opt.points = 1.0

    max_score = int(round(sum(opt.points for opt in options if opt.is_correct)))

    if qtype is QuestionType.SC:
        scoring_mode = "all_or_nothing"
    else:
        scoring_mode = "partial"

    solution: Dict[str, Any] = {
        "max_score": max_score,
        "scoring_mode": scoring_mode,
        "auto_check": True,
        "manual_review_required": False,
        "correct_options": correct_ids,
        "partial_rules": [],    # простая схема — по correct_options
        "short_answer": None,
        "text_answer": None,
        "penalties": _build_penalties(),
    }

    log.debug(
        "_build_solution_for_choice: external_uid=%r, type=%s, max_score=%s, correct=%s",
        row.question_code,
        qtype.value,
        max_score,
        correct_ids,
    )

    return solution, max_score


def _build_short_answer_rules(
    row: QuestionInputRow,
    settings: Optional[Settings],
) -> Tuple[Dict[str, Any], int, str, bool, bool]:
    """
    Построить ShortAnswerRules + max_score для SA/SA_COM. 

    Возвращает:
      - short_answer_rules dict,
      - max_score (int),
      - scoring_mode ("all_or_nothing"/"partial"),
      - auto_check (bool),
      - manual_review_required (bool).
    """
    raw = (row.correct_answer or "").strip()

    # Если settings не передали – пусть будет дефолт 1 балл
    default_score = int(
        round(getattr(settings, "default_points_short_answer", 1.0))
    )

    normalization = ["trim", "lower", "collapse_spaces"]

    if not raw:
        # Нет эталона – автоматом не проверяем
        short_answer = {
            "normalization": normalization,
            "accepted_answers": [],
            "use_regex": False,
            "regex": None,
        }
        return short_answer, default_score, "all_or_nothing", False, True

    # Regex режим: префикс "re:"
    if raw.startswith("re:"):
        pattern = raw[3:].strip()
        short_answer = {
            "normalization": [],
            "accepted_answers": [],
            "use_regex": True,
            "regex": pattern,
        }
        # regex — всё или ничего
        return short_answer, default_score, "all_or_nothing", True, False

    # Иначе — список допустимых строк через ';'
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    accepted = [
        {
            "value": p,
            "score": default_score,
        }
        for p in parts
    ]
    short_answer = {
        "normalization": normalization,
        "accepted_answers": accepted,
        "use_regex": False,
        "regex": None,
    }

    # Если несколько вариантов с одинаковыми баллами — считаем all_or_nothing
    scoring_mode = "all_or_nothing"
    auto_check = True
    manual_review_required = False

    return short_answer, default_score, scoring_mode, auto_check, manual_review_required


def _build_solution_for_ta() -> Tuple[Dict[str, Any], int]:
    """
    SolutionRules для развёрнутого ответа (TA). 

    Логика:
      - только ручная проверка,
      - простая рубрика с одним критерием "content".
    """
    max_score = 5

    text_answer = {
        "auto_check": False,
        "rubric": [
            {
                "id": "content",
                "title": "Содержание ответа",
                "max_score": max_score,
            }
        ],
    }

    solution: Dict[str, Any] = {
        "max_score": max_score,
        "scoring_mode": "custom",
        "auto_check": False,
        "manual_review_required": True,
        "correct_options": [],
        "partial_rules": [],
        "short_answer": None,
        "text_answer": text_answer,
        "penalties": _build_penalties(),
    }

    return solution, max_score


def build_solution_rules(
    row: QuestionInputRow,
    qtype: QuestionType,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    """
    Построить JSON в формате SolutionRules по схеме бекенда. 
    """
    if qtype in (QuestionType.SC, QuestionType.MC):
        solution, _ = _build_solution_for_choice(row, qtype)
        return solution

    if qtype in (QuestionType.SA, QuestionType.SA_COM):
        short_answer, max_score, scoring_mode, auto_check, manual_review_required = (
            _build_short_answer_rules(row, settings)
        )

        # Для SA_COM требуем ручную дооценку комментария
        if qtype is QuestionType.SA_COM:
            manual_review_required = True

        solution = {
            "max_score": max_score,
            "scoring_mode": scoring_mode,
            "auto_check": auto_check,
            "manual_review_required": manual_review_required,
            "correct_options": [],
            "partial_rules": [],
            "short_answer": short_answer,
            "text_answer": None,
            "penalties": _build_penalties(),
        }

        log.debug(
            "build_solution_rules(SA*): external_uid=%r, max_score=%s, mode=%s",
            row.question_code,
            max_score,
            scoring_mode,
        )
        return solution

    if qtype is QuestionType.TA:
        solution, _ = _build_solution_for_ta()
        log.debug(
            "build_solution_rules(TA): external_uid=%r, max_score=%s",
            row.question_code,
            solution["max_score"],
        )
        return solution

    # На всякий случай: неизвестный тип — пустые правила с max_score=0
    log.warning(
        "build_solution_rules: неизвестный тип %r для external_uid=%r",
        qtype,
        row.question_code,
    )
    return {
        "max_score": 0,
        "scoring_mode": "all_or_nothing",
        "auto_check": False,
        "manual_review_required": True,
        "correct_options": [],
        "partial_rules": [],
        "short_answer": None,
        "text_answer": None,
        "penalties": _build_penalties(),
    }


# --- Маппинг сложностей и курсов ---------------------------------------------


def map_difficulty_ru_to_lms_id(
    row: QuestionInputRow,
    meta_difficulties: List[Dict[str, Any]],
) -> int:
    """
    Поиск difficulty_id по русскому названию сложности (name_ru).
    Если не нашли — используем id для 'Easy' (2) как дефолт.
    """
    name = (row.difficulty_ru or "").strip()

    for d in meta_difficulties:
        if (d.get("name_ru") or "").strip() == name:
            return int(d["id"])

    # дефолт: Easy => id=2 (как мы договорились)
    log.warning(
        "Не удалось сопоставить сложность %r, используем дефолт difficulty_id=2",
        name,
    )
    return 2


def map_quiz_title_to_course_id(
    row: QuestionInputRow,
    meta_courses: List[Dict[str, Any]],
) -> int:
    """
    Маппинг курса по коду/uid из таблицы.

    Приоритет:
      1) row.course_code -> course.course_uid (если совпадает),
      2) если найден ровно один курс в meta, берём его id,
      3) иначе — ошибка.
    """
    code = (row.course_code or "").strip()

    if code:
        for c in meta_courses:
            if (c.get("course_uid") or "").strip() == code:
                return int(c["id"])

    if len(meta_courses) == 1:
        return int(meta_courses[0]["id"])

    titles = ", ".join(f"{c['id']}:{c['title']}" for c in meta_courses)
    raise ValueError(
        f"Не удалось сопоставить курс по коду {code!r} "
        f"и нельзя выбрать единственный курс из meta: {titles}"
    )


# --- Главный маппер в TaskUpsertItem -----------------------------------------


def row_to_task_upsert_item(
    row: QuestionInputRow,
    meta: Dict[str, Any],
    settings: Settings,
) -> Dict[str, Any]:
    """
    Собрать dict в формате TaskUpsertItem для /api/v1/tasks/bulk-upsert.

    Структура:
      - external_uid: str
      - course_id: int
      - difficulty_id: int
      - task_content: TaskContent
      - solution_rules: SolutionRules | None
      - max_score: int | None
    """
    raw_qtype = (row.qtype_code or "").strip().upper()
    try:
        qtype = QuestionType(raw_qtype)
    except Exception as e:
        log.error(
            "Неизвестный тип задания qtype_code=%r для question_code=%r: %s",
            row.qtype_code,
            row.question_code,
            e,
        )
        raise

    course_id = map_quiz_title_to_course_id(row, meta["courses"])
    difficulty_id = map_difficulty_ru_to_lms_id(row, meta["difficulties"])

    task_content = build_task_content(row, qtype, settings)
    solution_rules = build_solution_rules(row, qtype, settings)

    max_score = int(solution_rules.get("max_score", 0))

    item = {
        "external_uid": (row.question_code or "").strip() or None,
        "course_id": course_id,
        "difficulty_id": difficulty_id,
        "task_content": task_content,
        "solution_rules": solution_rules,
        "max_score": max_score,
    }

    log.info(
        "row_to_task_upsert_item: external_uid=%r, type=%s, course_id=%s, "
        "difficulty_id=%s, max_score=%s",
        item["external_uid"],
        qtype.value,
        course_id,
        difficulty_id,
        max_score,
    )

    return item

