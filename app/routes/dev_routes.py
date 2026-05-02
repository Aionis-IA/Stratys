"""Routes de développement temporaires — à retirer en production."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DiagnosticHistory, User

router = APIRouter(prefix="/dev", tags=["Dev (temporaire)"])


@router.delete("/reset-users")
def reset_all_users(db: Session = Depends(get_db)):
    """
    Supprime tous les enregistrements d'historique puis tous les utilisateurs.
    À retirer après les tests.
    """
    n = db.query(User).count()
    db.query(DiagnosticHistory).delete(synchronize_session=False)
    db.query(User).delete(synchronize_session=False)
    db.commit()
    return {"utilisateurs_supprimes": n}
