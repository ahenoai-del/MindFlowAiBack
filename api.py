import hmac
import hashlib
import json
import logging
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from db import UserRepo, TaskRepo, GamificationRepo, StatsRepo, init_db, close_db
from config.settings import settings
from services.push_service import PushService
from services.reminder_service import ReminderService
from services.voice_service import VoiceService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        yield
    finally:
        await close_db()


app = FastAPI(title="MindFlow API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_telegram_webapp(init_data: str) -> Optional[dict]:
    try:
        params = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
        hash_value = params.pop("hash", None)
        if not hash_value:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        secret_key = hmac.new(
            b"WebAppData",
            settings.BOT_TOKEN.encode(),
            hashlib.sha256,
        ).digest()
        computed_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(computed_hash, hash_value):
            user_data = params.get("user")
            if user_data:
                return json.loads(user_data)
        return None
    except Exception as e:
        logger.warning("WebApp verification failed: %s", e)
        return None


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: Optional[str] = None
    category: str = "general"
    priority: int = Field(default=2, ge=1, le=3)
    deadline: Optional[str] = None
    estimated_minutes: Optional[int] = Field(default=None, ge=1)


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=1, le=3)
    deadline: Optional[str] = None
    status: Optional[str] = None


class ReminderCreate(BaseModel):
    remind_at: str
    task_id: Optional[int] = None
    text: Optional[str] = None
    repeat_interval: Optional[str] = None


class ReminderSnooze(BaseModel):
    minutes: int = Field(default=10, ge=1, le=1440)


class PushSubscriptionCreate(BaseModel):
    subscription: str


@app.get("/api/user/{user_id}")
async def get_user(user_id: int):
    user, _ = await UserRepo.create(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    g = await GamificationRepo.get_or_create(user_id)
    return {
        "id": user.id,
        "username": user.username,
        "timezone": user.timezone,
        "morning_time": user.morning_time,
        "evening_time": user.evening_time,
        "is_premium": user.is_premium_active,
        "premium_until": user.premium_until,
        "xp": g.xp,
        "level": g.level,
        "streak": g.streak,
        "total_completed": g.total_completed,
        "achievements": await GamificationRepo.get_achievements(user_id),
    }


@app.get("/api/user/{user_id}/premium")
async def check_premium(user_id: int):
    user = await UserRepo.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"is_premium": user.is_premium_active, "premium_until": user.premium_until}


@app.get("/api/vapid-public-key")
async def get_vapid_public_key():
    if not PushService.is_configured():
        raise HTTPException(status_code=404, detail="Push not configured")
    return {"publicKey": settings.VAPID_PUBLIC_KEY}


@app.post("/api/push/{user_id}/subscribe")
async def push_subscribe(user_id: int, sub: PushSubscriptionCreate):
    await UserRepo.create(user_id)
    ok = await PushService.register_subscription(user_id, sub.subscription)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid subscription")
    return {"status": "subscribed"}


@app.delete("/api/push/{user_id}/subscribe")
async def push_unsubscribe(user_id: int):
    await PushService.unregister_subscription(user_id)
    return {"status": "unsubscribed"}


@app.get("/api/tasks/{user_id}")
async def get_tasks(user_id: int, include_completed: bool = False):
    tasks = await TaskRepo.get_user_tasks(user_id, include_completed=include_completed)
    return [
        {
            "id": t.id, "title": t.title, "description": t.description,
            "category": t.category, "priority": t.priority, "deadline": t.deadline,
            "estimated_minutes": t.estimated_minutes, "status": t.status,
            "created_at": t.created_at, "completed_at": t.completed_at,
        }
        for t in tasks
    ]


@app.post("/api/tasks/{user_id}")
async def create_task(user_id: int, task: TaskCreate):
    await UserRepo.create(user_id)
    new_task = await TaskRepo.create(
        user_id=user_id, title=task.title, description=task.description,
        category=task.category, priority=task.priority,
        deadline=task.deadline, estimated_minutes=task.estimated_minutes,
    )
    if not new_task:
        raise HTTPException(status_code=500, detail="Failed to create task")
    return {"id": new_task.id, "title": new_task.title, "status": "created"}


@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: int, task: TaskUpdate, user_id: int = Query(...)):
    existing = await TaskRepo.get(task_id)
    if not existing or existing.user_id != user_id:
        raise HTTPException(status_code=404, detail="Task not found")
    raw_updates = task.model_dump(exclude_unset=True)
    updates = {}
    for key, value in raw_updates.items():
        if key in {"description", "deadline"}:
            updates[key] = value
        elif value is not None:
            updates[key] = value
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    updated = await TaskRepo.update(task_id, **updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"id": updated.id, "status": "updated"}


@app.post("/api/tasks/{task_id}/complete")
async def complete_task(task_id: int, user_id: int = Query(...)):
    existing = await TaskRepo.get(task_id)
    if not existing or existing.user_id != user_id:
        raise HTTPException(status_code=404, detail="Task not found")
    task = await TaskRepo.complete(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"id": task.id, "status": "completed"}


@app.post("/api/tasks/{task_id}/uncomplete")
async def uncomplete_task(task_id: int, user_id: int = Query(...)):
    existing = await TaskRepo.get(task_id)
    if not existing or existing.user_id != user_id:
        raise HTTPException(status_code=404, detail="Task not found")
    task = await TaskRepo.uncomplete(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"id": task.id, "status": "pending"}


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: int, user_id: int = Query(...)):
    deleted = await TaskRepo.delete_for_user(task_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "deleted"}


@app.get("/api/reminders/{user_id}")
async def get_reminders(user_id: int):
    reminders = await ReminderService.get_user_reminders(user_id)
    return [
        {
            "id": r.id, "task_id": r.task_id, "text": r.text,
            "remind_at": r.remind_at, "status": r.status,
            "repeat_interval": r.repeat_interval, "created_at": r.created_at,
        }
        for r in reminders
    ]


@app.post("/api/reminders/{user_id}")
async def create_reminder(user_id: int, reminder: ReminderCreate):
    new_reminder = await ReminderService.create(
        user_id=user_id, remind_at=reminder.remind_at,
        task_id=reminder.task_id, text=reminder.text,
        repeat_interval=reminder.repeat_interval,
    )
    if not new_reminder:
        raise HTTPException(status_code=500, detail="Failed to create reminder")
    return {
        "id": new_reminder.id, "remind_at": new_reminder.remind_at,
        "status": "created",
    }


@app.delete("/api/reminders/{reminder_id}")
async def delete_reminder(reminder_id: int, user_id: int = Query(...)):
    ok = await ReminderService.delete(reminder_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"status": "deleted"}


@app.post("/api/reminders/{reminder_id}/snooze")
async def snooze_reminder(reminder_id: int, body: ReminderSnooze, user_id: int = Query(...)):
    ok = await ReminderService.snooze(reminder_id, user_id, body.minutes)
    if not ok:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"status": "snoozed", "minutes": body.minutes}


@app.post("/api/voice/{user_id}")
async def transcribe_voice(user_id: int, file: UploadFile = File(...)):
    if not VoiceService.is_configured():
        raise HTTPException(status_code=501, detail="Voice transcription not configured")
    audio_data = await file.read()
    if len(audio_data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 25MB)")
    text = await VoiceService.transcribe(audio_data, filename=file.filename or "voice.ogg")
    if not text:
        raise HTTPException(status_code=422, detail="Could not transcribe audio")
    return {"text": text}


@app.get("/api/stats/{user_id}")
async def get_stats(user_id: int):
    stats = await StatsRepo.get_week_stats(user_id)
    return [
        {"date": s.date, "tasks_completed": s.tasks_completed, "tasks_total": s.tasks_total, "focus_score": s.focus_score}
        for s in stats
    ]


@app.get("/api/verify")
async def verify_user(init_data: str = Query(...)):
    user_data = verify_telegram_webapp(init_data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid Telegram data")
    user_id = user_data.get("id")
    if user_id:
        await UserRepo.create(user_id, user_data.get("username"))
    return {"user_id": user_id, "user": user_data}


@app.get("/webapp")
async def webapp_index():
    return FileResponse("webapp/index.html", media_type="text/html")


@app.get("/sw.js")
async def service_worker():
    return FileResponse(
        "webapp/sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )
