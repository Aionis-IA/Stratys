"""Routes des pages web (templates Jinja2)."""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.analyze import analyze_business, analyze_premium
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


def _dashboard_url(user: User) -> str:
    user_type = (getattr(user, "user_type", None) or "").strip().lower()
    if user_type == "premium":
        return "/dashboard/premium"
    return "/dashboard/entreprise"


def _register_offer_from_query(raw: str) -> str:
    kind = (raw or "").strip().lower()
    if kind == "premium":
        return "premium"
    return "entreprise"


def _user_type_from_register_offer(offer: str) -> str:
    if offer == "premium":
        return "premium"
    return "entreprise"


def _register_offer_meta(offer: str) -> dict[str, str]:
    if offer == "premium":
        return {
            "label": "Entreprise Premium — à partir de 90€/mois",
            "price": "À partir de 90€/mois",
        }
    return {"label": "Entreprise — 30€/mois", "price": "30€/mois"}


def _transition_price_for(target: str) -> str:
    if target == "premium":
        return "à partir de 90€/mois"
    return "30€/mois"


def _can_change_type(current: str, target: str) -> bool:
    if current == target:
        return False
    if current == "entreprise" and target == "premium":
        return True
    return False


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


def _form_option_flag(form, *keys: str) -> bool:
    """Champ 0/1 (hidden ou dernière valeur) : option activée si 1, on, true (vérifie plusieurs noms de champ)."""
    for key in keys:
        vals = form.getlist(key)
        for v in reversed(vals or []):
            s = str(v or "").strip().lower()
            if s in ("1", "on", "true", "oui", "yes", "o"):
                return True
    return False


def _debug_form_option_lists(form, keys: tuple[str, ...]) -> dict[str, list[str]]:
    return {k: [str(x) for x in form.getlist(k)] for k in keys}


@router.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse(request=request, name="landing.html")


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    offer_type = _register_offer_from_query(request.query_params.get("type") or "")
    signup_type = _user_type_from_register_offer(offer_type)
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={
            "signup_type": signup_type,
            "offer_type": offer_type,
            **_register_offer_meta(offer_type),
        },
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
    if ut not in ("entreprise", "premium"):
        ut = "entreprise"
    offer_type = ut
    cn = (company_name or "").strip()
    sec = (sector or "").strip()
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "error": "Un compte existe déjà avec cet email.",
                "signup_type": ut,
                "offer_type": offer_type,
                "company_name": cn,
                "sector": sec,
                **_register_offer_meta(offer_type),
            },
            status_code=400,
        )
    user = User(
        email=email,
        hashed_password=hash_password(password),
        user_type=ut,
        company_name=cn,
        sector=sec,
    )
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


@router.get("/dashboard/premium", response_class=HTMLResponse)
def dashboard_premium(
    request: Request,
    user: Annotated[User, Depends(get_current_user_web)],
    db: Annotated[Session, Depends(get_db)],
):
    if user.user_type != "premium":
        return RedirectResponse(url=_dashboard_url(user), status_code=302)
    ctx = _history_context(db, user.id)
    ctx["company_name"] = (getattr(user, "company_name", None) or "").strip()
    return templates.TemplateResponse(
        request=request,
        name="dashboard_premium.html",
        context=ctx,
    )


@router.get("/analyze")
@router.get("/analyze/")
def analyze_get_redirect():
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/analyze/premium")
@router.get("/analyze/premium/")
def analyze_premium_get_redirect():
    return RedirectResponse(url="/dashboard/premium", status_code=302)


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


@router.post("/analyze/premium")
@router.post("/analyze/premium/")
async def analyze_premium_submit(
    request: Request,
    current_user: Annotated[User, Depends(get_subscribed_user_web)],
    db: Annotated[Session, Depends(get_db)],
):
    if current_user.user_type != "premium":
        return RedirectResponse(url=_dashboard_url(current_user), status_code=302)
    form = await request.form()
    opt_debug = _debug_form_option_lists(
        form,
        ("opt_clarte", "opt_arch", "opt_pivot", "opt_roadmap", "option3", "option4"),
    )
    print("[Stratys DEBUG] POST /analyze/premium — options brutes (getlist):", opt_debug, flush=True)
    situation = _form_last_nonempty_str(form, "situation")
    user_offer = _form_last_nonempty_str(form, "user_offer")
    top_challenges = _form_last_nonempty_str(form, "top_challenges")
    resources = _form_last_nonempty_str(form, "resources")
    goals_12m = _form_last_nonempty_str(form, "goals_12m")
    if not situation or not user_offer or not top_challenges or not resources or not goals_12m:
        raise HTTPException(status_code=422, detail="Champs obligatoires manquants.")
    revenue = _form_last_int(form, "revenue")
    if revenue is None:
        raise HTTPException(status_code=422, detail="Revenu invalide ou manquant.")

    pivot_sel = _form_option_flag(form, "opt_pivot", "option3")
    roadmap_sel = _form_option_flag(form, "opt_roadmap", "option4")
    print(
        "[Stratys DEBUG] POST /analyze/premium — options résolues:",
        {
            "opt_clarte": _form_option_flag(form, "opt_clarte"),
            "opt_arch": _form_option_flag(form, "opt_arch"),
            "opt_pivot": pivot_sel,
            "opt_roadmap": roadmap_sel,
        },
        flush=True,
    )
    data = {
        "situation": situation,
        "revenue": revenue,
        "user_offer": user_offer,
        "top_challenges": top_challenges,
        "resources": resources,
        "goals_12m": goals_12m,
        "opt_clarte": "1" if _form_option_flag(form, "opt_clarte") else "0",
        "opt_arch": "1" if _form_option_flag(form, "opt_arch") else "0",
        "opt_pivot": "1" if pivot_sel else "0",
        "opt_roadmap": "1" if roadmap_sel else "0",
        "option3": "1" if pivot_sel else "0",
        "option4": "1" if roadmap_sel else "0",
    }
    result = analyze_premium(data)
    diag_id = save_diagnostic_history(db, current_user.id, "premium", result)
    request.session["analyze_diag_id"] = diag_id
    request.session["analyze_kind"] = "premium"
    request.session.pop("analyze_result", None)
    return RedirectResponse(url="/result", status_code=302)


@router.get("/account/change-type/confirm", response_class=HTMLResponse)
def change_type_confirm_page(
    request: Request,
    target: str,
    user: Annotated[User, Depends(get_current_user_web)],
):
    current = (user.user_type or "").strip().lower()
    normalized_target = (target or "").strip().lower()
    if not _can_change_type(current, normalized_target):
        return RedirectResponse(url=_dashboard_url(user), status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="change_type_confirm.html",
        context={
            "current_type": current,
            "target_type": normalized_target,
            "target_price": _transition_price_for(normalized_target),
        },
    )


@router.post("/account/change-type/confirm")
def change_type_confirm_submit(
    target: str = Form(...),
    user: Annotated[User, Depends(get_current_user_web)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    current = (user.user_type or "").strip().lower()
    normalized_target = (target or "").strip().lower()
    if not _can_change_type(current, normalized_target):
        return RedirectResponse(url=_dashboard_url(user), status_code=302)
    user.user_type = normalized_target
    db.commit()
    return RedirectResponse(url=_dashboard_url(user), status_code=302)


@router.get("/result/premium", response_class=HTMLResponse)
def result_premium_redirect():
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
    _bs = result_data.get("blind_spots")
    if not isinstance(_bs, list):
        _bs = []
    template_name = "result_premium.html" if kind == "premium" else "result.html"
    return templates.TemplateResponse(
        request=request,
        name=template_name,
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
            "blind_spots": _bs,
            "message_direct": str(result_data.get("message_direct", "") or ""),
            "growth_potential": str(result_data.get("growth_potential", "") or ""),
            "main_risk": str(result_data.get("main_risk", "") or ""),
            "opt_clarte": bool(result_data.get("opt_clarte")),
            "opt_arch": bool(result_data.get("opt_arch")),
            "opt_pivot": bool(result_data.get("opt_pivot")),
            "opt_roadmap": bool(result_data.get("opt_roadmap")),
            "clarte_section": str(result_data.get("clarte_section", "") or ""),
            "angles_morts": result_data.get("angles_morts")
            if isinstance(result_data.get("angles_morts"), list)
            else [],
            "architecture_section": str(result_data.get("architecture_section", "") or ""),
            "pivot_section": str(result_data.get("pivot_section", "") or ""),
            "roadmap_section": str(result_data.get("roadmap_section", "") or ""),
            **hist_ctx,
        },
    )
