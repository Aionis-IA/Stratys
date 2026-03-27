"""Routes d'authentification : inscription, connexion, profil."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models import User

router = APIRouter(tags=["Authentification"])


# Schémas
class RegisterIn(BaseModel):
    email: EmailStr
    password: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    email: str


@router.post("/register", response_model=MeOut, summary="Inscription")
def register(
    data: RegisterIn,
    db: Annotated[Session, Depends(get_db)],
):
    """Inscription d'un nouvel utilisateur."""
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un compte existe déjà avec cet email.",
        )
    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return MeOut(email=user.email)


@router.post("/login", response_model=TokenOut, summary="Connexion")
def login(
    data: LoginIn,
    db: Annotated[Session, Depends(get_db)],
):
    """Connexion : retourne un token JWT."""
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé.",
        )
    token = create_access_token(data={"sub": user.email})
    return TokenOut(access_token=token)


@router.get("/me", response_model=MeOut, summary="Profil courant")
def me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Retourne l'email de l'utilisateur connecté."""
    return MeOut(email=current_user.email)
