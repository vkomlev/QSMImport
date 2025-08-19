# app/qsm/repositories.py
from __future__ import annotations
from typing import Iterable, Dict, Any, List
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin

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
    
    def _table_has_columns(self, table: str, columns: list[str]) -> bool:
        """
        Проверяет наличие всех колонок в INFORMATION_SCHEMA.
        Возвращает True, если все заданные колонки существуют.
        """
        placeholders = ", ".join([":c" + str(i) for i in range(len(columns))])
        params = {f"c{i}": col for i, col in enumerate(columns)}
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(text(f"""
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = :tname
                      AND COLUMN_NAME IN ({placeholders})
                """), {"tname": table, **params}).fetchall()
                found = {r[0] for r in rows}
                return all(col in found for col in columns)
        except SQLAlchemyError as e:
            log.warning("Failed to introspect columns for %s: %s", table, e)
            return False
    
    # ---- quizzes ----

    def create_quiz(self, quiz_name: str) -> int:
        """
        Создаёт новый квиз с заполнением всех NOT NULL-полей из вашей схемы.
        В этой схеме колонки qpages/pages отсутствуют.
        """
        # Разумные дефолты под ваш пайплайн:
        defaults = {
            "message_before": "",
            "message_after": "",
            "message_comment": "",
            "message_end_template": "",
            "user_email_template": "",
            "admin_email_template": "",
            "submit_button_text": "Отправить",
            "name_field_text": "Фамилия и имя",
            "business_field_text": "",
            "email_field_text": "Email",
            "phone_field_text": "Телефон",
            "comment_field_text": "Комментарий",
            "email_from_text": "",
            "question_answer_template": "",
            "leaderboard_template": "",
            "quiz_system": 0,
            "randomness_order": 0,
            "loggedin_user_contact": 0,
            "show_score": 1,                # показывать набранные баллы
            "send_user_email": 0,
            "send_admin_email": 0,
            "contact_info_location": 0,     # где отображать контактную форму
            "user_name": 1,                 # Собирать только ФИО
            "user_comp": 0,
            "user_email": 0,
            "user_phone": 0,
            "admin_email": "",
            "comment_section": 0,
            "question_from_total": 0,
            "total_user_tries": 0,
            "total_user_tries_text": "",
            "certificate_template": "",
            "social_media": 0,
            "social_media_text": "",
            "pagination": 0,
            "pagination_text": "",
            "timer_limit": 0,
            "quiz_stye": "",                # в схеме именно 'quiz_stye'
            "question_numbering": 0,
            "quiz_settings": "",
            "theme_selected": "",
            # last_activity — зададим через NOW()
            "require_log_in": 0,
            "require_log_in_text": "",
            "limit_total_entries": 0,
            "limit_total_entries_text": "",
            "scheduled_timeframe": "",
            "scheduled_timeframe_text": "",
            "disable_answer_onselect": 0,
            "ajax_show_correct": 0,
            "quiz_views": 0,
            "quiz_taken": 0,
            "deleted": 0,
            "quiz_author_id": 0,
        }

        cols = [
            "quiz_name",
            "message_before", "message_after", "message_comment",
            "message_end_template", "user_email_template", "admin_email_template",
            "submit_button_text", "name_field_text", "business_field_text",
            "email_field_text", "phone_field_text", "comment_field_text",
            "email_from_text", "question_answer_template", "leaderboard_template",
            "quiz_system", "randomness_order", "loggedin_user_contact", "show_score",
            "send_user_email", "send_admin_email", "contact_info_location",
            "user_name", "user_comp", "user_email", "user_phone",
            "admin_email", "comment_section", "question_from_total", "total_user_tries",
            "total_user_tries_text", "certificate_template",
            "social_media", "social_media_text", "pagination", "pagination_text",
            "timer_limit", "quiz_stye", "question_numbering", "quiz_settings",
            "theme_selected",
            # last_activity отдельно
            "require_log_in", "require_log_in_text",
            "limit_total_entries", "limit_total_entries_text",
            "scheduled_timeframe", "scheduled_timeframe_text",
            "disable_answer_onselect", "ajax_show_correct",
            "quiz_views", "quiz_taken", "deleted", "quiz_author_id",
        ]

        named = {c: defaults[c] for c in cols if c != "quiz_name"}
        named["quiz_name"] = quiz_name

        placeholders = ", ".join([f":{c}" for c in cols])
        sql = f"""
            INSERT INTO wp_mlw_quizzes
            ({", ".join(cols)}, last_activity)
            VALUES ({placeholders}, NOW())
        """

        with self.engine.begin() as conn:
            conn.execute(text(sql), named)
            row = conn.execute(text("SELECT LAST_INSERT_ID() AS id")).fetchone()
            new_id = int(row.id)
            log.info("Created quiz '%s' with quiz_id=%s", quiz_name, new_id)
            return new_id

    def get_or_create_quiz_by_name(self, quiz_name: str) -> int:
        qid = self.get_quiz_id_by_name(quiz_name)
        if qid:
            return qid
        return self.create_quiz(quiz_name)
    
    
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
                        category: str = "",
                        question_name: str = "",
                        question_order: int = 0) -> int:
        """
        Вставляет вопрос и возвращает question_id.
        Заполняет все NOT NULL поля, требуемые старой схемой wp_mlw_questions.
        """
        # Преобразуем новый тип ("0"/"3"/"5") к старому числовому
        try:
            qtype_num = int(qtype_new)
        except ValueError:
            # страховка: одиночный/множественный выбор
            qtype_num = 0

        # Старые колонки ответов — оставляем пустыми/нулевыми (мы используем answer_array)
        empty_answers = {
            "answer_one": "",
            "answer_one_points": 0,
            "answer_two": "",
            "answer_two_points": 0,
            "answer_three": "",
            "answer_three_points": 0,
            "answer_four": "",
            "answer_four_points": 0,
            "answer_five": "",
            "answer_five_points": 0,
            "answer_six": "",
            "answer_six_points": 0,
            "correct_answer": 0,
        }

        sql = """
            INSERT INTO wp_mlw_questions
            (
                quiz_id,
                question_name,
                answer_array,
                answer_one, answer_one_points,
                answer_two, answer_two_points,
                answer_three, answer_three_points,
                answer_four, answer_four_points,
                answer_five, answer_five_points,
                answer_six, answer_six_points,
                correct_answer,
                question_answer_info,
                comments,
                hints,
                question_order,
                question_type,
                question_type_new,
                question_settings,
                category,
                linked_question,
                deleted,
                deleted_question_bank
            )
            VALUES
            (
                :quiz_id,
                :question_name,
                :answer_array,
                :answer_one, :answer_one_points,
                :answer_two, :answer_two_points,
                :answer_three, :answer_three_points,
                :answer_four, :answer_four_points,
                :answer_five, :answer_five_points,
                :answer_six, :answer_six_points,
                :correct_answer,
                :question_answer_info,
                :comments,
                :hints,
                :question_order,
                :question_type,
                :question_type_new,
                :question_settings,
                :category,
                :linked_question,
                :deleted,
                :deleted_question_bank
            )
        """

        params = {
            "quiz_id": quiz_id,
            "question_name": question_name or "",          # NOT NULL
            "answer_array": answer_array,                  # NOT NULL
            **empty_answers,                               # все старые поля
            "question_answer_info": question_answer_info or "",
            "comments": comments,
            "hints": hints or "",
            "question_order": question_order,
            "question_type": qtype_num,                    # старое числовое поле
            "question_type_new": qtype_new,                # новое текстовое поле (как раньше)
            "question_settings": question_settings,        # NOT NULL
            "category": category or "",                    # NOT NULL
            "linked_question": None,                       # NULL допустим
            "deleted": 0,
            "deleted_question_bank": 0,
        }

        with self.engine.begin() as conn:
            conn.execute(text(sql), params)
            row = conn.execute(text("SELECT LAST_INSERT_ID() AS id")).fetchone()
            qid = int(row.id)
            log.info("Inserted question quiz_id=%s question_id=%s", quiz_id, qid)
            return qid


    def update_quiz_pages(self, quiz_id: int, question_ids: List[int]) -> None:
        """
        Обновляет qpages/pages, если такие колонки существуют в схеме.
        Иначе — логирует предупреждение и завершает без ошибки.
        """
        if not self._table_has_columns("wp_mlw_quizzes", ["qpages", "pages"]):
            log.warning("Columns qpages/pages not found in wp_mlw_quizzes. Skipping pages update for quiz_id=%s", quiz_id)
            return

        from .builders import build_qpages_single_page, build_pages_single_page  # локальный импорт
        qpages = build_qpages_single_page(question_ids)
        pages = build_pages_single_page(question_ids)
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE wp_mlw_quizzes SET qpages=:qp, pages=:pg WHERE quiz_id=:qid
            """), {"qp": qpages, "pg": pages, "qid": quiz_id})
            log.info("Updated quiz pages quiz_id=%s -> %s questions", quiz_id, len(question_ids))
    
    # ---- posts (qsm_quiz) ----

    def get_quiz_post_id(self, quiz_id: int) -> int | None:
        """
        Ищет пост типа qsm_quiz по точному шорткоду [mlw_quizmaster quiz=ID].
        Возвращает ID поста или None.
        """
        shortcode = f"[mlw_quizmaster quiz={quiz_id}]"
        with self.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT ID FROM wp_posts
                WHERE post_type='qsm_quiz'
                  AND post_status<>'trash'
                  AND post_content LIKE :sc
                ORDER BY ID DESC
                LIMIT 1
            """), {"sc": f"%{shortcode}%"}).fetchone()
            return int(row.ID) if row else None

    def _slug_exists(self, slug: str) -> bool:
        with self.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT 1 FROM wp_posts WHERE post_name=:slug LIMIT 1
            """), {"slug": slug}).fetchone()
            return bool(row)

    def _make_unique_slug(self, base_slug: str) -> str:
        """
        Делает уникальный слаг: base, base-2, base-3, ...
        """
        slug = base_slug
        counter = 2
        while self._slug_exists(slug):
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug

    def create_quiz_post(self,
                         quiz_id: int,
                         quiz_name: str,
                         author_id: int = 1,
                         site_url: str | None = None,
                         status: str = "private") -> int:
        """
        Создаёт пост типа qsm_quiz с шорткодом на данный quiz_id.
        Возвращает ID нового поста.
        """
        from app.utils.text import slugify  # ваш помощник-транслитератор

        now_local = datetime.now()
        now_gmt = datetime.now(timezone.utc).replace(tzinfo=None)

        content = f"[mlw_quizmaster quiz={quiz_id}]"
        slug = self._make_unique_slug(slugify(quiz_name))

        # Базовые поля, достаточные для появления поста в админке
        cols = [
            "post_author", "post_date", "post_date_gmt", "post_content", "post_title",
            "post_excerpt", "post_status", "comment_status", "ping_status", "post_password",
            "post_name", "to_ping", "pinged", "post_modified", "post_modified_gmt",
            "post_content_filtered", "post_parent", "menu_order", "post_type",
            "post_mime_type", "comment_count", "guid"
        ]
        vals = {
            "post_author": author_id,
            "post_date": now_local.strftime("%Y-%m-%d %H:%M:%S"),
            "post_date_gmt": now_gmt.strftime("%Y-%m-%d %H:%M:%S"),
            "post_content": content,
            "post_title": quiz_name,
            "post_excerpt": "",
            "post_status": status,          # 'private' или 'draft'
            "comment_status": "closed",
            "ping_status": "closed",
            "post_password": "",
            "post_name": slug,
            "to_ping": "",
            "pinged": "",
            "post_modified": now_local.strftime("%Y-%m-%d %H:%M:%S"),
            "post_modified_gmt": now_gmt.strftime("%Y-%m-%d %H:%M:%S"),
            "post_content_filtered": "",
            "post_parent": 0,
            "menu_order": 0,
            "post_type": "qsm_quiz",
            "post_mime_type": "",
            "comment_count": 0,
            # временно пустой guid — обновим ниже, когда узнаем ID
            "guid": "",
        }

        placeholders = ", ".join(f":{c}" for c in cols)
        sql = f"""
            INSERT INTO wp_posts ({", ".join(cols)})
            VALUES ({placeholders})
        """

        with self.engine.begin() as conn:
            conn.execute(text(sql), vals)
            row = conn.execute(text("SELECT LAST_INSERT_ID() AS id")).fetchone()
            post_id = int(row.id)

            # Проставим GUID (опционально)
            if site_url:
                guid = urljoin(site_url.rstrip("/") + "/", f"?post_type=qsm_quiz&p={post_id}")
                conn.execute(text("UPDATE wp_posts SET guid=:g WHERE ID=:id"),
                             {"g": guid, "id": post_id})

            log.info("Created wp_posts qsm_quiz post_id=%s for quiz_id=%s", post_id, quiz_id)
            return post_id

    def ensure_quiz_post(self,
                         quiz_id: int,
                         quiz_name: str,
                         author_id: int = 1,
                         site_url: str | None = None,
                         status: str = "private") -> int:
        """
        Возвращает ID поста qsm_quiz. Создаёт, если не найден.
        """
        pid = self.get_quiz_post_id(quiz_id)
        if pid:
            return pid
        return self.create_quiz_post(quiz_id, quiz_name, author_id=author_id, site_url=site_url, status=status)

