import asyncio

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import verify_api_key


def test_verify_api_key_requires_server_configuration(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_API_KEYS", {})

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(verify_api_key("demo-key"))

    assert exc_info.value.status_code == 503


def test_verify_api_key_accepts_configured_key(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_API_KEYS", {"demo-key": "Agent-Demo"})

    agent_name = asyncio.run(verify_api_key("demo-key"))

    assert agent_name == "Agent-Demo"
