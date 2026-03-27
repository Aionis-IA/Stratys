"""Authentification JWT et hachage des mots de passe."""
from datetime import datetime, timedelta
from typing import Annotated

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

# Config (à mettre en variables d'environnement en production)
SECRET_KEY = "stratys-secret-dev-change-en-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 h

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def hash_password(password: str) -> str:
    """Hash un mot de passe avec bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Vérifie un mot de passe contre son hash."""
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    """Crée un token JWT."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Dépendance : utilisateur courant à partir du token Bearer."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM]
        )
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé",
        )
    return user


def get_subscribed_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Dépendance : utilisateur courant uniquement s'il est abonné."""
    if not user.is_subscribed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Abonnement requis pour accéder au diagnostic",
        )
    return user


COOKIE_NAME = "stratys_token"


def get_current_user_web(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Utilisateur courant depuis le cookie (pour les pages web). Redirige vers /login si invalide."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise RedirectResponse(url="/login", status_code=302)
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise RedirectResponse(url="/login", status_code=302)
    except JWTError:
        raise RedirectResponse(url="/login", status_code=302)
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active:
        raise RedirectResponse(url="/login", status_code=302)
    return user


def get_subscribed_user_web(
    user: Annotated[User, Depends(get_current_user_web)],
) -> User:
    """Utilisateur abonné pour les pages web. Redirige vers /login si non abonné."""
    if not user.is_subscribed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Abonnement requis pour accéder au diagnostic",
        )
    return user
