"""Routes des pages web (templates Jinja2)."""
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.analyze import analyze_business
from app.auth import (
    COOKIE_NAME,
    create_access_token,
    get_current_user_web,
    get_subscribed_user_web,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
load_dotenv()

BETA_CODE = os.getenv("BETA_CODE", "").strip()
BETA_COOKIE_NAME = "stratys_beta_code"


@router.get("/", response_class=HTMLResponse)
def landing(request: Request):
    beta_cookie = request.cookies.get(BETA_COOKIE_NAME, "")
    if BETA_CODE and beta_cookie != BETA_CODE:
        return templates.TemplateResponse(request=request, name="beta_access.html")
    return templates.TemplateResponse(request=request, name="landing.html")


@router.post("/", response_class=HTMLResponse)
def beta_access_submit(request: Request, beta_code: str = Form("")):
    if not BETA_CODE:
        return RedirectResponse(url="/", status_code=302)

    if beta_code.strip() != BETA_CODE:
        return templates.TemplateResponse(
            request=request,
            name="beta_access.html",
            context={"error": "Code invalide. Veuillez réessayer."},
            status_code=401,
        )

    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=BETA_COOKIE_NAME,
        value=BETA_CODE,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html")


@router.post("/register")
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Annotated[Session, Depends(get_db)] = None,
):
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": "Un compte existe déjà avec cet email."},
            status_code=400,
        )
    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    db.commit()
    return RedirectResponse(url="/login", status_code=302)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Annotated[Session, Depends(get_db)] = None,
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password) or not user.is_active:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Email ou mot de passe incorrect."},
            status_code=401,
        )
    token = create_access_token(data={"sub": user.email})
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=60 * 24 * 60,  # 24 h
        samesite="lax",
    )
    return response


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    _: Annotated[User, Depends(get_current_user_web)],
):
    return templates.TemplateResponse(request=request, name="dashboard.html")


@router.get("/analyze")
@router.get("/analyze/")
def analyze_get_redirect():
    return RedirectResponse(url="/dashboard", status_code=302)


@router.post("/analyze")
@router.post("/analyze/")
def analyze_submit(
    request: Request,
    situation: str = Form(...),
    revenue: int = Form(...),
    user_offer: str = Form(...),
    prospects_per_week: int = Form(...),
    closing_rate: int = Form(...),
    main_blocker: str = Form(...),
    current_user: Annotated[User, Depends(get_subscribed_user_web)] = None,
):
    data = {
        "situation": situation.strip(),
        "revenue": revenue,
        "user_offer": user_offer.strip(),
        "prospects_per_week": prospects_per_week,
        "closing_rate": closing_rate,
        "main_blocker": main_blocker.strip(),
    }
    result = analyze_business(data)
    request.session["analyze_result"] = result
    return RedirectResponse(url="/result", status_code=302)


@router.get("/result", response_class=HTMLResponse)
def result(request: Request):
    result_data = request.session.get("analyze_result")
    if not result_data:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="result.html",
        context={
            "score": result_data.get("score", 0),
            "issues": result_data.get("issues", []),
            "summary": result_data.get("summary", ""),
            "strength": result_data.get("strength", ""),
            "weakness": result_data.get("weakness", ""),
        },
    )
