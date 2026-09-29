from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db_session, require_feature
from app.core.logging import get_logger
from app.schemas.ai import LisaAskRequest, LisaAskResponse
from app.schemas.auth import CurrentUser
from app.schemas.lisa_context import LisaConversationContextResponse
from app.services.ai.agent_service import ask_lisa
from app.services.ai.provider import (
    AIProviderError,
    AIProviderNotConfiguredError,
    NotConfiguredProvider,
    get_ai_provider,
)
from app.services.lisa import context_service

router = APIRouter(
    prefix="/lisa",
    tags=["lisa"],
    dependencies=[Depends(require_feature("lisa_ai_copilot"))],
)
logger = get_logger(__name__)


@router.get("/status")
def get_lisa_status(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, object]:
    provider = get_ai_provider()
    is_configured = not isinstance(provider, NotConfiguredProvider)
    return {
        "configured": is_configured,
        "provider": getattr(provider, "_model", "none") if is_configured else "not_configured",
    }


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
    except Exception as exc:  # noqa: BLE001 - honest, controlled failure; never a fabricated response
        # M5.2: a provider that raises anything other than the two typed
        # errors above (malformed/unexpected output, a client-library bug,
        # a network error the provider itself didn't wrap) must still
        # surface as a controlled failure, not an unhandled 500 with an
        # internal stack trace. The message is deliberately generic --
        # exc's own text may contain provider-internal details.
        logger.warning("ai_provider_unexpected_failure", error=str(exc))
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "code": "ai_provider_error",
                    "message": "The AI provider returned an unexpected error. Please try again.",
                }
            },
        )
    return LisaAskResponse.model_validate(result)


@router.get("/context", response_model=LisaConversationContextResponse)
def get_context(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> LisaConversationContextResponse:
    context = context_service.get_or_create_context(
        db, organization_id=current_user.organization_id, user_id=current_user.id
    )
    return LisaConversationContextResponse.model_validate(context)


@router.post("/context/reset", response_model=LisaConversationContextResponse)
def reset_context(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> LisaConversationContextResponse:
    context = context_service.get_or_create_context(
        db, organization_id=current_user.organization_id, user_id=current_user.id
    )
    context = context_service.reset_context(db, context)
    return LisaConversationContextResponse.model_validate(context)
