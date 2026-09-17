from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class Settings(BaseSettings):
    database_url: str = "postgresql://leiloes:leiloes@localhost:5432/leiloes"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
