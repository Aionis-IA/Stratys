"""Évaluation Groq : les problèmes du diagnostic précédent sont-ils résolus au vu du nouveau ?"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from app.analyze import GROQ_MODEL, extract_json_from_groq_response

load_dotenv()


def extract_issue_titles(result: dict[str, Any], count: int) -> list[str]:
    """Extrait count titres d’axes depuis le résultat d’analyse (3 = entreprise, 5 = premium)."""
    issues = result.get("issues")
    if not isinstance(issues, list):
        issues = []
    c = max(1, min(5, int(count)))
    out: list[str] = []
    for i in range(c):
        if i < len(issues) and isinstance(issues[i], dict):
            t = str(issues[i].get("title", "") or "").strip()
            out.append(t if t else "—")
        else:
            out.append("—")
    return out


def extract_three_issue_titles(result: dict[str, Any]) -> list[str]:
    """Rétrocompatibilité : 3 titres."""
    return extract_issue_titles(result, 3)


def _new_diagnostic_text_block(new_result: dict[str, Any], user_type: str) -> str:
    """Bloc texte du nouveau diagnostic pour le prompt."""
    issues = new_result.get("issues") or []
    new_titles: list[str] = []
    n_axes = 5 if user_type == "premium" else 3
    if isinstance(issues, list):
        for it in issues[:n_axes]:
            if isinstance(it, dict):
                new_titles.append(str(it.get("title", "") or "").strip())
    kind = "entrepreneur / activité"
    _bs = new_result.get("blind_spots", "")
    if isinstance(_bs, list):
        parts: list[str] = []
        for x in _bs:
            if isinstance(x, dict):
                t = str(x.get("title", "") or "").strip()
                e = str(x.get("explanation", "") or "").strip()
                if t and e:
                    parts.append(f"{t} — {e}")
                elif e:
                    parts.append(e)
                elif t:
                    parts.append(t)
            else:
                s = str(x).strip()
                if s:
                    parts.append(s)
        blind_line = " | ".join(parts) if parts else ""
    else:
        blind_line = str(_bs or "")

    return (
        f"Type de profil : {kind}\n\n"
        f"Message direct (si présent) : {new_result.get('message_direct', '')}\n\n"
        f"Score : {new_result.get('score', 0)}\n\n"
        f"Résumé :\n{new_result.get('summary', '')}\n\n"
        f"Force :\n{new_result.get('strength', '')}\n\n"
        f"Faiblesse :\n{new_result.get('weakness', '')}\n\n"
        f"Potentiel / risque (si présents) :\n"
        f"{new_result.get('potentiel_croissance', '')}\n{new_result.get('risque_principal', '')}\n"
        f"{new_result.get('growth_potential', '')}\n{new_result.get('main_risk', '')}\n\n"
        f"Angles morts (si présents) : {blind_line}\n\n"
        f"Titres des axes prioritaires du NOUVEAU diagnostic :\n"
        + "\n".join(f"- {t}" for t in new_titles if t)
    )


def evaluate_previous_issues_resolution(
    previous_titles: list[str],
    new_result: dict[str, Any],
    user_type: str,
) -> list[bool] | None:
    """
    Pour chaque titre de problème du diagnostic précédent, indique si le nouveau diagnostic
    laisse penser que ce point est résolu ou en grande partie dépassé (true) ou toujours d’actualité (false).
    Retourne une liste de 3 à 5 booléens (selon les titres fournis) ou None si l’appel échoue.
    """
    titles = [str(t or "").strip() or "—" for t in (previous_titles or [])]
    if not titles:
        titles = ["—", "—", "—"]
    while len(titles) < 3:
        titles.append("—")
    n = min(len(titles), 5)
    titles = titles[:n]

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None

    system = (
        "Tu es un analyseur factuel pour le suivi de diagnostics Stratys. "
        f"On te donne les {n} titres de problèmes du diagnostic PRÉCÉDENT et le contenu du diagnostic NOUVEAU. "
        "Pour chaque titre du diagnostic précédent (dans l'ordre), décide si ce problème semble "
        "RÉSOLU ou largement dépassé au vu du nouveau contexte (true), ou toujours EN COURS / pertinent (false). "
        "Sois strict : true seulement si le nouveau diagnostic montre clairement une évolution ou une résolution crédible sur ce point. "
        "Réponds UNIQUEMENT avec un objet JSON UTF-8 valide, sans markdown, de la forme :\n"
        '{"resolved": [true, false, ...]}\n'
        f"Le tableau a EXACTEMENT {n} booléens dans le MÊME ORDRE que les {n} titres précédents fournis. "
        "IMPORTANT: JSON uniquement, pas de texte autour."
    )
    lines = [f"{i + 1}. {titles[i]}" for i in range(n)]
    user_msg = (
        f"Titres des {n} problèmes du diagnostic PRÉCÉDENT (dans l'ordre) :\n"
        + "\n".join(lines)
        + "\n\n--- NOUVEAU DIAGNOSTIC ---\n"
        + _new_diagnostic_text_block(new_result, user_type)
    )

    try:
        from groq import Groq

        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=1536,
        )
        raw = (completion.choices[0].message.content or "").strip()
        parsed = extract_json_from_groq_response(raw)
        arr = parsed.get("resolved")
        if not isinstance(arr, list):
            return None
        out: list[bool] = []
        for i in range(n):
            if i < len(arr):
                v = arr[i]
                out.append(v is True or str(v).lower() in ("true", "1", "oui"))
            else:
                out.append(False)
        return out[:n]
    except Exception:
        return None


def titles_from_stored_issues(issues: Any, count: int = 3) -> list[str]:
    """Rétrocompatibilité : titres depuis la colonne issues (liste d’objets)."""
    c = max(1, min(5, int(count)))
    if not isinstance(issues, list):
        return ["—"] * c
    out: list[str] = []
    for i in range(c):
        if i < len(issues) and isinstance(issues[i], dict):
            t = str(issues[i].get("title", "") or "").strip()
            out.append(t if t else "—")
        else:
            out.append("—")
    return out
