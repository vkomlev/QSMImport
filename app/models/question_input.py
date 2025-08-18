from dataclasses import dataclass

@dataclass(slots=True)
class QuestionInputRow:
    """
    Представляет одну строку из листа "Задания".
    Все текстовые поля уже trim-нуты.
    """
    text: str                                 # "Текст"
    variants_and_points: str                  # "Варианты ответа и баллы"
    correct_answer: str                       # "Правильный ответ" (через ;)
    input_link: str                           # "Входные данные" (URL или пусто)
    qtype_code: str                           # "Тип задания": SC/MC/SA/TA/SA+COM
    quiz_title: str                           # "Тема - название теста"
    difficulty_ru: str                        # "Сложность"
    hint: str                                 # "Текст подсказки"
    video_url: str                            # "Видеоразбор" -> question_answer_info (может быть пусто)
