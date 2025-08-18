from app.models.enums import Difficulty

RU_TO_TERM = {
    Difficulty.THEORY.value:  "Theory",
    Difficulty.EASY.value:    "Easy",
    Difficulty.NORMAL.value:  "Normal",
    Difficulty.HARD.value:    "Hard",
    Difficulty.PROJECT.value: "Project",
}

def map_ru_to_term_name(rus: str) -> str:
    """
    'Базовая' -> 'Easy' и т.д. (именно имя терма в wp_terms.name)
    """
    return RU_TO_TERM.get(rus.strip(), "Easy")
