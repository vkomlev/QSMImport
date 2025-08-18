from __future__ import annotations
from typing import List, Tuple

def split_lines(cell: str) -> List[str]:
    return [ln.strip() for ln in (cell or "").splitlines() if ln.strip()]

def parse_variant_line(line: str) -> Tuple[str, float]:
    """
    Разбирает строку варианта по разделителю '||'.
    Берем самый правый '||' на случай, если '||' встречается в тексте.
    """
    idx = line.rfind("||")
    if idx == -1:
        raise ValueError(f"Строка варианта без '||': {line}")
    left, right = line[:idx].strip(), line[idx+2:].strip()
    points = float(right.replace(",", ".")) if right else 0.0
    return left, points

def parse_variants_block(block: str) -> List[Tuple[str, float]]:
    """
    Блок вариантов — несколько строк вида `текст || баллы`.
    Возвращает список (text, points) без пустых строк.
    """
    variants: List[Tuple[str, float]] = []
    for ln in split_lines(block):
        text, pts = parse_variant_line(ln)
        variants.append((text, pts))
    return variants

def parse_correct_list(cell: str) -> List[str]:
    """
    'Правильный ответ': 'A; B; C' -> ['A','B','C'].
    """
    return [p.strip() for p in (cell or "").split(";") if p.strip()]
