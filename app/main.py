"""Stratys - API SaaS de diagnostic business freelance."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

from app.auth import SECRET_KEY
from app.database import Base, engine
from app.models import User  # noqa: F401 — pour que Base connaisse User
from app.routes import auth_routes, analyze_routes, web_routes

load_dotenv()

BETA_CODE = os.getenv("BETA_CODE", "").strip()
BETA_COOKIE_NAME = "stratys_beta_code"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Au démarrage : création des tables SQLite."""
    Base.metadata.create_all(bind=engine)
    yield
    # Arrêt : rien à faire pour SQLite minimal


app = FastAPI(
    title="Stratys",
    description="Outil de diagnostic business pour freelances — API d'authentification.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


@app.middleware("http")
async def beta_access_guard(request: Request, call_next):
    """Protège toutes les routes tant que le code bêta n'est pas validé."""
    if not BETA_CODE:
        return await call_next(request)

    if request.url.path == "/":
        return await call_next(request)

    beta_cookie = request.cookies.get(BETA_COOKIE_NAME, "")
    if beta_cookie != BETA_CODE:
        return RedirectResponse(url="/", status_code=302)

    return await call_next(request)


@app.exception_handler(403)
async def forbidden_page(request: Request, exc):
    """Affiche une page simple pour les 403 (ex. abonnement requis)."""
    if request.url.path == "/analyze" or "diagnostic" in (getattr(exc, "detail", "") or ""):
        return HTMLResponse(
            "<!DOCTYPE html><html lang='fr'><head><meta charset='UTF-8'><script src='https://cdn.tailwindcss.com'></script></head>"
            "<body class='bg-neutral-900 text-white min-h-screen flex items-center justify-center'><div class='text-center max-w-md px-4'>"
            "<h1 class='text-xl font-semibold mb-2'>Accès restreint</h1><p class='text-neutral-400 mb-4'>Abonnement requis pour accéder au diagnostic.</p>"
            "<a href='/dashboard' class='text-white underline'>Retour au tableau de bord</a></div></body></html>",
            status_code=403,
        )
    from starlette.responses import JSONResponse
    return JSONResponse({"detail": exc.detail}, status_code=403)


app.include_router(web_routes.router)
app.include_router(auth_routes.router)
app.include_router(analyze_routes.router)
