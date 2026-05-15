from typing import Optional

from fastapi import Depends, Header, HTTPException, Security, status

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import api_key_header
from app.schemas.routing import AgentPrincipal
from app.services.control_plane import (
    AuthenticationError,
    AuthorizationError,
    ControlPlaneService,
    NotFoundError,
    QuotaExceededError,
    build_redis_runtime,
)
from app.services.persistence import (
    SqlAlchemyCredentialStore,
    SqlAlchemyDecisionStore,
    SqlAlchemyMetadataStore,
)


_control_plane_service: Optional[ControlPlaneService] = None


def get_control_plane_service() -> ControlPlaneService:
    global _control_plane_service
    if _control_plane_service is None:
        credential_store = SqlAlchemyCredentialStore(
            AsyncSessionLocal,
            settings.bootstrap_agent_credentials,
        )
        metadata_store = SqlAlchemyMetadataStore(AsyncSessionLocal)
        decision_store = SqlAlchemyDecisionStore(AsyncSessionLocal)
        _control_plane_service = build_redis_runtime(
            credential_store=credential_store,
            metadata_store=metadata_store,
            decision_store=decision_store,
        )
    return _control_plane_service


def get_idempotency_key(
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> Optional[str]:
    return idempotency_key


async def _authenticate(
    required_scopes: list[str],
    api_key: Optional[str],
    service: ControlPlaneService,
) -> AgentPrincipal:
    try:
        return await service.authenticate(api_key, required_scopes=required_scopes)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except AuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


async def get_routing_decision_principal(
    api_key: Optional[str] = Security(api_key_header),
    service: ControlPlaneService = Depends(get_control_plane_service),
) -> AgentPrincipal:
    return await _authenticate(["routing:decide"], api_key, service)


async def get_routing_outcome_principal(
    api_key: Optional[str] = Security(api_key_header),
    service: ControlPlaneService = Depends(get_control_plane_service),
) -> AgentPrincipal:
    return await _authenticate(["routing:outcome"], api_key, service)


async def get_control_principal(
    api_key: Optional[str] = Security(api_key_header),
    service: ControlPlaneService = Depends(get_control_plane_service),
) -> AgentPrincipal:
    return await _authenticate(["control:read"], api_key, service)


def service_error_to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthorizationError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, AuthenticationError):
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, QuotaExceededError):
        return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal control-plane error")
