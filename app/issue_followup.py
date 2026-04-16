"""Évaluation Groq : les problèmes du diagnostic précédent sont-ils résolus au vu du nouveau ?"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from app.analyze import GROQ_MODEL, extract_json_from_groq_response

load_dotenv()


def extract_three_issue_titles(result: dict[str, Any]) -> list[str]:
    """Extrait exactement 3 titres d’axes depuis le résultat d’analyse."""
    issues = result.get("issues")
    if not isinstance(issues, list):
        issues = []
    out: list[str] = []
    for i in range(3):
        if i < len(issues) and isinstance(issues[i], dict):
            t = str(issues[i].get("title", "") or "").strip()
            out.append(t if t else "—")
        else:
            out.append("—")
    return out


def _new_diagnostic_text_block(new_result: dict[str, Any], user_type: str) -> str:
    """Bloc texte du nouveau diagnostic pour le prompt."""
    issues = new_result.get("issues") or []
    new_titles: list[str] = []
    if isinstance(issues, list):
        for it in issues[:3]:
            if isinstance(it, dict):
                new_titles.append(str(it.get("title", "") or "").strip())
    kind = "entrepreneur / activité" if user_type == "entreprise" else "salarié / carrière"
    return (
        f"Type de profil : {kind}\n\n"
        f"Score : {new_result.get('score', 0)}\n\n"
        f"Résumé :\n{new_result.get('summary', '')}\n\n"
        f"Force :\n{new_result.get('strength', '')}\n\n"
        f"Faiblesse :\n{new_result.get('weakness', '')}\n\n"
        f"Potentiel / risque (si présents) :\n"
        f"{new_result.get('potentiel_croissance', '')}\n{new_result.get('risque_principal', '')}\n\n"
        f"Titres des 3 axes du NOUVEAU diagnostic :\n"
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
    Retourne une liste de 3 booléens ou None si l’appel échoue.
    """
    titles = [str(t or "").strip() or "—" for t in previous_titles[:3]]
    while len(titles) < 3:
        titles.append("—")
    titles = titles[:3]

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None

    system = (
        "Tu es un analyseur factuel pour le suivi de diagnostics Stratys. "
        "On te donne les 3 titres de problèmes du diagnostic PRÉCÉDENT et le contenu du diagnostic NOUVEAU. "
        "Pour chaque titre du diagnostic précédent (dans l’ordre), décide si ce problème semble "
        "RÉSOLU ou largement dépassé au vu du nouveau contexte (true), ou toujours EN COURS / pertinent (false). "
        "Sois strict : true seulement si le nouveau diagnostic montre clairement une évolution ou une résolution crédible sur ce point. "
        "Réponds UNIQUEMENT avec un objet JSON UTF-8 valide, sans markdown, de la forme :\n"
        '{"resolved": [true, false, true]}\n'
        "Le tableau a EXACTEMENT 3 booléens dans le MÊME ORDRE que les 3 titres précédents fournis. "
        "IMPORTANT: JSON uniquement, pas de texte autour."
    )
    user_msg = (
        "Titres des 3 problèmes du diagnostic PRÉCÉDENT (dans l’ordre) :\n"
        f"1. {titles[0]}\n2. {titles[1]}\n3. {titles[2]}\n\n"
        "--- NOUVEAU DIAGNOSTIC ---\n"
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
            max_tokens=1024,
        )
        raw = (completion.choices[0].message.content or "").strip()
        parsed = extract_json_from_groq_response(raw)
        arr = parsed.get("resolved")
        if not isinstance(arr, list):
            return None
        out: list[bool] = []
        for i in range(3):
            if i < len(arr):
                v = arr[i]
                out.append(v is True or str(v).lower() in ("true", "1", "oui"))
            else:
                out.append(False)
        return out[:3]
    except Exception:
        return None


def titles_from_stored_issues(issues: Any) -> list[str]:
    """Rétrocompatibilité : titres depuis la colonne issues (liste d’objets)."""
    if not isinstance(issues, list):
        return ["—", "—", "—"]
    out: list[str] = []
    for i in range(3):
        if i < len(issues) and isinstance(issues[i], dict):
            t = str(issues[i].get("title", "") or "").strip()
            out.append(t if t else "—")
        else:
            out.append("—")
    return out
