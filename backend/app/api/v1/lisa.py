from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db_session
from app.schemas.ai import LisaAskRequest, LisaAskResponse
from app.schemas.auth import CurrentUser
from app.services.ai.agent_service import ask_lisa
from app.services.ai.provider import AIProviderError, AIProviderNotConfiguredError, get_ai_provider

router = APIRouter(prefix="/lisa", tags=["lisa"])


@router.post("/ask", response_model=None)
async def ask(
    payload: LisaAskRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> LisaAskResponse | JSONResponse:
    provider = get_ai_provider()
    try:
        result = await ask_lisa(
            db,
            provider=provider,
            user=current_user,
            question=payload.question,
            conversation_history=payload.conversation_history,
            current_entity=payload.current_entity,
        )
    except AIProviderNotConfiguredError:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "ai_not_configured",
                    "message": (
                        "AI model is not configured. "
                        "Set ANTHROPIC_API_KEY to enable the real agent."
                    ),
                }
            },
        )
    except AIProviderError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": {"code": "ai_provider_error", "message": str(exc)}},
        )
    return LisaAskResponse.model_validate(result)
