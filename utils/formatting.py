from datetime import datetime, date
from typing import Optional


def format_date(dt_str: Optional[str]) -> str:
    if not dt_str:
        return "не указана"
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return str(dt_str)


def format_premium_until(until_str: Optional[str]) -> str:
    if not until_str:
        return "не активен"
    try:
        until_date = datetime.strptime(until_str, "%Y-%m-%d").date()
        if until_date < date.today():
            return "истёк"
        return until_date.strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return str(until_str)


def priority_emoji(priority: int) -> str:
    return {1: "🔴", 2: "🟡", 3: "🟢"}.get(priority, "⚪")


def priority_name(priority: int) -> str:
    return {1: "Высокий", 2: "Средний", 3: "Низкий"}.get(priority, "Средний")


def category_emoji(category: str) -> str:
    return {
        "work": "💼",
        "home": "🏠",
        "study": "📚",
        "sport": "💪",
        "general": "🎯",
        "other": "📌",
    }.get(category, "📌")
