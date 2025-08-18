from __future__ import annotations
from typing import Iterable, Dict, Any, List
from sqlalchemy import create_engine, text
import logging

log = logging.getLogger(__name__)

class QsmRepository:
    """
    Репозиторий для операций с QSM:
    - поиск/создание термов
    - вставка вопросов
    - привязка вопроса к квизу (qpages/pages)
    """

    def __init__(self, db_url: str):
        self.engine = create_engine(db_url, pool_pre_ping=True)

    # ---- terms ----

    def ensure_terms(self, names: List[str]) -> Dict[str, int]:
        """
        Гарантирует наличие терминов (wp_terms.name).
        Возвращает map name -> term_id.
        """
        res: Dict[str, int] = {}
        with self.engine.begin() as conn:
            for name in names:
                row = conn.execute(text("SELECT term_id FROM wp_terms WHERE name=:n"), {"n": name}).fetchone()
                if row:
                    res[name] = int(row.term_id)
                    continue
                conn.execute(text("INSERT INTO wp_terms (name, slug, term_group) VALUES (:n, :s, 0)"),
                             {"n": name, "s": name.lower()})
                row = conn.execute(text("SELECT term_id FROM wp_terms WHERE name=:n"), {"n": name}).fetchone()
                res[name] = int(row.term_id)
                log.info("Created term '%s' id=%s", name, res[name])
        return res

    def upsert_question_term(self, question_id: int, quiz_id: int, term_id: int, taxonomy: str = "qsm_category") -> None:
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO wp_mlw_question_terms (question_id, quiz_id, term_id, taxonomy)
                SELECT :qid, :quiz, :tid, :tx FROM DUAL
                WHERE NOT EXISTS (
                  SELECT 1 FROM wp_mlw_question_terms
                  WHERE question_id=:qid AND quiz_id=:quiz AND term_id=:tid AND taxonomy=:tx
                )
            """), {"qid": question_id, "quiz": quiz_id, "tid": term_id, "tx": taxonomy})

    # ---- questions ----

    def get_quiz_id_by_name(self, quiz_name: str) -> int | None:
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT quiz_id FROM wp_mlw_quizzes WHERE quiz_name=:n"), {"n": quiz_name}).fetchone()
            return int(row.quiz_id) if row else None

    def insert_question(self,
                        quiz_id: int,
                        qtype_new: str,
                        question_settings: str,
                        answer_array: str,
                        comments: int,
                        question_answer_info: str = "",
                        hints: str = "",
                        category: str = "") -> int:
        """
        Вставляет вопрос и возвращает question_id.
        """
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO wp_mlw_questions
                (quiz_id, question_type_new, question_settings, answer_array, comments, question_answer_info, hints, category)
                VALUES (:quiz_id, :qt, :qs, :aa, :cm, :qinfo, :hints, :cat)
            """), {"quiz_id": quiz_id, "qt": qtype_new, "qs": question_settings,
                   "aa": answer_array, "cm": comments, "qinfo": question_answer_info,
                   "hints": hints, "cat": category})
            row = conn.execute(text("SELECT LAST_INSERT_ID() AS id")).fetchone()
            qid = int(row.id)
            log.info("Inserted question quiz_id=%s question_id=%s", quiz_id, qid)
            return qid

    def update_quiz_pages(self, quiz_id: int, question_ids: List[int]) -> None:
        """
        Обновляет qpages/pages (одна страница).
        """
        from .builders import build_qpages_single_page, build_pages_single_page  # локальный импорт
        qpages = build_qpages_single_page(question_ids)
        pages = build_pages_single_page(question_ids)
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE wp_mlw_quizzes SET qpages=:qp, pages=:pg WHERE quiz_id=:qid
            """), {"qp": qpages, "pg": pages, "qid": quiz_id})
            log.info("Updated quiz pages quiz_id=%s -> %s questions", quiz_id, len(question_ids))
