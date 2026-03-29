"""Diagnostic Stratys — analyse via Groq (JSON structuré)."""

from __future__ import annotations

import copy
import json
import os
import re
from typing import Any

from dotenv import load_dotenv

load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"

# Structure renvoyée si le JSON Groq est illisible après toutes les tentatives.
_DEFAULT_GROQ_JSON_ERROR: dict[str, Any] = {
    "summary": (
        "On n’a pas pu lire la réponse technique de Groq : le JSON était invalide. "
        "Réessaie en raccourcissant ta situation et ton blocage, ou vérifie ta clé API."
    ),
    "strength": "Impossible d’identifier une force sans réponse valide du modèle — relance le diagnostic.",
    "weakness": "Impossible d’identifier une faiblesse sans réponse valide du modèle — relance le diagnostic.",
    "score": 0,
    "issues": [
        {
            "title": "Réponse Groq illisible (JSON invalide)",
            "impact": "Le modèle a renvoyé du texte que l’app n’a pas pu parser en JSON. Réessaie ou raccourcis tes champs.",
            "actions": [
                "Aujourd'hui : relance le diagnostic une fois.",
                "Aujourd'hui : réduis « Ta situation » et « Ton blocage principal » à l’essentiel (moins de 800 caractères chacun).",
            ],
        }
    ],
}


def _strip_trailing_commas(s: str) -> str:
    """Supprime les virgules en trop avant } ou ] (erreur fréquente des LLM)."""
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r",(\s*[}\]])", r"\1", s)
    return s


def _candidate_json_strings(raw: str) -> list[str]:
    """Génère des candidats à parser, du plus probable au plus large."""
    t = (raw or "").strip()
    out: list[str] = []
    if not t:
        return out

    # Bloc markdown ```json ... ```
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.IGNORECASE)
    if fence:
        out.append(fence.group(1).strip())

    out.append(t)

    # Sous-chaîne du premier { au dernier } (texte autour ignoré)
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1 and end > start:
        out.append(t[start : end + 1])

    # Dédupliquer en gardant l’ordre
    seen: set[str] = set()
    uniq: list[str] = []
    for c in out:
        if c and c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def extract_json_from_groq_response(text: str) -> dict[str, Any]:
    """
    Extrait et parse un objet JSON depuis la réponse Groq (texte autour, markdown, virgules traînantes).

    Si tout échoue, renvoie une structure d’erreur par défaut (score + issues minimal).
    """
    for candidate in _candidate_json_strings(text):
        cleaned = _strip_trailing_commas(candidate)
        try:
            obj = json.loads(cleaned)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        # Deuxième passe virgules (imbriquées)
        cleaned2 = _strip_trailing_commas(cleaned)
        if cleaned2 != cleaned:
            try:
                obj = json.loads(cleaned2)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass

    return copy.deepcopy(_DEFAULT_GROQ_JSON_ERROR)


def _normalize_issues(raw: Any) -> list[dict[str, Any]]:
    """Garantit 3 issues avec title, impact, actions (min 2 chaînes)."""
    if not isinstance(raw, list):
        raw = []
    out: list[dict[str, Any]] = []
    for item in raw[:3]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "") or "").strip() or "Point à traiter"
        impact = str(item.get("impact", "") or "").strip() or "Impact non précisé."
        actions = item.get("actions")
        if isinstance(actions, str):
            actions_list = [a.strip() for a in re.split(r"[\n•\-–;]", actions) if a.strip()]
        elif isinstance(actions, list):
            actions_list = [str(a).strip() for a in actions if str(a).strip()]
        else:
            actions_list = []
        while len(actions_list) < 2:
            actions_list.append(
                "Aujourd'hui : note une action concrète datée (heure + livrable) liée à ce que tu as décrit."
            )
        out.append({"title": title, "impact": impact, "actions": actions_list[:8]})

    fallback = [
        {
            "title": "Ton diagnostic n’a pas pu être complété proprement.",
            "impact": "Reviens avec plus de détail ou réessaie dans un instant.",
            "actions": [
                "Aujourd'hui : reprends le formulaire et cite des chiffres et faits précis (revenus, nombre de RDV, refus).",
                "Aujourd'hui : vérifie que GROQ_API_KEY est bien défini dans ton environnement.",
            ],
        },
        {
            "title": "Sans données précises, tu navigues à l’aveugle.",
            "impact": "Le business se joue sur des faits, pas sur des intentions.",
            "actions": [
                "Aujourd'hui : écris 3 métriques hebdo à suivre (prospects, closes, CA).",
                "Aujourd'hui : choisis UNE action commerciale à faire dans les 24h.",
            ],
        },
        {
            "title": "Le prochain pas doit être mesurable.",
            "impact": "Si tu ne mesures pas, tu ne corriges pas.",
            "actions": [
                "Aujourd'hui : définis un objectif chiffré pour la semaine (1 seul).",
                "Aujourd'hui : bloque 45 minutes pour exécuter sans distraction.",
            ],
        },
    ]
    for f in fallback:
        if len(out) >= 3:
            break
        out.append(f)
    return out[:3]


def _fallback_result(reason: str) -> dict[str, Any]:
    return {
        "score": 0,
        "summary": (
            "Le diagnostic n’a pas pu aboutir : corrige le point ci-dessous et relance. "
            "Sans réponse valide de l’API, on ne peut pas te résumer ta situation correctement."
        ),
        "strength": "On n’a pas pu analyser tes points forts tant que le diagnostic ne fonctionne pas.",
        "weakness": "On n’a pas pu analyser tes points faibles tant que le diagnostic ne fonctionne pas.",
        "issues": _normalize_issues(
            [
                {
                    "title": "Diagnostic indisponible pour l’instant",
                    "impact": reason,
                    "actions": [
                        "Vérifie que la variable d’environnement GROQ_API_KEY est définie (fichier .env à la racine du projet).",
                        "Relance le diagnostic après avoir redémarré le serveur.",
                    ],
                }
            ]
        ),
    }


def _optional_non_negative_int(value: Any) -> int | None:
    """Entier >= 0 si la valeur est renseignée, sinon None (champ absent ou vide)."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        n = int(s)
    except ValueError:
        return None
    return n if n >= 0 else None


def _optional_closing_rate(value: Any) -> int | None:
    """Taux 0–100 si renseigné, sinon None."""
    n = _optional_non_negative_int(value)
    if n is None:
        return None
    return n if n <= 100 else None


def analyze_business(data: dict) -> dict[str, Any]:
    """
    Envoie les champs à Groq et attend un JSON :
    {
      "summary": str (2-3 phrases),
      "strength": str (1 force principale),
      "weakness": str (1 faiblesse principale),
      "score": 0-100,
      "issues": [ { "title", "impact", "actions": [str, ...] }, x3 ]
    }
    Les champs prospection hebdo et taux de closing sont optionnels : s'ils sont absents,
    ils ne sont pas envoyés au modèle et ne doivent pas apparaître dans le diagnostic.
    """
    situation = str(data.get("situation", "") or "").strip()
    revenue = int(data.get("revenue", 0) or 0)
    user_offer = str(data.get("user_offer", "") or "").strip()
    prospects_per_week = _optional_non_negative_int(data.get("prospects_per_week"))
    closing_rate = _optional_closing_rate(data.get("closing_rate"))
    main_blocker = str(data.get("main_blocker", "") or "").strip()
    has_prospects = prospects_per_week is not None
    has_closing = closing_rate is not None

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return _fallback_result("Clé API Groq absente (GROQ_API_KEY).")

    metrics_hint = (
        "Tu peux aussi t’appuyer sur revenus, offre"
        + (", volume de prospection et taux de closing" if (has_prospects or has_closing) else "")
        + " pour être spécifique. "
    )
    if not has_prospects and not has_closing:
        metrics_rules = (
            "Les données ne comportent PAS de volume de prospection hebdomadaire ni de taux de closing : "
            "n’invente aucune métrique, ne les mentionne nulle part (summary, strength, weakness, issues), "
            "et n’en déduis rien pour le score — base le score uniquement sur situation, revenus, offre et blocage. "
        )
    elif not has_prospects:
        metrics_rules = (
            "Les données ne comportent PAS de volume de prospection hebdomadaire : "
            "ne le mentionne nulle part et n’en déduis rien ; le score s’appuie sur les autres champs fournis. "
        )
    elif not has_closing:
        metrics_rules = (
            "Les données ne comportent PAS de taux de closing : "
            "ne le mentionne nulle part et n’en déduis rien ; le score s’appuie sur les autres champs fournis. "
        )
    else:
        metrics_rules = ""

    system_prompt = (
        "Tu es un mentor business pour freelances. Tu parles à la personne au TU systématiquement : jamais de vouvoiement, "
        "jamais de « vous », même dans title, impact et actions. "
        "Tu réponds UNIQUEMENT avec un objet JSON valide UTF-8, sans texte avant ou après, sans markdown. "
        "Le JSON doit avoir exactement cette structure :\n"
        '{"summary": "<string>", "strength": "<string>", "weakness": "<string>", "score": <entier 0 à 100>, "issues": [\n'
        '  {"title": "...", "impact": "...", "actions": ["...", "..."]},\n'
        '  {"title": "...", "impact": "...", "actions": ["...", "..."]},\n'
        '  {"title": "...", "impact": "...", "actions": ["...", "..."]}\n'
        "]}\n"
        + metrics_rules
        + "Champ strength : UNE phrase en français, tutoiement obligatoire. "
        "Ta principale force visible dans ce qu’elle a écrit : positif et encourageant, mais honnête — "
        "appuie-toi sur des faits tirés de ses textes (situation, offre, chiffres). Pas de flatterie creuse. "
        "Champ weakness : UNE phrase en français, tutoiement obligatoire. "
        "Sa principale faiblesse actuelle : brutal et direct, sans langage corporate. "
        "Personnalisé à partir de ce qu’elle a décrit (situation, blocage, métriques). "
        "Champ summary : 2 à 3 phrases en français, tutoiement obligatoire. "
        "Résumé brutal et direct de la situation réelle de la personne et de ce qui la bloque vraiment, "
        "en t’appuyant sur ce qu’elle a écrit (situation + blocage + chiffres si utiles). Pas de langage corporate. "
        "Règles de fond : exactement 3 objets dans issues. Chaque actions contient AU MINIMUM 2 chaînes. "
        "Ton brutal et direct : tu dis la vérité comme un mentor qui ne te ménage pas. "
        "Zéro langage corporate, zéro adoucissement, zéro formules creuses du type « il serait bon de », "
        "« pourrait être intéressant », « synergies », « optimiser », « valoriser » sans fait concret. "
        "Sois précis et actionnable : pas de conseils génériques qui s’appliquent à tout le monde. "
        "Chaque action doit être faisable AUJOURD’HUI, en MOINS D’UNE HEURE, avec un verbe d’action et un résultat vérifiable "
        "(ex. message envoyé, liste écrite, chiffre noté, appel passé). "
        "Dans CHAQUE issue, tu DOIS reprendre MOT POUR MOT au moins un extrait court (quelques mots) tiré du champ « situation » "
        "ET au moins un extrait court tiré du champ « blocage principal » dans le title ou dans une des actions uniquement "
        "(jamais dans impact — voir règle ci-dessous). "
        "pour prouver que tu t’appuies sur ce qui a été écrit. "
        "Never copy the user's exact words in the impact field. Always reformulate in your own words using 'tu'. Never use 'je' in any field. "
        + metrics_hint
        + "Tout le texte du JSON (hors clés) est en français. "
        "IMPORTANT: Return only valid JSON. No trailing commas. No text outside JSON."
    )

    blocks: list[str] = [
        f"1) Ta situation (texte exact à citer) :\n{situation}\n\n",
        f"2) Revenus mensuels (euros) : {revenue}\n\n",
        f"3) Ton offre (promesse en une phrase) :\n{user_offer}\n\n",
    ]
    n = 4
    if has_prospects:
        blocks.append(f"{n}) Prospects par semaine : {prospects_per_week}\n\n")
        n += 1
    if has_closing:
        blocks.append(f"{n}) Taux de closing (0-100 %) : {closing_rate}\n\n")
        n += 1
    blocks.append(f"{n}) Ton blocage principal (texte exact à citer) :\n{main_blocker}\n\n")

    user_payload = (
        "Voici les données saisies (tu t’en sers pour être ultra spécifique) :\n\n"
        + "".join(blocks)
        + "Calcule un score global 0-100 cohérent avec ce contexte et les chiffres effectivement fournis ci-dessus. "
        "Rédige summary, strength, weakness, puis 3 issues prioritaires : tutoie partout, sois sans filtre, "
        "et chaque action doit tenir en moins d’une heure aujourd’hui."
    )

    try:
        from groq import Groq

        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.35,
            max_tokens=4096,
        )
        raw_text = (completion.choices[0].message.content or "").strip()
        parsed = extract_json_from_groq_response(raw_text)
        score = int(parsed.get("score", 0))
        score = max(0, min(100, score))
        issues = _normalize_issues(parsed.get("issues"))
        summary = str(parsed.get("summary", "") or "").strip()
        if not summary:
            summary = (
                "Résumé absent de la réponse : complète mieux ta situation et ton blocage au prochain diagnostic "
                "pour qu’on puisse te cadrer sans détour."
            )
        strength = str(parsed.get("strength", "") or "").strip()
        if not strength:
            strength = (
                "Force non renvoyée par le modèle : au prochain diagnostic, détaille un peu plus ce qui fonctionne déjà chez toi."
            )
        weakness = str(parsed.get("weakness", "") or "").strip()
        if not weakness:
            weakness = (
                "Faiblesse non renvoyée par le modèle : précise davantage ton blocage pour qu’on puisse te challenger directement."
            )
        return {
            "score": score,
            "issues": issues,
            "summary": summary,
            "strength": strength,
            "weakness": weakness,
        }
    except Exception as exc:
        return _fallback_result(f"Erreur Groq ou JSON invalide : {exc!s}")
