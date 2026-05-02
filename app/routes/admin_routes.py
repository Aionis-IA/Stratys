"""Routes admin réservées aux tests (sans authentification)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DiagnosticHistory, User

router = APIRouter(tags=["Admin (test)"])


@router.get("/admin/reset-user")
def reset_user_for_testing(
    email: str = Query(..., description="E-mail du compte à réinitialiser"),
    db: Session = Depends(get_db),
):
    """
    Supprime tout l'historique de diagnostics de l'utilisateur et remet user_type à « standard ».
    Le compte (mot de passe, etc.) est conservé.
    """
    normalized = (email or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Paramètre email requis.")

    user = db.query(User).filter(User.email == normalized).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Aucun utilisateur avec cet e-mail.")

    deleted = (
        db.query(DiagnosticHistory)
        .filter(DiagnosticHistory.user_id == user.id)
        .delete(synchronize_session=False)
    )
    user.user_type = "standard"
    db.commit()

    return {
        "ok": True,
        "email": user.email,
        "diagnostic_history_deleted": deleted,
        "user_type": user.user_type,
    }
