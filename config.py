from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    ENV: str = "development"
    DEBUG: bool = True

    BACKEND_CORS_ORIGINS: str = (
        "http://localhost:5173,https://qiyoga.xyz,http://localhost:3000"
    )

    # Paddle / 支付
    PADDLE_VENDOR_ID: str = ""
    PADDLE_API_KEY: str = ""
    PADDLE_WEBHOOK_SECRET: str = ""

    # DeepSeek（老版本用这个）
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # DeepInfra（现在保留做实验用）
    DEEPINFRA_API_KEY: str = ""
    DEEPINFRA_MODEL: str = "meta-llama/Llama-3.2-3B-Instruct"

    class Config:
        env_file = ".env.local"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
