"""Routes des pages web (templates Jinja2)."""
import os
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.analyze import analyze_business, analyze_business_particulier
from app.auth import (
    COOKIE_NAME,
    create_access_token,
    get_current_user_web,
    get_subscribed_user_web,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.history import format_history_for_template, last_diagnostics_for_user, save_diagnostic_history
from app.models import DiagnosticHistory, User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
load_dotenv()

BETA_CODE = os.getenv("BETA_CODE", "").strip()
BETA_COOKIE_NAME = "stratys_beta_code"


def _dashboard_url(user: User) -> str:
    if getattr(user, "user_type", None) == "particulier":
        return "/dashboard/particulier"
    return "/dashboard/entreprise"


def _history_context(db: Session, user_id: int) -> dict:
    rows = last_diagnostics_for_user(db, user_id, 5)
    return {"history": format_history_for_template(rows)}


def _form_last_nonempty_str(form, key: str) -> str:
    """Dernière valeur non vide si le navigateur envoie plusieurs champs du même nom."""
    vals = form.getlist(key)
    if not vals:
        return ""
    for v in reversed(vals):
        s = str(v).strip() if v is not None else ""
        if s:
            return s
    return str(vals[-1] or "").strip()


def _form_last_int(form, key: str) -> Optional[int]:
    vals = form.getlist(key)
    if not vals:
        return None
    for v in reversed(vals):
        try:
            return int(str(v).strip())
        except (TypeError, ValueError):
            continue
    return None


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
    raw = (request.query_params.get("type") or "").strip().lower()
    signup_type = raw if raw in ("particulier", "entreprise") else "entreprise"
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={"signup_type": signup_type},
    )


@router.post("/register")
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    user_type: str = Form("entreprise"),
    company_name: str = Form(""),
    sector: str = Form(""),
    db: Annotated[Session, Depends(get_db)] = None,
):
    ut = (user_type or "entreprise").strip().lower()
    if ut not in ("particulier", "entreprise"):
        ut = "entreprise"
    cn = (company_name or "").strip()
    sec = (sector or "").strip()
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "error": "Un compte existe déjà avec cet email.",
                "signup_type": ut,
                "company_name": cn if ut == "entreprise" else "",
                "sector": sec if ut == "entreprise" else "",
            },
            status_code=400,
        )
    user_kw: dict = {
        "email": email,
        "hashed_password": hash_password(password),
        "user_type": ut,
    }
    if ut == "entreprise":
        user_kw["company_name"] = cn
        user_kw["sector"] = sec
    else:
        user_kw["company_name"] = ""
        user_kw["sector"] = ""
    user = User(**user_kw)
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
    response = RedirectResponse(url=_dashboard_url(user), status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=60 * 24 * 60,  # 24 h
        samesite="lax",
    )
    return response


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_redirect(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user_web)],
):
    return RedirectResponse(url=_dashboard_url(current_user), status_code=302)


@router.get("/dashboard/entreprise", response_class=HTMLResponse)
def dashboard_entreprise(
    request: Request,
    user: Annotated[User, Depends(get_current_user_web)],
    db: Annotated[Session, Depends(get_db)],
):
    if user.user_type != "entreprise":
        return RedirectResponse(url=_dashboard_url(user), status_code=302)
    ctx = _history_context(db, user.id)
    ctx["company_name"] = (getattr(user, "company_name", None) or "").strip()
    return templates.TemplateResponse(
        request=request,
        name="dashboard_entreprise.html",
        context=ctx,
    )


@router.get("/dashboard/particulier", response_class=HTMLResponse)
def dashboard_particulier(
    request: Request,
    user: Annotated[User, Depends(get_current_user_web)],
    db: Annotated[Session, Depends(get_db)],
):
    if user.user_type != "particulier":
        return RedirectResponse(url=_dashboard_url(user), status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="dashboard_particulier.html",
        context=_history_context(db, user.id),
    )


@router.get("/analyze")
@router.get("/analyze/")
def analyze_get_redirect():
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/analyze/particulier")
@router.get("/analyze/particulier/")
def analyze_particulier_get_redirect():
    return RedirectResponse(url="/dashboard/particulier", status_code=302)


@router.post("/analyze")
@router.post("/analyze/")
async def analyze_submit(
    request: Request,
    current_user: Annotated[User, Depends(get_subscribed_user_web)],
    db: Annotated[Session, Depends(get_db)],
):
    if current_user.user_type != "entreprise":
        return RedirectResponse(url=_dashboard_url(current_user), status_code=302)
    form = await request.form()
    print("[Stratys DEBUG] POST /analyze — champs reçus (ordre getlist):", flush=True)
    for _key in form.keys():
        for _i, _item in enumerate(form.getlist(_key)):
            _s = str(_item)
            _prev = _s[:400] + ("…" if len(_s) > 400 else "")
            print(f"  [{_key!r}][{_i}] len={len(_s)} value={_prev!r}", flush=True)

    situation = _form_last_nonempty_str(form, "situation")
    user_offer = _form_last_nonempty_str(form, "user_offer")
    main_blocker = _form_last_nonempty_str(form, "main_blocker")
    if not situation or not user_offer or not main_blocker:
        raise HTTPException(status_code=422, detail="Champs obligatoires manquants.")
    revenue = _form_last_int(form, "revenue")
    if revenue is None:
        raise HTTPException(status_code=422, detail="Revenu invalide ou manquant.")

    def _optional_form_str(key: str) -> Optional[str]:
        s = _form_last_nonempty_str(form, key)
        return s if s else None

    prospects_per_week = _optional_form_str("prospects_per_week")
    closing_rate = _optional_form_str("closing_rate")

    data = {
        "situation": situation,
        "revenue": revenue,
        "user_offer": user_offer,
        "prospects_per_week": prospects_per_week,
        "closing_rate": closing_rate,
        "main_blocker": main_blocker,
    }
    _data_repr = repr(data)
    if len(_data_repr) > 2500:
        _data_repr = _data_repr[:2500] + "…"
    print("[Stratys DEBUG] POST /analyze — dict passé à analyze_business:", _data_repr, flush=True)
    result = analyze_business(data)
    diag_id = save_diagnostic_history(db, current_user.id, "entreprise", result)
    request.session["analyze_diag_id"] = diag_id
    request.session["analyze_kind"] = "entreprise"
    request.session.pop("analyze_result", None)
    return RedirectResponse(url="/result", status_code=302)


@router.post("/analyze/particulier")
@router.post("/analyze/particulier/")
def analyze_particulier_submit(
    request: Request,
    situation: str = Form(...),
    net_salary: int = Form(...),
    ambition: str = Form(...),
    job_satisfaction: int = Form(...),
    main_blocker: str = Form(...),
    passer_entrepreneur: Optional[str] = Form(None),
    current_user: Annotated[User, Depends(get_subscribed_user_web)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    if current_user.user_type != "particulier":
        return RedirectResponse(url=_dashboard_url(current_user), status_code=302)
    data = {
        "situation": situation.strip(),
        "net_salary": net_salary,
        "ambition": ambition.strip(),
        "job_satisfaction": job_satisfaction,
        "main_blocker": main_blocker.strip(),
    }
    result = analyze_business_particulier(data)
    diag_id = save_diagnostic_history(db, current_user.id, "particulier", result)
    if passer_entrepreneur == "on":
        u = db.query(User).filter(User.id == current_user.id).first()
        if u:
            u.user_type = "entreprise"
            db.commit()
    request.session["analyze_diag_id"] = diag_id
    request.session["analyze_kind"] = "particulier"
    request.session.pop("analyze_result", None)
    return RedirectResponse(url="/result", status_code=302)


@router.get("/result", response_class=HTMLResponse)
def result(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user_web)],
    db: Annotated[Session, Depends(get_db)],
):
    result_data = None
    raw_diag_id = request.session.get("analyze_diag_id")
    if raw_diag_id is not None:
        try:
            diag_id = int(raw_diag_id)
        except (TypeError, ValueError):
            diag_id = None
        else:
            row = (
                db.query(DiagnosticHistory)
                .filter(
                    DiagnosticHistory.id == diag_id,
                    DiagnosticHistory.user_id == current_user.id,
                )
                .first()
            )
            if row and row.result_payload and isinstance(row.result_payload, dict):
                result_data = row.result_payload
    if not result_data:
        result_data = request.session.get("analyze_result")
    if not result_data:
        return RedirectResponse(url=_dashboard_url(current_user), status_code=302)
    kind = request.session.get("analyze_kind") or "entreprise"
    hist_ctx = _history_context(db, current_user.id)
    return templates.TemplateResponse(
        request=request,
        name="result.html",
        context={
            "analyze_kind": kind,
            "score": result_data.get("score", 0),
            "issues": result_data.get("issues", []),
            "summary": result_data.get("summary", ""),
            "strength": result_data.get("strength", ""),
            "weakness": result_data.get("weakness", ""),
            "potentiel_croissance": result_data.get("potentiel_croissance", ""),
            "risque_principal": result_data.get("risque_principal", ""),
            "intention_lancement": result_data.get("intention_lancement", False),
            "etapes_lancement": result_data.get("etapes_lancement"),
            **hist_ctx,
        },
    )
