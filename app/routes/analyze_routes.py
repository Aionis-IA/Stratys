"""Route de diagnostic business — réservée aux abonnés."""
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.analyze import analyze_business
from app.auth import get_subscribed_user
from app.models import User

# Préfixe /api pour éviter le conflit avec POST /analyze (formulaire HTML dans web_routes).
router = APIRouter(prefix="/api", tags=["Diagnostic"])


class AnalyzeIn(BaseModel):
    situation: str = Field(..., description="Qui tu es, ce que tu fais, où tu en es")
    revenue: int = Field(..., ge=0, description="Revenus mensuels en euros")
    user_offer: str = Field(..., description="Promesse / offre en une phrase")
    prospects_per_week: int = Field(
        ...,
        ge=0,
        description="Nombre de prospects par semaine",
    )
    closing_rate: int = Field(
        ...,
        ge=0,
        le=100,
        description="Taux de closing en % (0-100)",
    )
    main_blocker: str = Field(
        ...,
        description="Blocage principal (texte libre)",
    )


@router.post(
    "/analyze",
    summary="Lancer le diagnostic business",
    description="Réservé aux utilisateurs abonnés. Retourne un score 0-100 et 3 axes d'action (Groq).",
)
def analyze(
    data: AnalyzeIn,
    current_user: Annotated[User, Depends(get_subscribed_user)],
):
    """Diagnostic : score + issues (titre, impact, actions)."""
    payload = {
        "situation": data.situation.strip(),
        "revenue": data.revenue,
        "user_offer": data.user_offer.strip(),
        "prospects_per_week": data.prospects_per_week,
        "closing_rate": data.closing_rate,
        "main_blocker": data.main_blocker.strip(),
    }
    return analyze_business(payload)
