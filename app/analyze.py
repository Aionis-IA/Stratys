"""Diagnostic Stratys — analyse via Groq (JSON structuré)."""

from __future__ import annotations

import copy
import hashlib
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


def _normalize_premium_issues(raw: Any) -> list[dict[str, Any]]:
    """Garantit 5 issues avec title, impact, actions (exactement 3 chaînes)."""
    if not isinstance(raw, list):
        raw = []
    out: list[dict[str, Any]] = []
    for item in raw[:5]:
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
        while len(actions_list) < 3:
            actions_list.append(
                "Aujourd’hui : note une action concrète datée (heure + livrable) liée à ce que tu as décrit."
            )
        out.append({"title": title, "impact": impact, "actions": actions_list[:3]})

    fallback5 = [
        {
            "title": "Ton diagnostic n’a pas pu être complété proprement.",
            "impact": "Reviens avec plus de détail ou réessaie dans un instant.",
            "actions": [
                "Aujourd’hui : reprends le formulaire et cite des chiffres et faits précis (revenus, défis, ressources).",
                "Aujourd’hui : vérifie que GROQ_API_KEY est bien défini dans ton environnement.",
                "Aujourd’hui : raccourcis un champ si le JSON Groq a échoué (blocs trop longs).",
            ],
        },
        {
            "title": "Sans données précises, tu navigues à l’aveugle.",
            "impact": "Le business se joue sur des faits, pas sur des intentions.",
            "actions": [
                "Aujourd’hui : écris 3 métriques hebdo à suivre (prospects, closes, trésorerie).",
                "Aujourd’hui : choisis UNE offre cible (produit + niche) en une phrase.",
                "Aujourd’hui : bloque 45 min pour fixer l’ordre d’exécution (sans outil).",
            ],
        },
        {
            "title": "Défis : tu en listes 3, mais tu n’en traites aucun vraiment.",
            "impact": "Éparpillement = stagnation. Un axe à la fois, avec date.",
            "actions": [
                "Aujourd’hui : prends TON défis n°1 et le critère d’accomplissement pour vendredi 18h.",
                "Aujourd’hui : dis non à 2 tâches non critiques cette semaine.",
                "Aujourd’hui : envoie 5 messages ciblés sur ton ICP, pas 50 au hasard.",
            ],
        },
        {
            "title": "Ressources floues = pas d’exécution crédible.",
            "impact": "Sans budget, temps, compétence nommés, le plan tient en l’air.",
            "actions": [
                "Aujourd’hui : écris le nombre d’h/semaine réaliste pour toi (pas idéal) sur 4 semaines.",
                "Aujourd’hui : mets chiffré (ou 0) le budget OPEX prochain mois sur ta priorité 1.",
                "Aujourd’hui : choisis 1 ressource externe (outil ou freelance) pour le goulot, pas 5.",
            ],
        },
        {
            "title": "Objectif 12 mois sans jalon, c’est de la fumée.",
            "impact": "Sans jalon, tu ne sauras pas quand t’arrêter de pivoter par peur.",
            "actions": [
                "Aujourd’hui : mets 3 jalons (date + chiffre) sur les 3 prochains mois.",
                "Aujourd’hui : l’écart entre ici et 12 mois : une seule cause racine en une phrase.",
                "Aujourd’hui : un rendez-vous (toi ou pro) d’une heure le plus tôt possible pour cadrer.",
            ],
        },
    ]
    for f in fallback5:
        if len(out) >= 5:
            break
        out.append(f)
    return out[:5]


def _truthy_option(value: Any) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    s = str(value).strip().lower()
    return s in ("1", "true", "on", "oui", "yes", "o")


def _premium_options_from_data(data: dict) -> dict[str, bool]:
    flags = {
        "clarte": _truthy_option(data.get("opt_clarte")),
        "arch": _truthy_option(data.get("opt_arch")),
        "pivot": _truthy_option(data.get("opt_pivot")) or _truthy_option(data.get("option3")),
        "roadmap": _truthy_option(data.get("opt_roadmap")) or _truthy_option(data.get("option4")),
    }
    ex = data.get("selected_options")
    if isinstance(ex, (list, tuple, set)) and ex:
        s = {str(x).strip().lower() for x in ex}
        sel = {
            "clarte": "clarte" in s or "opt1" in s or "opt_clarte" in s,
            "arch": "arch" in s or "opt2" in s or "opt_arch" in s,
            "pivot": "pivot" in s or "opt3" in s or "opt_pivot" in s or "option3" in s,
            "roadmap": "roadmap" in s or "opt4" in s or "opt_roadmap" in s or "option4" in s,
        }
        return {k: flags[k] or sel[k] for k in flags}
    return flags


def _normalize_angles_morts_three(raw: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if isinstance(raw, list):
        for x in raw[:3]:
            if isinstance(x, dict):
                t = str(x.get("title", "") or "").strip() or "Angle mort"
                e = str(x.get("explanation", "") or "").strip() or "—"
                out.append({"title": t, "explanation": e})
    while len(out) < 3:
        out.append(
            {
                "title": "Donnée manquante",
                "explanation": "Le modèle n’a pas renvoyé trois angles. Relance le diagnostic ou raccourcis le contexte.",
            }
        )
    return out[:3]


def _normalize_blind_spots_premium(raw: Any) -> list[dict[str, str]]:
    """
    Deux angles morts : chacun a un titre + une explication 2-3 phrases (brutale, spécifique).
    Rétrocompat : si l’ancien format renvoie 2 chaînes, on les bascule en explication.
    """
    out: list[dict[str, str]] = []

    def one_pair(title: str, explanation: str) -> dict[str, str]:
        t = str(title or "").strip() or "Angle mort"
        e = str(explanation or "").strip()
        if not e or len(e) < 100:
            e = (
                "Personne ne te le dira à voix haute, mais c’est cohérent avec ce que tu as décrit : "
                "ton activité a besoin d’une décision de rejet, pas d’une nouvelle idée. "
                "Tant que tu fuis le chiffre et la confrontation client, tu répéteras le même trimestre."
            )
        return {"title": t, "explanation": e}

    if isinstance(raw, list):
        for x in raw[:2]:
            if isinstance(x, dict):
                t = str(x.get("title", x.get("titre", "")) or "").strip()
                e = str(x.get("explanation", x.get("detail", x.get("texte", ""))) or "").strip()
                out.append(one_pair(t, e))
            elif str(x).strip():
                s = str(x).strip()
                out.append(
                    one_pair(
                        "Ce que tu ne veux pas voir",
                        s
                        if len(s) >= 100
                        else f"{s} C’est le genre de fuite que tu ne nommes jamais en réunion, "
                        f"sauf que c’est exactement ce qui t’empêche d’arbitrer. En restant flou, tu protèges "
                        f"ton confort, pas ton CA, et ton équipe s’en accommode parce qu’on n’aime pas se faire huer.",
                    )
                )
    elif isinstance(raw, str) and raw.strip():
        parts = [p.strip() for p in re.split(r"[\n•]+", raw) if p.strip()]
        for p in parts[:2]:
            out.append(one_pair("Blind spot", p))

    while len(out) < 2:
        out.append(
            one_pair(
                "L’aveugle volontaire",
                "Tu n’as pas de critère d’abandon explicite : tant que l’espoir reste, tu acceptes n’importe quelle "
                "activité et tu t’en vantes comme de la souplesse. En réalité, tu ne payes le prix d’aucune décision : "
                "ni couper un client, ni doubler le prix, ni cesser une idée. C’est le point commun des plateaux moyens.",
            )
        )
    return out[:2]


def _fallback_result(reason: str) -> dict[str, Any]:
    return {
        "score": 0,
        "summary": (
            "Le diagnostic n’a pas pu aboutir : corrige le point ci-dessous et relance. "
            "Sans réponse valide de l’API, on ne peut pas te résumer ta situation correctement."
        ),
        "strength": "On n’a pas pu analyser tes points forts tant que le diagnostic ne fonctionne pas.",
        "weakness": "On n’a pas pu analyser tes points faibles tant que le diagnostic ne fonctionne pas.",
        "potentiel_croissance": "",
        "risque_principal": "",
        "intention_lancement": False,
        "etapes_lancement": None,
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
        "Tu es un conseiller business orienté P&L et croissance pour freelances / petites structures qui vendent une offre. "
        "Ce n’est PAS un bilan de carrière salarié : tu parles acquisition, offre, prix, pipeline, risque cash, traction. "
        "Tu parles à la personne au TU partout : jamais de vouvoiement, jamais de « vous », même dans title, impact et actions. "
        "Tu réponds UNIQUEMENT avec un objet JSON valide UTF-8, sans texte avant ou après, sans markdown. "
        "Le JSON doit avoir exactement cette structure :\n"
        '{"summary": "<string>", "strength": "<string>", "weakness": "<string>", '
        '"potentiel_croissance": "<string>", "risque_principal": "<string>", '
        '"score": <entier 0 à 100>, "issues": [\n'
        '  {"title": "...", "impact": "...", "actions": ["...", "..."]},\n'
        '  {"title": "...", "impact": "...", "actions": ["...", "..."]},\n'
        '  {"title": "...", "impact": "...", "actions": ["...", "..."]}\n'
        "]}\n"
        + metrics_rules
        + "Champ potentiel_croissance : 2 à 4 phrases en français — estimation brutalement honnête : "
        "est-ce que ce business a une vraie marge de croissance compte tenu des données (revenus, offre, prospection, closing) ? "
        "Pas de langue de bois : dis si c’est du plafond de verre, du marché saturé, ou au contraire du levier réel. "
        "Champ risque_principal : 1 à 2 phrases en français — le risque business le plus dangereux MAINTENANT "
        "(trésorerie, dépendance à un client, offre floue, pas de prospection, etc.), tiré des faits fournis. "
        "Champ strength : UNE phrase — force business concrète (offre, réputation, délivrabilité…), pas psychologie de bureau. "
        "Champ weakness : UNE phrase — faiblesse qui fait mal au CA ou à la croissance. "
        "Champ summary : 2 à 3 phrases — synthèse sans filtre de la santé économique de l’activité et du vrai goulot. "
        "Règles : exactement 3 issues ; chaque actions contient AU MINIMUM 2 chaînes ; actions business (offre, prix, prospection, closing, suivi). "
        "Brutal et direct : pas de coaching « bien-être », pas de reconversion salariée — reste sur l’argent, les clients et l’exécution. "
        "Zéro langage corporate creux. Chaque action faisable AUJOURD’HUI en moins d’une heure avec résultat vérifiable. "
        "Dans CHAQUE issue, reprends au moins un court extrait du champ « situation » et du « blocage principal » "
        "dans le title ou une action (jamais dans impact), mot pour mot pour prouver que tu t’appuies sur les textes. "
        "Never copy the user's exact words in the impact field. Reformulate with 'tu'. Never use 'je' in any field. "
        + metrics_hint
        + "Tout le texte du JSON (hors clés) est en français. "
        "Ne jamais copier les mots exacts de l'utilisateur entre guillemets dans les titres ou impacts. "
        "Toujours reformuler avec tes propres mots. "
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
        "Voici les données business saisies (tu t’en sers pour juger traction, risque et levier) :\n\n"
        + "".join(blocks)
        + "Calcule un score global 0-100 cohérent avec ce contexte. "
        "Rédige summary, strength, weakness, potentiel_croissance, risque_principal, puis 3 issues prioritaires "
        "100 % orientées croissance et rentabilité : tutoie partout, sans filtre, chaque action en moins d’une heure."
    )
    _payload_utf8 = user_payload.encode("utf-8")
    print(
        "[Stratys DEBUG] analyze_business Groq user message: sha256="
        + hashlib.sha256(_payload_utf8).hexdigest()
        + " len="
        + str(len(_payload_utf8)),
        flush=True,
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
        potentiel_croissance = str(parsed.get("potentiel_croissance", "") or "").strip()
        if not potentiel_croissance:
            potentiel_croissance = (
                "Potentiel non renvoyé par le modèle : précise tes chiffres et ton marché au prochain diagnostic."
            )
        risque_principal = str(parsed.get("risque_principal", "") or "").strip()
        if not risque_principal:
            risque_principal = (
                "Risque principal non isolé par le modèle : détaille ta trésorerie et ta dépendance clients."
            )
        return {
            "score": score,
            "issues": issues,
            "summary": summary,
            "strength": strength,
            "weakness": weakness,
            "potentiel_croissance": potentiel_croissance,
            "risque_principal": risque_principal,
            "intention_lancement": False,
            "etapes_lancement": None,
        }
    except Exception as exc:
        return _fallback_result(f"Erreur Groq ou JSON invalide : {exc!s}")


def _fallback_premium_result(reason: str, options: dict[str, bool] | None = None) -> dict[str, Any]:
    o = options or {k: False for k in ("clarte", "arch", "pivot", "roadmap")}
    r: dict[str, Any] = {
        "score": 0,
        "summary": (
            "Le diagnostic premium n’a pas abouti : corrige le point ci-dessous et relance. "
            "Sans réponse valide de l’API, on ne peut pas te serrer le ton comme prévu."
        ),
        "strength": "On n’a pas pu isoler une force crédible tant que le diagnostic ne répond pas.",
        "weakness": "On n’a pas pu cibler la faiblesse n°1 tant que l’appel modèle a échoué.",
        "issues": _normalize_premium_issues(
            [
                {
                    "title": "Diagnostic indisponible",
                    "impact": reason,
                    "actions": [
                        "Vérifie GROQ_API_KEY dans le fichier .env à la racine du projet.",
                        "Redémarre le serveur après modification du .env.",
                        "Relance en raccourcissant chaque zone de texte (moins d’environ 1500 caractères chacune).",
                    ],
                }
            ]
        ),
        "blind_spots": _normalize_blind_spots_premium([]),
        "message_direct": (
            "Tant que le moteur ne tourne pas, personne d’autre n’a besoin d’en dire plus : c’est toi qu’on attend au bout du fil, pas l’idée parfaite."
        ),
        "growth_potential": "Potentiel non évalué : relance dès que l’API répond pour une lecture cash et marché.",
        "main_risk": "Risque principal non chiffré : sans diagnostic valide, tu ne vois ni goulot de tréso, ni offre, ni exécution.",
        "opt_clarte": o.get("clarte", False),
        "opt_arch": o.get("arch", False),
        "opt_pivot": o.get("pivot", False),
        "opt_roadmap": o.get("roadmap", False),
        "clarte_section": "",
        "angles_morts": [],
        "architecture_section": "",
        "pivot_section": "",
        "roadmap_section": "",
    }
    if o.get("clarte"):
        r["clarte_section"] = f"Génération impossible : {reason}"
        r["angles_morts"] = _normalize_angles_morts_three([])
    if o.get("arch"):
        r["architecture_section"] = f"Génération impossible : {reason}"
    if o.get("pivot"):
        r["pivot_section"] = f"Génération impossible : {reason}"
    if o.get("roadmap"):
        r["roadmap_section"] = f"Génération impossible : {reason}"
    return r


def _strip_md_fence(text: str) -> str:
    """Retire un bloc ``` optionnel autour de la réponse modèle."""
    t = (text or "").strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _groq_premium_plain(api_key: str, system: str, user: str, max_out: int) -> str:
    """Appel Groq — réponse texte brut (modules options, pas de JSON)."""
    from groq import Groq

    client = Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.35,
        max_tokens=max_out,
    )
    raw = (completion.choices[0].message.content or "").strip()
    return _strip_md_fence(raw)


def _groq_premium_json(api_key: str, system: str, user: str, max_out: int) -> dict[str, Any]:
    """Un appel Groq ; réponse parse en JSON. max_out: limite de sortie (évite de saturer l’appel)."""
    from groq import Groq

    client = Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
        max_tokens=max_out,
    )
    raw = (completion.choices[0].message.content or "").strip()
    return extract_json_from_groq_response(raw)


def _premium_essential_user_payload(
    situation: str,
    revenue: int,
    user_offer: str,
    top_challenges: str,
    resources: str,
    goals_12m: str,
) -> str:
    """Seules données passées aux modules options (situation, revenus, offre, défis, ressources, objectifs)."""
    return (
        "Ne rien inventer hors de ces éléments.\n\n"
        f"Situation :\n{situation}\n\n"
        f"Revenus mensuels (€) :\n{revenue}\n\n"
        f"Offre :\n{user_offer}\n\n"
        f"Défis :\n{top_challenges}\n\n"
        f"Ressources :\n{resources}\n\n"
        f"Objectifs :\n{goals_12m}\n"
    )


def analyze_premium(data: dict) -> dict[str, Any]:
    """
    Diagnostic Entreprise Premium (Groq) : 1er appel = diagnostic de base ; appels séparés par option
    (évite de dépasser la limite de tokens sur un seul message).
    """
    options = _premium_options_from_data(data)
    print(
        "[Stratys DEBUG] analyze_premium — options effectives (Groq):",
        options,
        "| brut:",
        {
            "opt_clarte": data.get("opt_clarte"),
            "opt_arch": data.get("opt_arch"),
            "opt_pivot": data.get("opt_pivot"),
            "opt_roadmap": data.get("opt_roadmap"),
            "option3": data.get("option3"),
            "option4": data.get("option4"),
        },
        flush=True,
    )
    situation = str(data.get("situation", "") or "").strip()
    revenue = int(data.get("revenue", 0) or 0)
    user_offer = str(data.get("user_offer", "") or "").strip()
    top_challenges = str(data.get("top_challenges", "") or "").strip()
    resources = str(data.get("resources", "") or "").strip()
    goals_12m = str(data.get("goals_12m", "") or "").strip()

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return _fallback_premium_result("Clé API Groq absente (GROQ_API_KEY).", options)

    system_premium_base = (
        "Tu es le conseiller business le plus direct de Stratys — diagnostic PREMIUM pour entrepreneurs. "
        "Ce n’est pas du coaching bienveillant : c’est P&L, offre, exécution, angles morts, risque. "
        "Tu parles à la personne au TU partout (title, impact, actions, partout) : jamais de vouvoiement. "
        "Tu réponds UNIQUEMENT avec un objet JSON valide UTF-8, sans texte avant ou après, sans markdown. "
        "Structure OBLIGATOIRE (ce seul appel, sans champs d’options payantes) :\n"
        "{\n"
        '  "summary": "<2-3 phrases, brutalement honnête, sans ménage>",\n'
        '  "message_direct": "<UNE seule phrase, tutoiement, qui dit la vérité que personne ose : le vrai problème à la face. '
        "Sans point d’exclamation à rallonge. Style mentor qui t’arrache la camisole, pas d’insulte gratuite.>\",\n"
        '  "strength": "<une force business concrète>",\n'
        '  "weakness": "<une faiblesse n°1 côté CA, cash ou exécution>",\n'
        '  "score": <0-100 entier>,\n'
        '  "issues": [ exactement 5 objets { "title", "impact", "actions" : [3 chaînes] } ],\n'
        '  "blind_spots": [\n'
        '     { "title": "<titre court (3-8 mots)>", "explanation": "<2 à 3 phrases. '
        "Explique ce que l’entrepreneur NE VOIT pas : illusion, fuite, déni, cécité marché, biais, etc. "
        "Spécifique aux données, brutal.>\" },\n"
        "     (exactement 2 objets) ],\n"
        '  "growth_potential": "<2-4 phrases : levier ou plafond, sans filtre>",\n'
        '  "main_risk": "<1-2 phrases : pire scénario proche, factuel>"\n'
        "}\n"
        "ACTIONS (issues[].actions) — ZÉRO TOLÉRANCE : 3 actions par issue, 1 chaîne chacune, ultra-concrètes. "
        "Impératif 2e personne : Fais, Envoie, Appelle, Définis, Mets en place. Jamais « il faut », jamais « vous devez », jamais 3e personne. "
        "QUOI + COMMENT + QUAND (jour, heure, délai). Exemple de niveau requis : "
        "« Mardi 9h, envoie un email (objet explicite) à tes 3 clients les plus gros chiffres, pour proposer un entretien de 20 minutes avant le 30 du mois. » "
        "Interdit : « mettre en place un système », « structurer sa prospection », etc. sans date/canal. "
        "Dans chaque issue, ancre un morceau des champs (situation, défis, ressources, objectifs) dans le title ou une action, pas dans impact. "
        "Never copy the user's exact words in the impact field. Never use 'je' in any field. "
        "Angles morts (base) : 2-3 phrases par explanation. Tout le JSON (hors clés) en français, brutal, direct. "
        "JSON uniquement, pas de texte hors JSON."
    )
    user_base = (
        "Données premium :\n\n"
        f"1) Situation :\n{situation}\n\n"
        f"2) Revenus mensuels (€) : {revenue}\n\n"
        f"3) Offre :\n{user_offer}\n\n"
        f"4) Défis :\n{top_challenges}\n\n"
        f"5) Ressources :\n{resources}\n\n"
        f"6) Objectifs 12 mois :\n{goals_12m}\n\n"
        "Rédige uniquement le JSON du diagnostic de base (summary, message_direct, strength, weakness, score, 5 issues, 2 blind_spots, growth_potential, main_risk)."
    )

    try:
        parsed = _groq_premium_json(api_key, system_premium_base, user_base, max_out=8192)
    except Exception as exc:
        return _fallback_premium_result(f"Erreur Groq ou JSON invalide (diagnostic de base) : {exc!s}", options)

    score = int(parsed.get("score", 0))
    score = max(0, min(100, score))
    issues = _normalize_premium_issues(parsed.get("issues"))
    summary = str(parsed.get("summary", "") or "").strip()
    if not summary:
        summary = (
            "Résumé absent de la réponse : complète la situation, les défis et les ressources au prochain essai."
        )
    strength = str(parsed.get("strength", "") or "").strip()
    if not strength:
        strength = "Force non isolée : précise ce qui cloche déjà en ta faveur côté clients ou marge."
    weakness = str(parsed.get("weakness", "") or "").strip()
    if not weakness:
        weakness = "Faiblesse floue : le modèle a séché — explicite ton goulot d’acquisition ou de marge la prochaine fois."
    blind_spots = _normalize_blind_spots_premium(parsed.get("blind_spots"))
    growth_potential = str(parsed.get("growth_potential", "") or "").strip()
    if not growth_potential:
        growth_potential = "Potentiel non renvoyé : mets chiffres et marché au prochain diagnostic."
    main_risk = str(parsed.get("main_risk", "") or "").strip()
    if not main_risk:
        main_risk = "Risque principal flou : détaille tréso, dépendance et pipeline au prochain diagnostic."
    message_direct = str(parsed.get("message_direct", "") or "").strip()
    if not message_direct:
        message_direct = (
            "Tant qu’on te demande d’arrêter d’inventer des priorités, tu n’en choisis qu’une : fuir le chiffre."
        )

    ctx = _premium_essential_user_payload(
        situation, revenue, user_offer, top_challenges, resources, goals_12m
    )

    clarte_section = ""
    angles_morts: list[dict[str, str]] = []
    architecture_section = ""
    pivot_section = ""
    roadmap_section = ""

    _plain_suffix = (
        "Réponds UNIQUEMENT en texte brut en français, au tutoiement. "
        "Pas de JSON, pas de markdown (pas de ```), pas de préambule « bien sûr », pas de liste à puces générique si tu peux densifier en phrases."
    )

    if options["clarte"]:
        sys1 = (
            "Tu es un coach stratégique brutal et honnête. Analyse la différence réelle entre ce que cet entrepreneur dit vouloir "
            "et ce que ses actions révèlent vraiment. Identifie 3 angles morts NON ÉVIDENTS — pas ce qu'il sait déjà, mais ce qu'il ne voit absolument pas "
            "sur lui-même ou son business. Chaque angle mort doit commencer par « Tu penses que... En réalité... » et doit être une révélation, pas une confirmation. "
            "Sois chirurgical.\n\n"
            "Structure ta réponse ainsi : (A) un bloc dense « Ce que tu dis vouloir vs ce que tes faits montrent » ; "
            "(B) puis trois angles morts numérotés 1 à 3, chacun ouvrant obligatoirement par la formule « Tu penses que... En réalité... » et développé en plusieurs phrases.\n\n"
            + _plain_suffix
        )
        u1 = ctx + "\nRédige le module complet maintenant."
        try:
            clarte_section = _groq_premium_plain(api_key, sys1, u1, max_out=6144)
            angles_morts = []
            print("[Stratys DEBUG] analyze_premium — option 1 (clarté) caractères:", len(clarte_section), flush=True)
        except Exception:
            clarte_section = "Module indisponible (erreur API, quota ou format)."
            angles_morts = []

    if options["arch"]:
        sys2 = (
            "Tu es un architecte organisationnel. Analyse ce business comme un système avec des flux, des dépendances et des goulots d'étranglement. Décris:\n"
            "1) Le flux exact de valeur de l'entreprise (comment l'argent et la valeur circulent)\n"
            "2) Les 3 goulots d'étranglement qui bloquent le système\n"
            "3) La structure idéale avec qui fait quoi et comment les éléments s'interconnectent\n"
            "4) Les 2 changements systémiques qui débloquent tout le reste.\n"
            "Pas des conseils généraux — une architecture concrète.\n\n"
            + _plain_suffix
            + " Numérote les parties 1 à 4 clairement dans le texte."
        )
        u2 = ctx + "\nRédige l'architecture système complète maintenant."
        try:
            architecture_section = _groq_premium_plain(api_key, sys2, u2, max_out=6144)
            print("[Stratys DEBUG] analyze_premium — option 2 (architecture) caractères:", len(architecture_section), flush=True)
        except Exception:
            architecture_section = "Module indisponible (erreur API, quota ou format)."

    if options["pivot"]:
        sys3 = (
            "Tu es un conseiller de crise. Identifie:\n"
            "1) Ce qu'il faut arrêter IMMÉDIATEMENT avec une date précise et la raison brutale\n"
            "2) Ce vers quoi pivoter avec exactement pourquoi ce marché ou cette offre\n"
            "3) Les 3 étapes de transition concrètes pour ne pas perdre les revenus actuels pendant le pivot\n"
            "4) Le risque principal du pivot et comment le mitiger précisément.\n"
            "Sois brutal — un vrai pivot fait mal.\n\n"
            + _plain_suffix
            + " Numérote les parties 1 à 4 dans le texte."
        )
        u3 = ctx + "\nRédige la stratégie de pivot complète maintenant."
        try:
            pivot_section = _groq_premium_plain(api_key, sys3, u3, max_out=6144)
            print("[Stratys DEBUG] analyze_premium — option 3 (pivot) caractères:", len(pivot_section), flush=True)
        except Exception:
            pivot_section = "Module indisponible (erreur API, quota ou format)."

    if options["roadmap"]:
        sys4 = (
            "Tu es un directeur stratégique. Crée une roadmap sur 12 mois avec: Mois 1: action précise + métrique business mesurable "
            "(pas followers, mais revenus, clients, taux de conversion). Mois 2: etc. Chaque mois a UNE priorité principale, "
            "UNE métrique de succès chiffrée, et UN risque à surveiller. La roadmap doit être cohérente — chaque mois construit sur le précédent. "
            "Pas de généralités.\n\n"
            + _plain_suffix
            + " Une ligne ou un court paragraphe par mois, étiqueté Mois 1: … jusqu'à Mois 12: …."
        )
        u4 = ctx + "\nRédige la roadmap 12 mois maintenant."
        try:
            roadmap_section = _groq_premium_plain(api_key, sys4, u4, max_out=8192)
            print("[Stratys DEBUG] analyze_premium — option 4 (roadmap) caractères:", len(roadmap_section), flush=True)
        except Exception:
            roadmap_section = "Module indisponible (erreur API, quota ou format)."

    return {
        "score": score,
        "summary": summary,
        "message_direct": message_direct,
        "strength": strength,
        "weakness": weakness,
        "issues": issues,
        "blind_spots": blind_spots,
        "growth_potential": growth_potential,
        "main_risk": main_risk,
        "intention_lancement": False,
        "etapes_lancement": None,
        "potentiel_croissance": growth_potential,
        "risque_principal": main_risk,
        "opt_clarte": options["clarte"],
        "opt_arch": options["arch"],
        "opt_pivot": options["pivot"],
        "opt_roadmap": options["roadmap"],
        "clarte_section": clarte_section,
        "angles_morts": angles_morts,
        "architecture_section": architecture_section,
        "pivot_section": pivot_section,
        "roadmap_section": roadmap_section,
    }



