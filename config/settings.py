from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    BOT_TOKEN: str
    OPENAI_API_KEY: str = ""
    AI_PROVIDER: str = "openai"
    AI_MODEL: str = ""
    WEBAPP_URL: str = ""
    API_URL: str = ""
    ADMIN_IDS: List[int] = []
    DATABASE_URL: str = ""
    PROXY_URL: str = ""
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/mindflow.log"
    RATE_LIMIT_SECONDS: int = 2
    BROADCAST_BATCH_SIZE: int = 25
    BROADCAST_DELAY_SECONDS: float = 0.5
    PREMIUM_TRIAL_DAYS: int = 3
    PREMIUM_MONTH_STARS: int = 150
    PREMIUM_YEAR_STARS: int = 999
    USER_CACHE_TTL: int = 300
    VAPID_PRIVATE_KEY: str = ""
    VAPID_PUBLIC_KEY: str = ""
    VAPID_CLAIMS_EMAIL: str = "mailto:admin@mindflow.ai"

    @property
    def resolved_ai_model(self) -> str:
        if self.AI_MODEL:
            return self.AI_MODEL
        if self.AI_PROVIDER == "groq":
            return "llama-3.1-70b-versatile"
        if self.OPENAI_API_KEY.startswith("csk-"):
            return "accounts/fireworks/models/gpt-4o-mini"
        return "gpt-4o-mini"

    @property
    def ai_base_url(self) -> Optional[str]:
        if self.AI_PROVIDER == "groq":
            return "https://api.groq.com/openai/v1"
        if self.OPENAI_API_KEY.startswith("csk-"):
            return "https://api.fireworks.ai/inference/v1"
        return None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
