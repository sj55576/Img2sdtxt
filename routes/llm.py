"""LLM provider management endpoints."""

from fastapi import APIRouter, HTTPException

import deps
from deps import get_available_providers, switch_provider
from models import SwitchProviderRequest

router = APIRouter(prefix="/api/llm", tags=["llm"])

VALID_PROVIDERS = {"openai_compatible", "anthropic", "gemini"}


@router.get("/providers")
def list_providers():
    """Return available LLM providers and their configuration status."""
    providers = get_available_providers()
    return {
        "current": {
            "provider": deps.llm_client.provider_name,
            "model": deps.llm_client.model,
        },
        "providers": providers,
        "fallback": {
            "enabled": deps.fallback_chain is not None,
            "chain": [p.provider_name for p in deps.fallback_chain.providers] if deps.fallback_chain else [],
            "last_used": deps.fallback_chain.last_used_provider if deps.fallback_chain else None,
        },
    }


@router.get("/health")
def provider_health():
    """Return health status of all configured providers."""
    statuses = deps.health_monitor.get_status() if deps.health_monitor else {}
    return {
        "providers": {
            name: {
                "status": status.status,
                "last_check": status.last_check.isoformat(),
                "response_time_ms": status.response_time_ms,
            }
            for name, status in statuses.items()
        },
        "fallback_chain": [p.provider_name for p in deps.fallback_chain.providers] if deps.fallback_chain else [],
        "active_provider": deps.llm_client.provider_name,
    }


@router.post("/provider")
def set_provider(request: SwitchProviderRequest):
    """Switch the active LLM provider at runtime."""
    if request.provider not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{request.provider}'. Valid: {sorted(VALID_PROVIDERS)}",
        )

    try:
        new = switch_provider(
            provider=request.provider,
            model=request.model,
            api_key=request.api_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "success": True,
        "provider": new.provider_name,
        "model": new.model,
    }
