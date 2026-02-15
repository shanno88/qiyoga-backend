from fastapi import FastAPI
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = "dev-secret"
    DB_URL: str = "sqlite:///./dev.db"

    class Config:
        env_file = ".env"


settings = Settings()
app = FastAPI()


@app.get("/ping")
async def ping():
    return {
        "status": "ok",
        "db": settings.DB_URL[:30],
    }
