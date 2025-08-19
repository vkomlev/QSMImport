# app/qsm/repositories.py
from __future__ import annotations
from typing import Iterable, Dict, Any, List, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin
from app.utils.text import slugify
import re

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
            "quiz_settings": self._minimal_quiz_settings(system=1),
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

    def _find_quiz_post_by_meta(self, quiz_id: int) -> Optional[int]:
        """
        Возвращает ID поста типа qsm_quiz по метаданным (wp_postmeta.meta_key='quiz_id').
        Если не найдено — None.
        """
        with self.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT p.ID
                  FROM wp_posts p
                  JOIN wp_postmeta m ON m.post_id = p.ID
                 WHERE p.post_type = 'qsm_quiz'
                   AND p.post_status <> 'trash'
                   AND m.meta_key = 'quiz_id'
                   AND m.meta_value = :qid
                 LIMIT 1
            """), {"qid": str(quiz_id)}).fetchone()
            return int(row.ID) if row else None

    def get_quiz_post_id(self, quiz_id: int) -> Optional[int]:
        """
        Ищет пост qsm_quiz для данного quiz_id:
        1) по метаданным (wp_postmeta.quiz_id)
        2) по точному содержимому шорткода в post_content
        """
        pid = self._find_quiz_post_by_meta(quiz_id)
        if pid:
            return pid

        shortcode = f"[mlw_quizmaster quiz={quiz_id}]"
        with self.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT ID FROM wp_posts
                WHERE post_type='qsm_quiz'
                  AND post_status<>'trash'
                  AND post_content = :sc
                LIMIT 1
            """), {"sc": shortcode}).fetchone()
            return int(row.ID) if row else None

    def upsert_postmeta(self, post_id: int, meta_key: str, meta_value: str) -> None:
        """
        Вставляет/обновляет wp_postmeta. Если ключ уже есть — обновляет значение.
        """
        with self.engine.begin() as conn:
            row = conn.execute(text("""
                SELECT meta_id FROM wp_postmeta
                 WHERE post_id=:pid AND meta_key=:k
                 LIMIT 1
            """), {"pid": post_id, "k": meta_key}).fetchone()
            if row:
                conn.execute(text("""
                    UPDATE wp_postmeta
                       SET meta_value=:v
                     WHERE meta_id=:mid
                """), {"v": meta_value, "mid": int(row.meta_id)})
            else:
                conn.execute(text("""
                    INSERT INTO wp_postmeta (post_id, meta_key, meta_value)
                    VALUES (:pid, :k, :v)
                """), {"pid": post_id, "k": meta_key, "v": meta_value})

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

    def create_or_update_quiz_post(
        self,
        quiz_id: int,
        title: str,
        author_id: int,
        status: str = "publish",
        site_base_url: str | None = None,
        force_update_guid: bool = False,
    ) -> int:
        """
        Создаёт/обновляет пост типа qsm_quiz с шорткодом и гарантирует wp_postmeta('quiz_id').
        Возвращает post_id.
        """
        shortcode = f"[mlw_quizmaster quiz={quiz_id}]"
        safe_slug = self._make_unique_slug(slugify(title))
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        with self.engine.begin() as conn:
            # 1) пробуем найти по метаданным
            row = conn.execute(text("""
                SELECT p.ID
                  FROM wp_posts p
                  JOIN wp_postmeta m ON m.post_id = p.ID
                 WHERE p.post_type='qsm_quiz'
                   AND p.post_status<>'trash'
                   AND m.meta_key='quiz_id'
                   AND m.meta_value=:qid
                 LIMIT 1
            """), {"qid": str(quiz_id)}).fetchone()

            if row:
                post_id = int(row.ID)
                conn.execute(text("""
                    UPDATE wp_posts
                       SET post_title=:title,
                           post_name=:slug,
                           post_status=:status,
                           post_author=:author,
                           post_modified=:now_local,
                           post_modified_gmt=:now_gmt,
                           post_content=:sc
                     WHERE ID=:pid
                """), {
                    "title": title, "slug": safe_slug, "status": status, "author": author_id,
                    "now_local": now, "now_gmt": now, "sc": shortcode, "pid": post_id
                })
                # meta quiz_id гарантированно будет (на всякий случай — апдейт)
                conn.execute(text("""
                    UPDATE wp_postmeta SET meta_value=:qid
                     WHERE post_id=:pid AND meta_key='quiz_id'
                """), {"qid": str(quiz_id), "pid": post_id})
                if site_base_url and force_update_guid:
                    guid = f"{site_base_url.rstrip('/')}/?post_type=qsm_quiz&p={post_id}"
                    conn.execute(text("UPDATE wp_posts SET guid=:g WHERE ID=:pid"),
                                 {"g": guid, "pid": post_id})
                return post_id

            # 2) пробуем найти по шорткоду
            row = conn.execute(text("""
                SELECT ID FROM wp_posts
                 WHERE post_type='qsm_quiz'
                   AND post_content=:sc
                 LIMIT 1
            """), {"sc": shortcode}).fetchone()

            if row:
                post_id = int(row.ID)
                conn.execute(text("""
                    UPDATE wp_posts
                       SET post_title=:title,
                           post_name=:slug,
                           post_status=:status,
                           post_author=:author,
                           post_modified=:now_local,
                           post_modified_gmt=:now_gmt
                     WHERE ID=:pid
                """), {
                    "title": title, "slug": safe_slug, "status": status, "author": author_id,
                    "now_local": now, "now_gmt": now, "pid": post_id
                })
            else:
                # 3) создаём новый
                vals = {
                    "post_author": author_id,
                    "post_date": now, "post_date_gmt": now,
                    "post_content": shortcode,
                    "post_title": title,
                    "post_excerpt": "",
                    "post_status": status,
                    "comment_status": "closed",
                    "ping_status": "closed",
                    "post_password": "",
                    "post_name": safe_slug,
                    "to_ping": "", "pinged": "",
                    "post_modified": now, "post_modified_gmt": now,
                    "post_content_filtered": "",
                    "post_parent": 0,
                    "menu_order": 0,
                    "post_type": "qsm_quiz",
                    "post_mime_type": "",
                    "comment_count": 0,
                }
                placeholders = ", ".join([f":{k}" for k in vals.keys()])
                conn.execute(text(f"""
                    INSERT INTO wp_posts ({", ".join(vals.keys())})
                    VALUES ({placeholders})
                """), vals)
                r = conn.execute(text("SELECT LAST_INSERT_ID() AS id")).fetchone()
                post_id = int(r.id)
                if site_base_url and force_update_guid:
                    guid = f"{site_base_url.rstrip('/')}/?post_type=qsm_quiz&p={post_id}"
                    conn.execute(text("UPDATE wp_posts SET guid=:g WHERE ID=:pid"),
                                 {"g": guid, "pid": post_id})

            # ГАРАНТИЯ: postmeta('quiz_id' = quiz_id)
            conn.execute(text("""
                INSERT INTO wp_postmeta (post_id, meta_key, meta_value)
                SELECT :pid, 'quiz_id', :qid FROM DUAL
                 WHERE NOT EXISTS (
                    SELECT 1 FROM wp_postmeta
                     WHERE post_id=:pid AND meta_key='quiz_id'
                 )
            """), {"pid": post_id, "qid": str(quiz_id)})
            conn.execute(text("""
                UPDATE wp_postmeta SET meta_value=:qid
                 WHERE post_id=:pid AND meta_key='quiz_id'
            """), {"pid": post_id, "qid": str(quiz_id)})

            return post_id

    def set_quiz_author(self, quiz_id: int, user_id: int) -> None:
        """Обновляет wp_mlw_quizzes.quiz_author_id."""
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE wp_mlw_quizzes SET quiz_author_id=:uid WHERE quiz_id=:qid
            """), {"uid": user_id, "qid": quiz_id})

    def ensure_quiz_post(self, quiz_id: int, quiz_name: str, author_id: int = 1,
                         site_url: str | None = None, status: str = "publish") -> int:
        """
        Возвращает ID поста qsm_quiz и гарантирует meta('quiz_id').
        """
        return self.create_or_update_quiz_post(
            quiz_id=quiz_id, title=quiz_name, author_id=author_id,
            site_base_url=site_url, status=status, force_update_guid=False
        )
    
    # === helpers for quiz_settings ===

    _SYSTEM_PAIR_RE = re.compile(r'(s:6:"system";s:1:")([01])(")')

    @staticmethod
    def _minimal_quiz_settings(system: int = 1) -> str:
        """
        Минимально достаточный сериализованный блок quiz_settings с quiz_options->system.
        Синтаксис — PHP serialize; структура совместима с тем, что QSM сам пишет.
        """
        # Вариант, аналогичный тому, что вы видели у квизов 28+, но с system="1"
        # a:3:{s:12:"quiz_options";s:...:"a:23:{ ... s:6:"system";s:1:"1"; ... }"; s:9:"quiz_text";s:...; s:17:"quiz_leaderboards";s:...;}
        # Чтобы не городить полный конструктор сериализации, берём проверенную заготовку.
        return (
            'a:3:{'
              's:12:"quiz_options";s:714:'
                '"a:23:{'
                   's:6:"system";s:1:"%s";'
                   's:21:"loggedin_user_contact";s:1:"0";'
                   's:21:"contact_info_location";s:1:"0";'
                   's:9:"user_name";s:1:"1";'
                   's:9:"user_comp";s:1:"0";'
                   's:10:"user_email";s:1:"0";'
                   's:10:"user_phone";s:1:"0";'
                   's:15:"comment_section";s:1:"0";'
                   's:16:"randomness_order";s:1:"0";'
                   's:19:"question_from_total";s:1:"0";'
                   's:21:"question_per_category";N;'
                   's:16:"total_user_tries";s:1:"0";'
                   's:12:"social_media";s:1:"0";'
                   's:10:"pagination";s:1:"0";'
                   's:11:"timer_limit";s:1:"0";'
                   's:18:"question_numbering";s:1:"0";'
                   's:14:"require_log_in";s:1:"0";'
                   's:19:"limit_total_entries";s:1:"0";'
                   's:20:"scheduled_time_start";s:0:"";'
                   's:18:"scheduled_time_end";s:0:"";'
                   's:23:"disable_answer_onselect";s:1:"0";'
                   's:17:"ajax_show_correct";s:1:"0";'
                   's:21:"preferred_date_format";N;'
                '}";'
              's:9:"quiz_text";s:810:'
                '"a:20:{'
                   's:14:"message_before";s:0:"";'
                   's:15:"message_comment";s:0:"";'
                   's:20:"message_end_template";s:0:"";'
                   's:18:"comment_field_text";s:22:"Комментарий";'
                   's:24:"question_answer_template";s:0:"";'
                   's:18:"submit_button_text";s:18:"Отправить";'
                   's:15:"name_field_text";s:24:"Фамилия и имя";'
                   's:19:"business_field_text";s:0:"";'
                   's:16:"email_field_text";s:5:"Email";'
                   's:16:"phone_field_text";s:14:"Телефон";'
                   's:21:"total_user_tries_text";s:0:"";'
                   's:20:"twitter_sharing_text";s:0:"";'
                   's:21:"facebook_sharing_text";s:0:"";'
                   's:21:"linkedin_sharing_text";s:0:"";'
                   's:20:"previous_button_text";s:10:"Назад";'
                   's:16:"next_button_text";s:10:"Далее";'
                   's:19:"require_log_in_text";s:0:"";'
                   's:24:"limit_total_entries_text";s:0:"";'
                   's:24:"scheduled_timeframe_text";s:0:"";'
                   's:22:"start_quiz_survey_text";s:10:"Start Quiz";'
                '}";'
              's:17:"quiz_leaderboards";s:28:"a:1:{s:8:"template";s:0:"";}";'
            '}'
        ) % (str(int(system)))

    def ensure_quiz_system_combined(self, quiz_id: int, force_show_score: bool = True) -> None:
        """
        Делает grading-систему комбинированной: 'system' = 1 в quiz_settings.
        При необходимости включает show_score=1.
        Работает бережно: если строки нет — создаёт минимальный блок; если есть — только правит system.
        """
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT quiz_settings, show_score FROM wp_mlw_quizzes WHERE quiz_id=:qid"),
                {"qid": quiz_id}
            ).fetchone()
            if not row:
                log.warning("Quiz %s not found when ensuring 'system=1'", quiz_id)
                return

            qset: Optional[str] = row.quiz_settings
            show_score: int = int(row.show_score or 0)

            if not qset:
                new_qset = self._minimal_quiz_settings(system=1)
            else:
                # есть строка — попробуем заменить system
                if 's:6:"system";' in qset:
                    new_qset = self._SYSTEM_PAIR_RE.sub(r'\g<1>1\3', qset)
                else:
                    # ключа нет — оставим как есть (не лезем в произвольную структуру) и логируем
                    log.info("quiz_settings has no 'system' key for quiz_id=%s; leaving as-is", quiz_id)
                    new_qset = qset

            # Обновить только если реально меняем
            if new_qset != qset or (force_show_score and show_score != 1):
                conn.execute(
                    text("""
                        UPDATE wp_mlw_quizzes
                           SET quiz_settings=:qs,
                               show_score=:ss
                         WHERE quiz_id=:qid
                    """),
                    {"qs": new_qset, "ss": 1 if force_show_score else show_score, "qid": quiz_id}
                )
                log.info("Quiz %s: set system=1 in quiz_settings; show_score=%s",
                         quiz_id, 1 if force_show_score else show_score)

