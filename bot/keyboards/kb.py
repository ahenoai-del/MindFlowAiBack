from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def get_main_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 Задачи")
    builder.button(text="➕ Новая задача")
    builder.button(text="📊 План на сегодня")
    builder.button(text="📱 Приложение")
    builder.button(text="⚙️ Настройки")
    builder.button(text="📈 Статистика")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def get_tasks_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить задачу", callback_data="task_add")
    builder.button(text="📝 Список задач", callback_data="task_list")
    builder.button(text="✅ Выполненные", callback_data="task_completed")
    builder.button(text="🔙 Назад", callback_data="back_main")
    builder.adjust(2)
    return builder.as_markup()


def get_task_actions(task_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Выполнить", callback_data=f"task_done_{task_id}")
    builder.button(text="✏️ Изменить", callback_data=f"task_edit_{task_id}")
    builder.button(text="🗑 Удалить", callback_data=f"task_del_{task_id}")
    builder.button(text="🔙 К списку", callback_data="task_list")
    builder.adjust(2)
    return builder.as_markup()


def get_tasks_list_keyboard(tasks) -> InlineKeyboardMarkup:
    buttons = []
    for task in tasks[:10]:
        status = "✅ " if task.status == "completed" else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"{status}{task.title[:30]}",
                callback_data=f"task_view_{task.id}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_plan_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Сгенерировать план", callback_data="plan_generate")
    builder.button(text="📅 Изменить расписание", callback_data="plan_schedule")
    builder.button(text="🔙 Назад", callback_data="back_main")
    builder.adjust(1)
    return builder.as_markup()


def get_settings_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🌍 Часовой пояс", callback_data="settings_timezone")
    builder.button(text="🌅 Утреннее время", callback_data="settings_morning")
    builder.button(text="🌙 Вечернее время", callback_data="settings_evening")
    builder.button(text="🔙 Назад", callback_data="back_main")
    builder.adjust(2)
    return builder.as_markup()


def get_back_button(callback_data: str = "back_main") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data=callback_data)
    return builder.as_markup()


def get_webapp_button(webapp_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📱 Открыть приложение", web_app=WebAppInfo(url=webapp_url))
    return builder.as_markup()


def get_premium_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 150 звёзд — Месяц", callback_data="buy_month")],
        [InlineKeyboardButton(text="⭐ 999 звёзд — Год (44% скидка)", callback_data="buy_year")],
    ])


def get_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"),
        ],
        [
            InlineKeyboardButton(text="📈 Аналитика", callback_data="admin_analytics"),
            InlineKeyboardButton(text="💎 Premium", callback_data="admin_premium"),
        ],
        [
            InlineKeyboardButton(text="🏆 Топ", callback_data="admin_top"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings"),
        ],
    ])
