import logging
from typing import List
from datetime import datetime

from openai import AsyncOpenAI

from config.settings import settings
from db.models import Task

logger = logging.getLogger(__name__)


def _get_ai_client() -> tuple:
    base_url = settings.ai_base_url
    model = settings.resolved_ai_model
    if base_url:
        return AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=base_url), model
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY), model


async def generate_day_plan(tasks: List[Task], timezone: str = "UTC") -> str:
    if not settings.OPENAI_API_KEY:
        return _generate_local_plan(tasks)

    try:
        client, model = _get_ai_client()
        tasks_text = "\n".join([
            f"- {t.title} (приоритет: {t.priority}, категория: {t.category}, "
            f"дедлайн: {t.deadline or 'нет'})"
            for t in tasks
        ])
        today = datetime.now().strftime("%A, %d %B")

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Ты помощник по планированию. Создай оптимальное расписание на сегодня ({today}).\n\n"
                        "Правила:\n"
                        "1. Начни с утра, заверши вечером\n"
                        "2. Сначала важные задачи (приоритет 1)\n"
                        "3. Чередуй разные категории для баланса\n"
                        "4. Оставь время на перерывы\n"
                        "5. Формат: ⏰ Время | Задача (категория)\n\n"
                        "Не добавляй ничего лишнего, только расписание."
                    ),
                },
                {"role": "user", "content": f"Мои задачи:\n{tasks_text}\n\nСоставь план на день."},
            ],
            temperature=0.7,
            max_tokens=1000,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning("AI plan generation error: %s", e)
        return _generate_local_plan(tasks)


def _generate_local_plan(tasks: List[Task]) -> str:
    if not tasks:
        return "Нет задач на сегодня. Добавь задачи, чтобы я составил план!"

    sorted_tasks = sorted(tasks, key=lambda t: (t.priority, t.deadline or "zzz"))
    plan_lines: list[str] = []
    current_hour = 9

    for i, task in enumerate(sorted_tasks[:8]):
        time = f"{current_hour:02d}:00"
        emoji = _get_category_emoji(task.category)
        plan_lines.append(f"⏰ {time} | {emoji} {task.title}")
        if (i + 1) % 3 == 0:
            current_hour += 1
            plan_lines.append(f"☕ {current_hour:02d}:00 | Перерыв 15 минут")
        current_hour += 1

    plan_lines.append(f"\n🌙 {current_hour:02d}:00 | Подведение итогов")
    return "\n".join(plan_lines)


def _get_category_emoji(category: str) -> str:
    return {
        "work": "💼", "home": "🏠", "study": "📚",
        "sport": "💪", "general": "🎯",
    }.get(category, "📌")


async def generate_evening_summary(tasks: List[Task]) -> str:
    completed = [t for t in tasks if t.status == "completed"]
    pending = [t for t in tasks if t.status != "completed"]

    summary = f"🌙 <b>Итоги дня</b>\n\n"
    summary += f"✅ Выполнено: {len(completed)} задач\n"
    summary += f"⏳ Осталось: {len(pending)} задач\n\n"

    if completed:
        summary += "<b>Завершено:</b>\n"
        for t in completed[:5]:
            summary += f"✓ {t.title}\n"
    if pending:
        summary += "\n<b>На завтра:</b>\n"
        for t in pending[:3]:
            summary += f"○ {t.title}\n"

    return summary
