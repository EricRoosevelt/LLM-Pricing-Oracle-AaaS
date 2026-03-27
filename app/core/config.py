# app/core/config.py
from typing import Dict, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "LLM Pricing Oracle AaaS"
    API_V1_STR: str = "/api/v1"

    REDIS_URL: str
    DATABASE_URL: str
    PROBE_PROXY: Optional[str] = None
    AGENT_API_KEYS: Dict[str, str] = Field(default_factory=dict)

    # 国内大模型 API Keys（必须检查的配置）☆
    KIMI_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None

    # 海外大模型 API Keys（必须检查的配置）☆
    # OPENAI_API_KEY: Optional[str] = None
    # ANTHROPIC_API_KEY: Optional[str] = None
    # GEMINI_API_KEY: Optional[str] = None

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=".env",
        env_file_encoding='utf-8',
        extra='ignore'
    )

settings = Settings()
