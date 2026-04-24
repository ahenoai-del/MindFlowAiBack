import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from db import TaskRepo
from services.task_service import TaskService
from services.voice_service import VoiceService
from utils.formatting import priority_emoji, priority_name
from bot.keyboards.kb import get_tasks_menu, get_task_actions, get_tasks_list_keyboard, get_back_button

router = Router()
logger = logging.getLogger(__name__)


class TaskStates(StatesGroup):
    waiting_title = State()


class TaskEditStates(StatesGroup):
    waiting_title = State()
    waiting_description = State()
    waiting_deadline = State()


@router.message(F.voice)
async def handle_voice_message(message: Message):
    if not VoiceService.is_configured():
        await message.answer("🎤 Голосовой ввод пока недоступен. Напиши задачу текстом.")
        return

    try:
        file_id = message.voice.file_id
        file = await message.bot.get_file(file_id)
        audio_data = await message.bot.download_file(file.file_path)
        audio_bytes = audio_data.read()

        text = await VoiceService.transcribe(audio_bytes, "voice.ogg")
        if not text:
            await message.answer("❌ Не удалось распознать речь. Попробуй ещё раз.")
            return

        task = await TaskService.create_from_text(message.from_user.id, text)
        if task:
            await message.answer(
                f"🎤 <b>Распознано:</b> {text}\n\n"
                f"✅ Задача создана: <b>{task.title}</b>"
            )
        else:
            await message.answer(f"🎤 <b>Распознано:</b> {text}\n\n❌ Не удалось создать задачу")
    except Exception as e:
        logger.error("Voice message handling error: %s", e)
        await message.answer("❌ Ошибка обработки голосового сообщения")


@router.message(F.text == "📋 Задачи")
async def show_tasks_menu(message: Message):
    await message.answer("📋 Управление задачами", reply_markup=get_tasks_menu())


@router.message(F.text == "➕ Новая задача")
async def new_task_prompt(message: Message, state: FSMContext):
    await message.answer(
        "📝 Напиши задачу в свободной форме:\n\n"
        "Примеры:\n"
        "• <b>завтра встреча в 15:00</b> — поставит дедлайн\n"
        "• <b>срочно позвонить клиенту</b> — высокий приоритет\n"
        "• <b>купить продукты</b> — создаст сразу\n\n"
        "Или нажми /cancel для отмены",
        reply_markup=get_back_button(),
    )
    await state.set_state(TaskStates.waiting_title)


@router.message(TaskStates.waiting_title)
async def process_task_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if title.lower() in ("отмена", "cancel", "/cancel"):
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=get_tasks_menu())
        return

    task = await TaskService.create_from_text(message.from_user.id, title)
    if not task:
        await message.answer("❌ Не удалось создать задачу. Попробуй ещё раз.")
        await state.clear()
        return

    text = f"✅ Задача создана: <b>{task.title}</b>\n"
    if task.deadline:
        text += f"📅 Дедлайн: {task.deadline}\n"

    await state.clear()
    await message.answer(text, reply_markup=get_tasks_menu())


@router.callback_query(F.data == "task_list")
async def show_task_list(callback: CallbackQuery):
    tasks = await TaskRepo.get_user_tasks(callback.from_user.id)
    if not tasks:
        try:
            await callback.message.edit_text(
                "📭 У тебя пока нет задач. Добавь первую!",
                reply_markup=get_tasks_menu(),
            )
        except Exception:
            pass
        return

    text = "📋 <b>Твои задачи:</b>\n\n"
    for task in tasks:
        p = priority_emoji(task.priority)
        deadline = f" 📅 {task.deadline}" if task.deadline else ""
        text += f"{p} <b>{task.title}</b>{deadline}\n"
        text += f"   📁 {task.category} | ID: {task.id}\n"

    try:
        await callback.message.edit_text(text, reply_markup=get_tasks_list_keyboard(tasks))
    except Exception:
        await callback.answer("Список не изменился")


@router.callback_query(F.data.startswith("task_view_"))
async def view_task(callback: CallbackQuery):
    try:
        task_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("Неверный ID задачи")
        return

    task = await TaskRepo.get(task_id)
    if not task or task.user_id != callback.from_user.id:
        await callback.answer("Задача не найдена")
        return

    text = (
        f"📋 <b>{task.title}</b>\n\n"
        f"📝 Описание: {task.description or 'не указано'}\n"
        f"📁 Категория: {task.category}\n"
        f"⚡ Приоритет: {priority_name(task.priority)}\n"
        f"📅 Дедлайн: {task.deadline or 'не указан'}\n"
        f"⏱ Оценка: {f'{task.estimated_minutes} мин' if task.estimated_minutes else 'не указана'}"
    )
    await callback.message.edit_text(text, reply_markup=get_task_actions(task_id))


@router.callback_query(F.data == "task_add")
async def add_task_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✍️ Напиши задачу в свободной форме.\n\n"
        "AI автоматически определит дату и приоритет.\n\n"
        "Или /cancel для отмены.",
        reply_markup=get_back_button(),
    )
    await state.set_state(TaskStates.waiting_title)


@router.callback_query(F.data.startswith("task_done_"))
async def complete_task(callback: CallbackQuery):
    try:
        task_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("Неверный ID")
        return

    result = await TaskService.complete_task(callback.from_user.id, task_id)
    if not result:
        await callback.answer("Задача не найдена")
        return

    msg = f"✅ Задача выполнена!\n💰 +{result['xp_earned']} XP"
    if result["leveled_up"]:
        msg += f"\n\n🎉 УРОВЕНЬ {result['new_level']}!"
    if result["streak"] > 1:
        msg += f"\n🔥 Серия: {result['streak']} дней"

    await callback.answer(msg, show_alert=True)
    try:
        await callback.message.delete()
    except Exception:
        pass


@router.callback_query(F.data.startswith("task_del_"))
async def delete_task(callback: CallbackQuery):
    try:
        task_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("Неверный ID")
        return
    deleted = await TaskRepo.delete_for_user(task_id, callback.from_user.id)
    if not deleted:
        await callback.answer("Задача не найдена")
        return
    await callback.answer("🗑 Задача удалена")
    try:
        await callback.message.delete()
    except Exception:
        pass


@router.callback_query(F.data == "task_completed")
async def show_completed_tasks(callback: CallbackQuery):
    tasks = await TaskRepo.get_user_tasks(callback.from_user.id, include_completed=True)
    tasks = [t for t in tasks if t.status == "completed"]
    if not tasks:
        await callback.answer("Нет выполненных задач")
        return

    text = "✅ <b>Выполненные задачи:</b>\n\n"
    for task in tasks[-10:]:
        text += f"✓ {task.title}\n"
    await callback.message.edit_text(text, reply_markup=get_back_button())


@router.callback_query(F.data.startswith("task_edit_"))
async def edit_task_start(callback: CallbackQuery, state: FSMContext):
    try:
        task_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("Неверный ID")
        return

    task = await TaskRepo.get(task_id)
    if not task or task.user_id != callback.from_user.id:
        await callback.answer("Задача не найдена")
        return

    await state.update_data(task_id=task_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Название", callback_data=f"edit_field_title_{task_id}")],
        [InlineKeyboardButton(text="📋 Описание", callback_data=f"edit_field_desc_{task_id}")],
        [InlineKeyboardButton(text="📅 Дедлайн", callback_data=f"edit_field_deadline_{task_id}")],
        [InlineKeyboardButton(text="⚡ Приоритет", callback_data=f"edit_field_priority_{task_id}")],
        [InlineKeyboardButton(text="📁 Категория", callback_data=f"edit_field_category_{task_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"task_view_{task_id}")],
    ])
    try:
        await callback.message.edit_text(
            f"✏️ <b>Редактирование задачи</b>\n\n📋 {task.title}\n\nВыберите что изменить:",
            reply_markup=keyboard,
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("edit_field_title_"))
async def edit_field_title(callback: CallbackQuery, state: FSMContext):
    try:
        task_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка")
        return
    await state.update_data(task_id=task_id, field="title")
    await state.set_state(TaskEditStates.waiting_title)
    task = await TaskRepo.get(task_id)
    if not task or task.user_id != callback.from_user.id:
        await callback.answer("Задача не найдена")
        return
    await callback.message.edit_text(
        f"📝 <b>Изменение названия</b>\n\nТекущее: {task.title}\n\nНапиши новое название:",
        reply_markup=get_back_button(),
    )


@router.callback_query(F.data.startswith("edit_field_desc_"))
async def edit_field_desc(callback: CallbackQuery, state: FSMContext):
    try:
        task_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка")
        return
    await state.update_data(task_id=task_id, field="description")
    await state.set_state(TaskEditStates.waiting_description)
    task = await TaskRepo.get(task_id)
    if not task or task.user_id != callback.from_user.id:
        await callback.answer("Задача не найдена")
        return
    await callback.message.edit_text(
        f"📋 <b>Изменение описания</b>\n\nТекущее: {task.description or 'не указано'}\n\n"
        "Напиши новое описание или /clear чтобы очистить:",
        reply_markup=get_back_button(),
    )


@router.callback_query(F.data.startswith("edit_field_deadline_"))
async def edit_field_deadline(callback: CallbackQuery, state: FSMContext):
    try:
        task_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка")
        return
    await state.update_data(task_id=task_id, field="deadline")
    await state.set_state(TaskEditStates.waiting_deadline)
    task = await TaskRepo.get(task_id)
    if not task or task.user_id != callback.from_user.id:
        await callback.answer("Задача не найдена")
        return
    await callback.message.edit_text(
        f"📅 <b>Изменение дедлайна</b>\n\nТекущий: {task.deadline or 'не указан'}\n\n"
        "Напиши дату в формате ГГГГ-ММ-ДД или /clear чтобы убрать:",
        reply_markup=get_back_button(),
    )


@router.callback_query(F.data.startswith("edit_field_priority_"))
async def edit_field_priority(callback: CallbackQuery, state: FSMContext):
    try:
        task_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка")
        return
    task = await TaskRepo.get(task_id)
    if not task or task.user_id != callback.from_user.id:
        await callback.answer("Задача не найдена")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Высокий", callback_data=f"set_priority_1_{task_id}")],
        [InlineKeyboardButton(text="🟡 Средний", callback_data=f"set_priority_2_{task_id}")],
        [InlineKeyboardButton(text="🟢 Низкий", callback_data=f"set_priority_3_{task_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"task_edit_{task_id}")],
    ])
    await callback.message.edit_text(
        f"⚡ <b>Изменение приоритета</b>\n\nТекущий: {priority_name(task.priority)}\n\nВыберите новый приоритет:",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("set_priority_"))
async def set_priority(callback: CallbackQuery):
    parts = callback.data.split("_")
    try:
        priority = int(parts[2])
        task_id = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer("Ошибка")
        return
    task = await TaskRepo.get(task_id)
    if not task or task.user_id != callback.from_user.id:
        await callback.answer("Задача не найдена")
        return
    await TaskRepo.update(task_id, priority=priority)
    await callback.answer("✅ Приоритет изменен")
    await _show_task_inline(callback, task_id)


@router.callback_query(F.data.startswith("edit_field_category_"))
async def edit_field_category(callback: CallbackQuery, state: FSMContext):
    try:
        task_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка")
        return
    task = await TaskRepo.get(task_id)
    if not task or task.user_id != callback.from_user.id:
        await callback.answer("Задача не найдена")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💼 Работа", callback_data=f"set_category_work_{task_id}")],
        [InlineKeyboardButton(text="🏠 Дом", callback_data=f"set_category_home_{task_id}")],
        [InlineKeyboardButton(text="📚 Учёба", callback_data=f"set_category_study_{task_id}")],
        [InlineKeyboardButton(text="💪 Спорт", callback_data=f"set_category_sport_{task_id}")],
        [InlineKeyboardButton(text="🎯 Прочее", callback_data=f"set_category_other_{task_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"task_edit_{task_id}")],
    ])
    await callback.message.edit_text(
        f"📁 <b>Изменение категории</b>\n\nТекущая: {task.category}\n\nВыберите новую категорию:",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("set_category_"))
async def set_category(callback: CallbackQuery):
    parts = callback.data.split("_")
    try:
        category = parts[2]
        task_id = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer("Ошибка")
        return
    task = await TaskRepo.get(task_id)
    if not task or task.user_id != callback.from_user.id:
        await callback.answer("Задача не найдена")
        return
    await TaskRepo.update(task_id, category=category)
    await callback.answer("✅ Категория изменена")
    await _show_task_inline(callback, task_id)


@router.message(TaskEditStates.waiting_title)
async def process_edit_title(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data.get("task_id")
    if not task_id:
        await state.clear()
        return
    task = await TaskRepo.get(task_id)
    if not task or task.user_id != message.from_user.id:
        await state.clear()
        await message.answer("❌ Задача не найдена")
        return
    await TaskRepo.update(task_id, title=message.text)
    await state.clear()
    await message.answer(f"✅ Название изменено на: {message.text}")
    await _show_task_by_id(message, task_id)


@router.message(TaskEditStates.waiting_description)
async def process_edit_desc(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data.get("task_id")
    if not task_id:
        await state.clear()
        return
    task = await TaskRepo.get(task_id)
    if not task or task.user_id != message.from_user.id:
        await state.clear()
        await message.answer("❌ Задача не найдена")
        return
    new_desc = None if message.text == "/clear" else message.text
    await TaskRepo.update(task_id, description=new_desc)
    await state.clear()
    await message.answer("✅ Описание изменено")
    await _show_task_by_id(message, task_id)


@router.message(TaskEditStates.waiting_deadline)
async def process_edit_deadline(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data.get("task_id")
    if not task_id:
        await state.clear()
        return
    task = await TaskRepo.get(task_id)
    if not task or task.user_id != message.from_user.id:
        await state.clear()
        await message.answer("❌ Задача не найдена")
        return
    new_deadline = None if message.text == "/clear" else message.text
    await TaskRepo.update(task_id, deadline=new_deadline)
    await state.clear()
    await message.answer(f"✅ Дедлайн изменен на: {new_deadline or 'не указан'}")
    await _show_task_by_id(message, task_id)


async def _show_task_inline(callback: CallbackQuery, task_id: int):
    task = await TaskRepo.get(task_id)
    if not task:
        await callback.answer("Задача не найдена")
        return
    text = (
        f"📋 <b>{task.title}</b>\n\n"
        f"📝 Описание: {task.description or 'не указано'}\n"
        f"📁 Категория: {task.category}\n"
        f"⚡ Приоритет: {priority_name(task.priority)}\n"
        f"📅 Дедлайн: {task.deadline or 'не указан'}"
    )
    try:
        await callback.message.edit_text(text, reply_markup=get_task_actions(task_id))
    except Exception:
        pass


async def _show_task_by_id(message: Message, task_id: int):
    task = await TaskRepo.get(task_id)
    if not task:
        return
    text = (
        f"📋 <b>{task.title}</b>\n\n"
        f"📝 Описание: {task.description or 'не указано'}\n"
        f"📁 Категория: {task.category}\n"
        f"⚡ Приоритет: {priority_name(task.priority)}\n"
        f"📅 Дедлайн: {task.deadline or 'не указан'}"
    )
    await message.answer(text, reply_markup=get_task_actions(task_id))
