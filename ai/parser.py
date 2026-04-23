import json
import re
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from openai import AsyncOpenAI

from config.settings import settings

logger = logging.getLogger(__name__)


def _get_ai_client() -> tuple[Optional[AsyncOpenAI], str]:
    if not settings.OPENAI_API_KEY:
        return None, ""
    base_url = settings.ai_base_url
    model = settings.resolved_ai_model
    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=base_url,
    ) if base_url else AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return client, model


async def correct_text(text: str) -> str:
    if not settings.OPENAI_API_KEY:
        return _correct_local(text)

    try:
        client, model = _get_ai_client()
        if not client:
            return _correct_local(text)

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты корректор текста. Твоя задача - исправить текст задачи:\n"
                        "1. Исправь опечатки и грамматические ошибки\n"
                        "2. Расшифруй сокращения (завт -> завтра, идт -> идти, ворк -> работа и т.д.)\n"
                        "3. Сделай текст читаемым и понятным\n"
                        "4. Сохрани смысл оригинала\n"
                        "5. Не добавляй ничего лишнего\n\n"
                        "Ответь ТОЛЬКО исправленным текстом без объяснений."
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0.2,
            max_tokens=100,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("AI correction error: %s", e)
        return _correct_local(text)


_CORRECTIONS = {
    "завт": "завтра", "завтр": "завтра", "идт": "идти", "ворк": "работа",
    "сег": "сегодня", "сегдн": "сегодня", "сегдня": "сегодня",
    "потм": "потом", "птм": "потом", "щас": "сейчас", "сйчас": "сейчас",
    "над": "надо", "нд": "надо", "делть": "делать", "сдлть": "сделать",
    "купит": "купить", "звн": "звонок", "звон": "звонок",
    "встр": "встреча", "встрч": "встреча", "отчт": "отчёт",
    "прочт": "прочитать", "док": "документ", "докум": "документ",
    "реп": "репетиция", "трен": "тренировка", "учб": "учёба",
    "учеб": "учёба", "домш": "домашнее", "домшк": "домашка",
    "рабт": "работа", "прв": "проверить", "провер": "проверить",
    "нпс": "написать", "напс": "написать", "звнк": "звонок",
    "позв": "позвонить", "отпр": "отправить", "получ": "получить",
    "законч": "закончить", "закон": "закончить", "начть": "начать",
    "начн": "начать", "продл": "продолжить", "подгот": "подготовить",
    "выполн": "выполнить", "сост": "составить", "заполн": "заполнить",
    "посм": "посмотреть", "посмотр": "посмотреть", "сход": "сходить",
    "пойт": "пойти", "прийт": "прийти", "уйт": "уйти",
    "верн": "вернуться", "поех": "поехать", "приех": "приехать",
    "встрт": "встретить", "обзв": "обзвонить", "напомн": "напомнить",
    "испр": "исправить", "обсуд": "обсудить", "решт": "решить",
    "отлож": "отложить", "перенс": "перенести", "отмн": "отменить",
    "подтв": "подтвердить", "согл": "согласовать", "утв": "утвердить",
    "созд": "создать", "удл": "удалить", "измн": "изменить",
    "обнов": "обновить", "сохр": "сохранить", "найт": "найти",
    "куп": "купить", "прод": "продать", "закз": "заказать",
    "прин": "принять", "забр": "забрать", "посл": "послать",
}


def _correct_local(text: str) -> str:
    corrected = text
    for wrong, right in _CORRECTIONS.items():
        pattern = r"\b" + re.escape(wrong) + r"\b"
        corrected = re.sub(pattern, right, corrected, flags=re.IGNORECASE)
    if corrected != text:
        corrected = corrected[0].upper() + corrected[1:]
    return corrected


async def parse_task_text(text: str) -> Dict[str, Any]:
    corrected_text = await correct_text(text)

    if not settings.OPENAI_API_KEY:
        result = _parse_local(corrected_text)
        result["original_text"] = text
        result["corrected_text"] = corrected_text
        return result

    try:
        client, model = _get_ai_client()
        if not client:
            result = _parse_local(corrected_text)
            result["original_text"] = text
            result["corrected_text"] = corrected_text
            return result

        today = datetime.now().strftime("%Y-%m-%d")
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Ты помощник для парсинга задач. Извлеки из текста:\n"
                        f"- title: название задачи (кратко, исправленное)\n"
                        f"- description: описание (если есть детали)\n"
                        f"- deadline: дата дедлайна в формате YYYY-MM-DD (если указана, сегодня: {today})\n"
                        f"- priority: 1-3 (1=высокий, 2=средний, 3=низкий)\n"
                        f"- category: work/home/study/sport/other\n"
                        f"- estimated_minutes: примерное время в минутах (если указано)\n\n"
                        f"Ответь ТОЛЬКО JSON без markdown."
                    ),
                },
                {"role": "user", "content": corrected_text},
            ],
            temperature=0.3,
            max_tokens=200,
        )
        content = response.choices[0].message.content
        result = json.loads(content)
        result["original_text"] = text
        result["corrected_text"] = corrected_text
        return result
    except Exception as e:
        logger.warning("AI parse error: %s", e)
        result = _parse_local(corrected_text)
        result["original_text"] = text
        result["corrected_text"] = corrected_text
        return result


def _parse_local(text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "title": text[:100],
        "priority": 2,
        "category": "general",
    }
    text_lower = text.lower()

    if any(w in text_lower for w in ["срочно", "важно", "немедленно", "urgent", "important"]):
        result["priority"] = 1
    elif any(w in text_lower for w in ["позже", "когда-нибудь", "later", "someday"]):
        result["priority"] = 3

    if any(w in text_lower for w in ["работ", "meet", "клиент", "проект", "work"]):
        result["category"] = "work"
    elif any(w in text_lower for w in ["дом", "квартир", "home", "уборк"]):
        result["category"] = "home"
    elif any(w in text_lower for w in ["учеб", "курс", "learn", "study", "экзамен"]):
        result["category"] = "study"
    elif any(w in text_lower for w in ["спорт", "тренаж", "gym", "fitness", "бег"]):
        result["category"] = "sport"

    if "завтра" in text_lower:
        result["deadline"] = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    elif "сегодня" in text_lower or "вечер" in text_lower or "утро" in text_lower:
        result["deadline"] = datetime.now().strftime("%Y-%m-%d")

    return result
