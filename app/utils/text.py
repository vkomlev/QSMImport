import re
import unicodedata

def normalize(s: str) -> str:
    """
    Нормализация текста для сравнения 'вариант ∈ правильные':
    - трим
    - приводим к нижнему регистру
    - схлопываем пробелы
    """
    s = (s or "").strip().lower()
    s = " ".join(s.split())
    return s

def add_input_link_to_title(title: str, link: str, label: str) -> str:
    if not link:
        return title
    return f"[{label}: {link}]\n\n{title}".strip()

def slugify(value: str, allow_unicode: bool = False) -> str:
    """
    Преобразует строку в slug для использования в post_name (WP).
    
    Args:
        value (str): Исходная строка (например, имя квиза).
        allow_unicode (bool): Если True, оставляет символы юникода (например, кириллицу).
                              Если False — выполняет транслитерацию в ASCII.

    Returns:
        str: Корректный slug (латиница, цифры и дефисы).
    
    Пример:
        >>> slugify("Тестовый Квиз №1")
        'testovyi-kviz-1'
    """
    value = str(value)

    if allow_unicode:
        # NFKC — компатибельная нормализация
        value = unicodedata.normalize("NFKC", value)
    else:
        # NFKD — декомпозируем и отбрасываем все не-ASCII
        value = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
        )

    # заменяем всё кроме латиницы/цифр/дефиса/подчёркивания на дефисы
    value = re.sub(r"[^\w\s-]", "", value.lower())
    # пробелы и подчёркивания → дефисы
    value = re.sub(r"[\s_-]+", "-", value)
    # убираем крайние дефисы
    value = value.strip("-")
    return value