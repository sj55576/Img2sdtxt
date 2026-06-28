"""LLM provider management endpoints."""

from fastapi import APIRouter, HTTPException

import deps
from deps import switch_provider, get_available_providers
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
