from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_SCOPES = ["routing:decide", "routing:outcome", "control:read"]


class BootstrapAgentCredential(BaseModel):
    api_key: str
    agent_id: str
    environment: str = "internal"
    tenant_id: str = "internal"
    status: Literal["active", "blocked"] = "active"
    scopes: List[str] = Field(default_factory=lambda: list(DEFAULT_SCOPES))
    rate_limit_rpm: int = Field(default=120, ge=1)
    concurrent_limit: int = Field(default=25, ge=1)
    daily_budget_usd: float = Field(default=250.0, ge=0)
    default_policy_id: str = "balanced"
    budget_profile_id: Optional[str] = None


class Settings(BaseSettings):
    PROJECT_NAME: str = "LLM Agent Routing Control Plane"
    API_V1_STR: str = "/v1"

    REDIS_URL: str
    DATABASE_URL: str
    CATALOG_PATH: str = "models_config.json"
    PROBE_PROXY: Optional[str] = None
    SIGNAL_FRESHNESS_SECONDS: int = Field(default=90, ge=5)
    DECISION_TTL_SECONDS: int = Field(default=300, ge=30)
    API_KEY_PEPPER: str = ""
    BOOTSTRAP_AGENT_CREDENTIALS: List[BootstrapAgentCredential] = Field(default_factory=list)

    # Legacy dev bootstrap support. These keys are only used to seed hashed credentials.
    AGENT_API_KEYS: Dict[str, str] = Field(default_factory=dict)

    OUTCOME_STREAM_NAME: str = "routing-outcomes"
    PROBE_STREAM_NAME: str = "routing-probes"
    PROBE_BATCH_SIZE: int = Field(default=20, ge=1)
    PROBE_INTERVAL_SECONDS: int = Field(default=60, ge=5)
    DEFAULT_POLICY_ID: str = "balanced"
    DEFAULT_ENVIRONMENT: str = "internal"

    KIMI_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def catalog_path(self) -> Path:
        return Path(self.CATALOG_PATH).resolve() if Path(self.CATALOG_PATH).is_absolute() else (Path(__file__).resolve().parents[2] / self.CATALOG_PATH)

    @property
    def bootstrap_agent_credentials(self) -> List[BootstrapAgentCredential]:
        credentials = list(self.BOOTSTRAP_AGENT_CREDENTIALS)
        for api_key, agent_id in self.AGENT_API_KEYS.items():
            credentials.append(
                BootstrapAgentCredential(
                    api_key=api_key,
                    agent_id=agent_id,
                    environment=self.DEFAULT_ENVIRONMENT,
                    default_policy_id=self.DEFAULT_POLICY_ID,
                )
            )
        return credentials


settings = Settings()
