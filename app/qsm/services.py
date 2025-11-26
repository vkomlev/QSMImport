#app/qsm/services.py
from __future__ import annotations
from typing import List, Dict
import logging
from app.models.enums import QuestionType
from app.models.question_input import QuestionInputRow
from app.utils import parsing, text
from app.mappers.difficulty_mapper import map_ru_to_term_name
from . import builders
from .repositories import QsmRepository
from app.config import Settings

log = logging.getLogger(__name__)

class ImportService:
    """
    Сервис: принимает строки из таблицы, пишет в БД QSM.
    """

    def __init__(self, repo: QsmRepository, default_points_short_answer: float = 10.0,
                 prepend_input_link: bool = True, input_link_label: str = "Входные данные",
                 wp_site_url: str | None = None, wp_author_id: int = 1, wp_post_status: str = "private"):
        self.repo = repo
        self.default_points_short_answer = default_points_short_answer
        self.prepend_input_link = prepend_input_link
        self.input_link_label = input_link_label
        self.wp_site_url = wp_site_url
        self.wp_author_id = wp_author_id
        self.wp_post_status = wp_post_status

    def _make_settings(self, qtype: QuestionType, title: str, placeholder: str) -> str:
        return builders.settings_for_type(qtype, title, placeholder)

    def _build_answer_array(self, qtype: QuestionType,
                            variants_block: str,
                            correct_cell: str) -> str:
        """
        Собирает answer_array:
        - SC/MC: из 'Варианты' + correct по текстам
        - SA/SA+COM: допускаемые строки из 'Правильный ответ', все по default_points_short_answer
        - TA: пусто
        """
        if qtype in (QuestionType.SC, QuestionType.MC):
            pairs = parsing.parse_variants_block(variants_block)
            correct = set(map(text.normalize, parsing.parse_correct_list(correct_cell)))
            opts: List[Dict[str, object]] = []
            for variant_text, pts in pairs:
                opts.append({"text": variant_text, "points": pts,
                             "correct": text.normalize(variant_text) in correct})
            return builders.build_answer_array_single(opts)

        if qtype in (QuestionType.SA, QuestionType.SA_COM):
            accepted = []
            for ans in parsing.parse_correct_list(correct_cell):
                accepted.append({"text": ans, "points": self.default_points_short_answer})
            return builders.build_answer_array_short(accepted)

        # TA
        return builders.build_answer_array_textarea(exemplar=None)

    def _comments_flag(self, qtype: QuestionType) -> int:
        return 2 if qtype == QuestionType.SA_COM else 0

    def _qtype_from_code(self, code: str) -> QuestionType:
        code = (code or "").strip().upper()
        return QuestionType(code)

    def import_questions_batch(self, rows: List[QuestionInputRow]) -> None:
        """
        Импортирует пачку строк:
        1) Находит quiz_id по 'Тема - название теста'
        2) Создаёт вопросы
        3) Проставляет термы: Difficulty + уровень
        4) Обновляет qpages/pages (одна страница) — все вставленные вопросы в порядке следования
        """
        # Группируем по квизу
        by_quiz: Dict[int, List[int]] = {}

        # Убедимся, что термы сложности есть
        diff_root_name = "Difficulty"
        diff_levels = {"Theory", "Easy", "Normal", "Hard", "Project"}
        terms_map = self.repo.ensure_terms([diff_root_name, *sorted(diff_levels)])

        for row in rows:
            quiz_id = self.repo.get_quiz_id_by_name(row.quiz_title)
            if not quiz_id:
                quiz_id = self.repo.get_or_create_quiz_by_name(row.quiz_title)
                log.info("Quiz '%s' был создан автоматически: quiz_id=%s", row.quiz_title, quiz_id)
            # гарантируем комбинированную систему
            # гарантируем систему оценивания, контактную форму и «результаты»
            self.repo.ensure_quiz_system_combined(quiz_id, force_show_score=True)  # system=3 + show_score=1
            self.repo.ensure_quiz_contact_flags(quiz_id)                           # location=1, name=2, email=0, phone=0
            self.repo.ensure_quiz_contact_form_block(quiz_id)                      # контактная форма как в дампе
            self.repo.ensure_quiz_message_after(quiz_id)                           # "Ваши результаты: %POINT_SCORE% из %MAXIMUM_POINTS%"

            # по вашей ремарке — если нужно ограничение вопросов, используем именно question_from_total
            # (в дампах "maximum_question_limit" нет, есть только question_from_total)
            # пример: 70
            self.repo.ensure_question_from_total(quiz_id, total=70)
            
            post_id = self.repo.ensure_quiz_post(
                quiz_id=quiz_id,
                quiz_name=row.quiz_title,
                author_id=self.wp_author_id,
                site_url=self.wp_site_url,
                status=self.wp_post_status,
            )
            # (не обязательно) ещё раз гарантируем мету:
            self.repo.upsert_postmeta(post_id, "quiz_id", str(quiz_id))
            
            qtype = self._qtype_from_code(row.qtype_code)

            # Текст вопроса (+ входные данные)
            title = row.text
            if self.prepend_input_link and row.input_link:
                title = text.add_input_link_to_title(row.text, row.input_link, self.input_link_label)

            # question_settings / answer_array / comments
            q_settings = self._make_settings(qtype, title, row.hint)
            a_array = self._build_answer_array(qtype, row.variants_and_points, row.correct_answer)
            comments = self._comments_flag(qtype)

            # Видеоразбор -> question_answer_info
            qinfo = row.video_url or ""

            # Вставка вопроса
            qid = self.repo.upsert_question(
                quiz_id=quiz_id,
                qtype_new=("0" if qtype in (QuestionType.SC, QuestionType.MC)
                           else "3" if qtype in (QuestionType.SA, QuestionType.SA_COM)
                           else "5"),
                question_settings=q_settings,
                answer_array=a_array,
                comments=comments,
                question_answer_info=qinfo,
                hints="",
                category="",
                question_name=title,
                question_order=0,
            )

            # Term: Difficulty + конкретный уровень
            level_term = map_ru_to_term_name(row.difficulty_ru)
            self.repo.upsert_question_term(qid, quiz_id, terms_map["Difficulty"])
            self.repo.upsert_question_term(qid, quiz_id, terms_map[level_term])

            by_quiz.setdefault(quiz_id, []).append(qid)

        # Перестраиваем страницы (одна страница: все новые вопросы по порядку)
        for quiz_id, qids in by_quiz.items():
            self.repo.update_quiz_pages(quiz_id, qids)