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


def _clamp_int(value: Any, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = lo
    return max(lo, min(hi, n))


def analyze_business_particulier(data: dict) -> dict[str, Any]:
    """
    Diagnostic salarié / carrière : même format JSON que analyze_business.
    Détecte une intention de création d’activité et adapte les conseils ; sinon focus carrière employé.
    """
    situation = str(data.get("situation", "") or "").strip()
    net_salary = int(data.get("net_salary", 0) or 0)
    ambition = str(data.get("ambition", "") or "").strip()
    job_satisfaction = _clamp_int(data.get("job_satisfaction", 5), 0, 10)
    main_blocker = str(data.get("main_blocker", "") or "").strip()

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return _fallback_result("Clé API Groq absente (GROQ_API_KEY).")

    system_prompt = (
        "Tu es un mentor carrière brutal et direct pour salariés et particuliers en France. "
        "Tu parles à la personne au TU systématiquement : jamais de vouvoiement, jamais de « vous », "
        "même dans title, impact et actions. "
        "Tu réponds UNIQUEMENT avec un objet JSON valide UTF-8, sans texte avant ou après, sans markdown. "
        "Le JSON doit avoir exactement cette structure :\n"
        '{"summary": "<string>", "strength": "<string>", "weakness": "<string>", "score": <entier 0 à 100>, '
        '"intention_lancement": <true ou false>, "etapes_lancement": <null OU tableau de 3 chaînes>, "issues": [\n'
        '  {"title": "...", "impact": "...", "actions": ["...", "..."]},\n'
        '  {"title": "...", "impact": "...", "actions": ["...", "..."]},\n'
        '  {"title": "...", "impact": "...", "actions": ["...", "..."]}\n'
        "]}\n"
        "TRANSITION / LANCEMENT — règle stricte : mets intention_lancement à true uniquement si les textes montrent clairement "
        "une envie de travailler en indépendant, devenir freelance ou entrepreneur, créer une activité, monter une boîte, "
        "quitter ou quitterait son poste pour se lancer, ou tout signal équivalent (même implicite mais crédible). "
        "Si intention_lancement est true : etapes_lancement DOIT être un tableau de EXACTEMENT 3 chaînes, "
        "chacune = une première étape concrète et réaliste pour commencer comme entrepreneur (pas du bullshit). "
        "Si intention_lancement est false : etapes_lancement DOIT être null (pas de tableau vide). "
        "Ne mets jamais intention_lancement à true sur une simple frustration de bureau sans projet de sortie — il faut un signal de bascule. "
        "Chaque issue a EXACTEMENT 2 actions (exactement 2 chaînes dans actions), jamais 1, jamais 3 ou plus. "
        "Ne recopie jamais les formulations exactes de l’utilisateur, notamment les enchaînements du type « car j’ai peur… » "
        "ou les longues excuses : reformule toujours avec tes mots, en restant fidèle au fond. "
        "Dans le summary (et partout ailleurs) : tutoiement strict ; n’emploie jamais « à mon compte » ni aucune tournure qui "
        "mélange les personnes (je / tu) de façon incorrecte : parle-lui avec « tu » de façon cohérente. "
        "Contexte : la personne est surtout salariée ; ton rôle n’est pas celui d’un coach business P&L comme pour une entreprise. "
        "Si intention_lancement est false : concentre-toi sur la carrière employé (évolution, entretiens, compétences, "
        "politique interne, reconversion, négociation) avec salaire, satisfaction 0-10 et blocage. "
        "Si intention_lancement est true : garde aussi des issues utiles sur la transition, sans douceur inutile. "
        "Champ strength : UNE phrase en français — une force réelle tirée de ce qu’elle a écrit. "
        "Champ weakness : UNE phrase en français — le vrai point faible actuel, sans ménager. "
        "Champ summary : 2 à 3 phrases en français — résumé sans filtre de sa situation pro et de ce qui la bloque. "
        "Score 0-100 : cohérent avec satisfaction au travail, ambition, blocage et situation (salaire en contexte, pas en jugement moral). "
        "Exactement 3 issues ; chaque action faisable en moins d’une heure aujourd’hui. "
        "Never copy the user's exact words in the impact field. Reformulate with 'tu'. Never use 'je' in any field. "
        "Tout le texte du JSON (hors clés) est en français. "
        "Ne jamais copier les mots exacts de l'utilisateur entre guillemets dans les titres ou impacts. "
        "Toujours reformuler avec tes propres mots. "
        "IMPORTANT: Return only valid JSON. No trailing commas. No text outside JSON."
    )

    user_payload = (
        "Voici les données saisies :\n\n"
        f"1) Ta situation (poste, entreprise, carrière) :\n{situation}\n\n"
        f"2) Salaire mensuel net (euros) : {net_salary}\n\n"
        f"3) Ton ambition sur 12 mois :\n{ambition}\n\n"
        f"4) Satisfaction au travail (0 = pas du tout, 10 = très satisfait) : {job_satisfaction}\n\n"
        f"5) Ton blocage principal :\n{main_blocker}\n\n"
        "Détecte une intention de lancer une activité / devenir indépendant·e / quitter le salariat pour entreprendre. "
        "Remplis intention_lancement et etapes_lancement selon les règles. "
        "Rédige summary, strength, weakness, score, puis 3 issues avec recommandations adaptées (carrière et/ou transition)."
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
                "Résumé absent de la réponse : complète mieux ta situation et ton blocage au prochain diagnostic."
            )
        strength = str(parsed.get("strength", "") or "").strip()
        if not strength:
            strength = (
                "Force non renvoyée par le modèle : précise davantage ce qui fonctionne déjà pour toi au travail."
            )
        weakness = str(parsed.get("weakness", "") or "").strip()
        if not weakness:
            weakness = (
                "Faiblesse non renvoyée : détaille ton blocage pour un retour plus tranché."
            )
        raw_intention = parsed.get("intention_lancement")
        intention_lancement = raw_intention is True or (
            isinstance(raw_intention, str) and raw_intention.strip().lower() in ("true", "1", "oui")
        )
        etapes_raw = parsed.get("etapes_lancement")
        etapes_lancement: list[str] | None = None
        if intention_lancement:
            if isinstance(etapes_raw, list) and len(etapes_raw) > 0:
                etapes_lancement = [str(x).strip() for x in etapes_raw[:3] if str(x).strip()]
                while len(etapes_lancement) < 3:
                    etapes_lancement.append(
                        "Affine cette étape avec une action vérifiable d’ici demain (30 min max)."
                    )
            else:
                intention_lancement = False
                etapes_lancement = None

        return {
            "score": score,
            "issues": issues,
            "summary": summary,
            "strength": strength,
            "weakness": weakness,
            "intention_lancement": intention_lancement,
            "etapes_lancement": etapes_lancement,
            "potentiel_croissance": "",
            "risque_principal": "",
        }
    except Exception as exc:
        return _fallback_result(f"Erreur Groq ou JSON invalide : {exc!s}")
