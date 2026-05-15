from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import (
    get_control_plane_service,
    get_control_principal,
    get_idempotency_key,
    get_routing_decision_principal,
    get_routing_outcome_principal,
    service_error_to_http,
)
from app.schemas.routing import (
    AgentPrincipal,
    CatalogResponse,
    HealthResponse,
    PolicyListResponse,
    RoutingDecisionRequest,
    RoutingDecisionResponse,
    RoutingOutcomeRequest,
    RoutingOutcomeResponse,
)
from app.services.control_plane import ControlPlaneService


router = APIRouter()


@router.post("/routing/decisions", response_model=RoutingDecisionResponse, tags=["Routing"])
async def create_routing_decision(
    request_body: RoutingDecisionRequest,
    principal: AgentPrincipal = Depends(get_routing_decision_principal),
    idempotency_key: str | None = Depends(get_idempotency_key),
    service: ControlPlaneService = Depends(get_control_plane_service),
) -> RoutingDecisionResponse:
    try:
        return await service.create_decision(principal, request_body, idempotency_key)
    except Exception as exc:
        raise service_error_to_http(exc) from exc


@router.post("/routing/outcomes", response_model=RoutingOutcomeResponse, tags=["Routing"])
async def record_routing_outcome(
    request_body: RoutingOutcomeRequest,
    principal: AgentPrincipal = Depends(get_routing_outcome_principal),
    idempotency_key: str | None = Depends(get_idempotency_key),
    service: ControlPlaneService = Depends(get_control_plane_service),
) -> RoutingOutcomeResponse:
    try:
        return await service.record_outcome(principal, request_body, idempotency_key)
    except Exception as exc:
        raise service_error_to_http(exc) from exc


@router.get("/control/health/live", response_model=HealthResponse, tags=["Control"])
async def live_health(
    service: ControlPlaneService = Depends(get_control_plane_service),
) -> HealthResponse:
    return await service.live_health()


@router.get("/control/health/ready", response_model=HealthResponse, tags=["Control"])
async def ready_health(
    service: ControlPlaneService = Depends(get_control_plane_service),
) -> HealthResponse:
    return await service.ready_health()


@router.get("/control/catalog", response_model=CatalogResponse, tags=["Control"])
async def get_catalog(
    _principal: AgentPrincipal = Depends(get_control_principal),
    service: ControlPlaneService = Depends(get_control_plane_service),
) -> CatalogResponse:
    return await service.get_catalog()


@router.get("/control/policies", response_model=PolicyListResponse, tags=["Control"])
async def get_policies(
    _principal: AgentPrincipal = Depends(get_control_principal),
    service: ControlPlaneService = Depends(get_control_plane_service),
) -> PolicyListResponse:
    return await service.get_policies()
