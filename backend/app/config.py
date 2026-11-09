import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv
from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_ENV_FILE)

# Shell pode herdar APIFY_TOKEN="" — load_dotenv(override=False) não preenche.
for _key, _val in (dotenv_values(_ENV_FILE) or {}).items():
    if _key and _val and str(_val).strip() and not (os.getenv(_key) or "").strip():
        os.environ[_key] = str(_val).strip()


class Settings(BaseSettings):
    database_url: str = "postgresql://leiloes:leiloes@localhost:5432/leiloes"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
