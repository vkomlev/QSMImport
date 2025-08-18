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
