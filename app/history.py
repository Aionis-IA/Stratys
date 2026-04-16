"""Persistance et affichage de l'historique des diagnostics."""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.issue_followup import (
    evaluate_previous_issues_resolution,
    extract_three_issue_titles,
    titles_from_stored_issues,
)
from app.models import DiagnosticHistory


def save_diagnostic_history(
    db: Session, user_id: int, user_type_str: str, result: dict[str, Any]
) -> int:
    """Enregistre un diagnostic et met à jour le statut résolu/en cours du diagnostic précédent. Retourne l'id du nouvel enregistrement."""
    issues = result.get("issues")
    if not isinstance(issues, list):
        issues = []
    new_titles = extract_three_issue_titles(result)

    prev = (
        db.query(DiagnosticHistory)
        .filter(DiagnosticHistory.user_id == user_id)
        .order_by(desc(DiagnosticHistory.created_at))
        .first()
    )

    new_entry = DiagnosticHistory(
        user_id=user_id,
        user_type=user_type_str,
        score=int(result.get("score", 0)),
        summary=str(result.get("summary", "") or ""),
        strength=str(result.get("strength", "") or ""),
        weakness=str(result.get("weakness", "") or ""),
        issues=issues,
        issues_titles=new_titles,
        issues_resolved=[False, False, False],
        result_payload=copy.deepcopy(result),
    )
    db.add(new_entry)
    db.flush()
    new_id = int(new_entry.id)

    if prev is not None:
        prev_titles: list[str]
        raw_titles = prev.issues_titles
        if raw_titles is None or not isinstance(raw_titles, list):
            prev_titles = titles_from_stored_issues(prev.issues)
        else:
            prev_titles = [str(t or "—").strip() or "—" for t in raw_titles[:3]]
            while len(prev_titles) < 3:
                prev_titles.append("—")
            prev_titles = prev_titles[:3]

        resolved = evaluate_previous_issues_resolution(
            prev_titles, result, user_type_str
        )
        if resolved is not None and len(resolved) == 3:
            prev.issues_resolved = resolved
        if prev.issues_titles is None:
            prev.issues_titles = prev_titles

    db.commit()
    return new_id


def last_diagnostics_for_user(db: Session, user_id: int, limit: int = 5):
    return (
        db.query(DiagnosticHistory)
        .filter(DiagnosticHistory.user_id == user_id)
        .order_by(desc(DiagnosticHistory.created_at))
        .limit(limit)
        .all()
    )


def format_history_for_template(rows: list) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        raw_titles = r.issues_titles
        if raw_titles is None or not isinstance(raw_titles, list):
            titles = titles_from_stored_issues(r.issues)
        else:
            titles = [str(x or "—").strip() or "—" for x in raw_titles[:3]]
            while len(titles) < 3:
                titles.append("—")
            titles = titles[:3]

        raw_res = r.issues_resolved
        if not isinstance(raw_res, list) or len(raw_res) != 3:
            resolved_flags = [False, False, False]
        else:
            resolved_flags = []
            for i in range(3):
                v = raw_res[i] if i < len(raw_res) else False
                resolved_flags.append(
                    v is True or str(v).lower() in ("true", "1", "oui")
                )

        problems = [
            {"title": titles[i], "resolved": resolved_flags[i]} for i in range(3)
        ]

        resolved_count = sum(1 for f in resolved_flags if f)
        unresolved_titles = [titles[i] for i in range(3) if not resolved_flags[i]]
        if resolved_count == 3:
            smart_message = (
                "Excellent travail ! Tu as réglé tous tes blocages. "
                "Fais un nouveau diagnostic pour identifier tes prochains défis."
            )
        elif resolved_count == 2:
            u = unresolved_titles[0] if unresolved_titles else "—"
            smart_message = (
                f"Bonne progression ! Il te reste un blocage prioritaire : {u}."
            )
        elif resolved_count == 1:
            u = unresolved_titles[0] if unresolved_titles else "—"
            smart_message = (
                f"Tu avances. Concentre-toi maintenant sur : {u}."
            )
        else:
            u = titles[0] if titles else "—"
            smart_message = f"Ces blocages sont toujours présents. Priorise : {u}."

        dt = r.created_at
        label = dt.strftime("%d/%m/%Y %H:%M") if dt else "—"
        out.append(
            {
                "date_label": label,
                "score": r.score,
                "problems": problems,
                "smart_message": smart_message,
            }
        )
    return out
