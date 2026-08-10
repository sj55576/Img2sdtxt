"""Small, opt-in API token guard for sensitive endpoints."""

import secrets

from fastapi import HTTPException, Request, status

import config


def require_api_token(request: Request) -> None:
    """Require ``Authorization: Bearer <API_TOKEN>`` when a token is configured."""
    if not config.API_TOKEN:
        return

    scheme, _, supplied_token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(supplied_token, config.API_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid API bearer token is required for this endpoint.",
            headers={"WWW-Authenticate": "Bearer"},
        )
