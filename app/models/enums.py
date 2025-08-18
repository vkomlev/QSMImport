from enum import Enum


class QuestionType(str, Enum):
    SC = "SC"        # single choice
    MC = "MC"        # multi choice
    SA = "SA"        # short answer (однострочный ввод)
    TA = "TA"        # textarea (многострочный ввод)
    SA_COM = "SA+COM"  # короткий ввод + обяз. комментарий


class Difficulty(str, Enum):
    THEORY = "Теория"
    EASY = "Базовая"
    NORMAL = "Нормальная"
    HARD = "Сложная"
    PROJECT = "Проектная"
