from .start import router as start_router
from .tasks import router as tasks_router
from .planning import router as planning_router
from .webapp_handler import router as webapp_router
from .admin import router as admin_router
from .payments import router as payments_router
from .reminders import router as reminders_router

__all__ = [
    "start_router", "tasks_router", "planning_router",
    "webapp_router", "admin_router", "payments_router", "reminders_router",
]
