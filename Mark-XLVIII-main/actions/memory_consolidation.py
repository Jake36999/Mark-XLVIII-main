"""Detect and consolidate vault memory: promote, merge, archive, flag.

The vault only ever grows. This module finds notes that have gone stale, that
duplicate each other, or that are ready to graduate from the short-term working
set into durable long-term knowledge — then (in later tasks) emits a reviewable
proposal and, on approval, applies it.

Detection is strictly read-only and bounded. Nothing here writes to a note; the
proposal and apply steps live alongside and are gated behind user review, matching
the plan/approval pattern used everywhere else in MARK.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from actions import jarvis_memory as jm

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(str(text or "").lower()))


def _similarity(a: set[str], b: set[str]) -> float:
    """Jaccard token overlap — a real 0..1 similarity the threshold applies to."""
    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0

EMPTY = {"stale": [], "duplicate": [], "promotable": [], "contradiction": []}


def _parse_iso(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def _all_notes(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Every indexed note as a flat record. Read-only."""
    if not jm.local_index_path(cfg).exists():
        jm.reindex_local(cfg)
    conn = jm._connect_index(cfg)
    try:
        rows = conn.execute(
            "SELECT id,path,title,type,updated,project_id,content_hash,"
            "review_after,supersedes,body,metadata_json FROM notes"
        ).fetchall()
    finally:
        conn.close()
    notes: list[dict[str, Any]] = []
    for row in rows:
        metadata = json.loads(row["metadata_json"] or "{}") if "metadata_json" in row.keys() else {}
        path = row["path"]
        title = row["title"] or ""
        notes.append(
            {
                "id": row["id"],
                "path": path,
                "title": title,
                "type": row["type"] or "",
                "updated": row["updated"] or "",
                "updated_ts": _parse_iso(row["updated"]),
                "project_id": row["project_id"] or "",
                "content_hash": row["content_hash"] or "",
                "review_after": row["review_after"] or metadata.get("review_after") or "",
                "snapshot_hash": str(metadata.get("snapshot_hash") or ""),
                "project_root": str(metadata.get("project_root") or ""),
                "lifecycle": jm.note_tier(metadata, path, cfg),
                "supersedes": metadata.get("supersedes") or [],
                "tokens": _tokens(f"{title} {row['body'] or ''}"),
            }
        )
    return notes


def _default_project(cfg: dict[str, Any]) -> str:
    return str(cfg.get("remember_project_id") or "")


def _snapshot_drifted(note: dict[str, Any], cache: dict[str, str]) -> bool:
    """True when a repository-derived note's source no longer matches its snapshot.

    This is the real drift check behind the project_operator false-fact case: the
    note stored the repo snapshot it was learned from; if the current repo hashes
    differently, its claims may no longer hold. Bounded — one inventory per root,
    cached across the run — and fails safe (no drift claimed if the repo is gone).
    """
    root = note["project_root"]
    stored = note["snapshot_hash"]
    if not root or not stored:
        return False
    if root not in cache:
        try:
            from actions.project_learning import inventory_repository

            inv = inventory_repository(root, max_inventory_files=5000)
            cache[root] = str(inv.get("snapshot_hash") or "") if inv.get("ok") else ""
        except Exception:
            cache[root] = ""
    current = cache[root]
    return bool(current) and current != stored


def detect_candidates(cfg: dict[str, Any] | None = None, *, now: float | None = None) -> dict[str, Any]:
    """Find consolidation candidates over the index. Read-only, bounded.

    Categories:
      * stale        — review_after has passed, or a snapshot-bound note has aged
                       (its source may have moved; the project_operator case).
      * duplicate    — near-identical notes within a project.
      * promotable   — aged short-term notes tied to a project, ready for long-term.
      * contradiction— near-duplicates that disagree (different content, one newer).
    """
    cfg = jm.resolve_config(cfg)
    if not cfg.get("memory_consolidation_enabled"):
        return {"ok": False, "reason": "consolidation_disabled", **EMPTY}

    now = time.time() if now is None else float(now)
    cap = int(cfg["memory_consolidation_max_candidates"])
    age_seconds = int(cfg["memory_short_term_age_days"]) * 86400
    review_seconds = int(cfg["memory_review_default_days"]) * 86400
    threshold = float(cfg["memory_consolidation_similarity_threshold"])
    default_project = _default_project(cfg)

    notes = _all_notes(cfg)
    stale: list[dict[str, Any]] = []
    promotable: list[dict[str, Any]] = []
    snapshot_cache: dict[str, str] = {}
    check_drift = bool(cfg.get("memory_consolidation_check_snapshot_drift", True))

    for note in notes:
        if note["lifecycle"] == "archive":
            continue
        review_ts = _parse_iso(note["review_after"])
        if review_ts is not None and review_ts < now:
            stale.append({"path": note["path"], "title": note["title"],
                          "reason": "review_after has passed", "suggested": "archive"})
        elif check_drift and _snapshot_drifted(note, snapshot_cache):
            # The source changed — the note needs re-verification, not removal.
            stale.append({
                "path": note["path"], "title": note["title"], "suggested": "review",
                "reason": "source repository snapshot has drifted; this note's claims may be stale — re-learn or verify",
            })
        elif note["snapshot_hash"] and note["updated_ts"] is not None and (now - note["updated_ts"]) > review_seconds:
            stale.append({
                "path": note["path"], "title": note["title"], "suggested": "review",
                "reason": "snapshot-bound note has aged; its source may have moved — verify against source",
            })

        if (
            note["lifecycle"] == "short_term"
            and note["project_id"]
            and note["project_id"] != default_project
            and note["updated_ts"] is not None
            and (now - note["updated_ts"]) > age_seconds
        ):
            promotable.append({"path": note["path"], "title": note["title"], "project_id": note["project_id"]})

    duplicate, contradiction = _detect_duplicates(cfg, notes, threshold, default_project)

    return {
        "ok": True,
        "stale": stale[:cap],
        "duplicate": duplicate[:cap],
        "promotable": promotable[:cap],
        "contradiction": contradiction[:cap],
        "counts": {
            "stale": len(stale), "duplicate": len(duplicate),
            "promotable": len(promotable), "contradiction": len(contradiction),
        },
        "capped_at": cap,
    }


def _actions_from_candidates(candidates: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten detection categories into a single ordered action list."""
    actions: list[dict[str, Any]] = []
    for item in candidates.get("promotable", []):
        actions.append({"kind": "promote", "path": item["path"], "title": item["title"],
                        "project_id": item.get("project_id", ""),
                        "why": "Aged short-term note tied to a project; graduate to long-term."})
    for item in candidates.get("duplicate", []):
        actions.append({"kind": "merge", "path": item["path"], "title": item["title"],
                        "into": item["duplicate_of"], "into_title": item["duplicate_of_title"],
                        "score": item["score"],
                        "why": f"Near-identical to a newer note (similarity {item['score']})."})
    for item in candidates.get("stale", []):
        # Drift/aged notes are flagged in place for re-learning; only notes whose
        # explicit review date has passed are archived.
        kind = "archive" if item.get("suggested") == "archive" else "review_stale"
        actions.append({"kind": kind, "path": item["path"], "title": item["title"],
                        "why": item["reason"]})
    for item in candidates.get("contradiction", []):
        actions.append({"kind": "flag", "path": item["path"], "title": item["title"],
                        "conflicts_with": item["duplicate_of"], "score": item["score"],
                        "why": "Near-duplicate within a project but the content disagrees; needs a human decision."})
    return actions


_CALLOUT_KIND = {"promote": "success", "merge": "abstract", "archive": "warning",
                 "flag": "danger", "review_stale": "question"}


def propose(cfg: dict[str, Any] | None = None, *, now: float | None = None) -> dict[str, Any]:
    """Write a reviewable consolidation proposal. Modifies no canonical note.

    This is the "distrust the model" gate: detection is turned into a single
    Consolidations/ note the user reads and approves before anything moves. Each
    action is a collapsible callout embedding the affected note.
    """
    from actions import obsidian_render as obs

    cfg = jm.resolve_config(cfg)
    candidates = detect_candidates(cfg, now=now)
    if not candidates["ok"]:
        return {"ok": False, "reason": candidates.get("reason"), "actions": [], "path": ""}

    actions = _actions_from_candidates(candidates)
    if not actions:
        return {"ok": True, "actions": [], "path": "", "message": "Nothing to consolidate."}

    root = Path(cfg["notes_root"])
    blocks = [
        obs.callout(
            "info", "Memory consolidation proposal",
            f"{len(actions)} proposed action(s). Nothing has moved yet — approve to apply. "
            "Every action is Reversible: archives are moves, not deletions, and supersession is recorded.",
        ),
        "",
    ]
    for index, action in enumerate(actions, 1):
        stem = Path(action["path"]).stem
        detail_lines = [f"**Action:** {action['kind']}", f"**Note:** `{action['path']}`", action["why"]]
        if action.get("into"):
            detail_lines.append(f"**Merge into:** `{action['into']}`")
        if action.get("conflicts_with"):
            detail_lines.append(f"**Conflicts with:** `{action['conflicts_with']}`")
        detail_lines.append("**Reversible:** yes — no note is deleted.")
        detail_lines.append("")
        detail_lines.append(obs.embed(stem))
        block = obs.callout(
            _CALLOUT_KIND.get(action["kind"], "note"),
            f"{index}. {action['kind'].title()} — {action['title']}",
            "\n".join(detail_lines),
            collapsed=True,
        )
        blocks.append(block)
        blocks.append("")

    title = "Consolidation Proposal"
    body = f"# {title}\n\n" + "\n".join(blocks).rstrip() + "\n"
    note = jm.create_note(
        note_type="memory", title=title, content=body, content_mode="full_body",
        cfg=cfg, sync=False, reindex=True,
        metadata_extra={
            "type": "consolidation_proposal", "rag_index": False, "lifecycle": "short_term",
            "consolidation_actions": actions,
        },
        path=root / "Consolidations" / f"{jm._now()[:10]}-consolidation-proposal.md",
    )
    return {"ok": True, "actions": actions, "path": note["path"], "counts": candidates["counts"]}


def _archive_dir(note_type: str, cfg: dict[str, Any]) -> Path:
    return jm.tier_root("archive", note_type or "memory", cfg)


def apply_action(action: dict[str, Any], *, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply one consolidation action. Reversible, idempotent, link-safe.

    Never deletes: archiving is a move, merging archives the folded source, and a
    flag only records the contradiction. Re-applying a completed action is a no-op.
    """
    from actions import obsidian_render as obs

    cfg = jm.resolve_config(cfg)
    kind = str(action.get("kind") or "").strip().lower()
    src = Path(str(action.get("path") or ""))

    if kind in {"archive", "promote", "merge"} and not src.exists():
        # The source is already gone — this action was applied before.
        return {"ok": True, "already_applied": True, "kind": kind, "path": str(src)}

    if kind == "archive":
        note_type = jm.read_note(src)[0].get("type") if src.exists() else "memory"
        moved = jm.move_note(src, _archive_dir(note_type, cfg), cfg=cfg, lifecycle="archive")
        return {"ok": moved["ok"], "kind": "archive", "path": moved.get("path", str(src)), **({} if moved["ok"] else {"error": moved.get("error")})}

    if kind == "promote":
        meta, body, _ = jm.read_note(src)
        project = str(action.get("project_id") or meta.get("project_id") or "project")
        long_dir = jm.tier_root("long_term", meta.get("type") or "memory", cfg) / jm._slug(project, "project")
        title = str(action.get("title") or meta.get("title") or "Consolidated Note")
        distilled = (
            obs.callout("summary", f"Promoted from short-term on {jm._now()[:10]}",
                        f"Source: `{src}` (now archived). Original detail is transcluded below.")
            + "\n\n"
            + obs.embed(src.stem)
            + "\n"
        )
        long_note = jm.create_note(
            note_type="memory", title=title, content=f"# {title}\n\n{distilled}",
            content_mode="full_body", cfg=cfg, sync=False, reindex=True,
            metadata_extra={"lifecycle": "long_term", "project_id": project, "supersedes": [src.stem]},
            path=long_dir / f"{jm._slug(title, 'note')}.md",
        )
        archived = jm.move_note(src, _archive_dir(meta.get("type") or "memory", cfg), cfg=cfg, lifecycle="archive")
        return {"ok": True, "kind": "promote", "long_term_path": long_note["path"], "path": archived.get("path", str(src))}

    if kind == "merge":
        survivor = Path(str(action.get("into") or ""))
        if not survivor.exists():
            return {"ok": False, "error": f"Merge survivor not found: {survivor}"}
        # Fold a transclusion of the source into the survivor, then archive source.
        jm.update_section(
            survivor, "## Merged Notes",
            f"{obs.wikilink(src.stem)} (merged {jm._now()[:10]}):\n\n{obs.embed(src.stem)}",
            mode="append", cfg=cfg,
        )
        note_type = jm.read_note(src)[0].get("type") if src.exists() else "memory"
        archived = jm.move_note(src, _archive_dir(note_type, cfg), cfg=cfg, lifecycle="archive")
        return {"ok": True, "kind": "merge", "path": archived.get("path", str(src)), "into": str(survivor)}

    if kind == "review_stale":
        # Non-destructive: mark the note for re-verification in place. Nothing moves.
        if not src.exists():
            return {"ok": True, "already_applied": True, "kind": kind, "path": str(src)}
        jm.update_section(
            src, "## Staleness Review",
            obs.callout("question", "Flagged for re-verification",
                        f"{action.get('why', 'This note may be stale.')} "
                        "Re-learn the source or confirm the note still holds; nothing has been changed."),
            mode="replace", cfg=cfg,
        )
        jm.update_note_frontmatter(src, {"review_after": jm._now()})
        return {"ok": True, "kind": "review_stale", "path": str(src)}

    if kind == "flag":
        conflicts = str(action.get("conflicts_with") or "")
        meta, _, _ = jm.read_note(src)
        existing = list(meta.get("contradicts") or [])
        if conflicts and conflicts not in existing:
            existing.append(conflicts)
        jm.update_note_frontmatter(src, {"contradicts": existing})
        jm.update_section(
            src, "## Contradiction",
            obs.callout("danger", "Unresolved contradiction",
                        f"This note conflicts with `{conflicts}`. A human decision is needed; "
                        "neither has been changed."),
            mode="replace", cfg=cfg,
        )
        return {"ok": True, "kind": "flag", "path": str(src), "conflicts_with": conflicts}

    return {"ok": False, "error": f"Unknown consolidation action: {kind}"}


def apply_proposal(proposal_path: str | Path, *, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply every action recorded in an approved proposal note."""
    cfg = jm.resolve_config(cfg)
    meta, _, _ = jm.read_note(Path(proposal_path))
    actions = meta.get("consolidation_actions") or []
    results = [apply_action(action, cfg=cfg) for action in actions]
    applied = sum(1 for r in results if r.get("ok"))
    return {"ok": all(r.get("ok") for r in results), "applied": applied, "results": results}


def _detect_duplicates(
    cfg: dict[str, Any], notes: list[dict[str, Any]], threshold: float, default_project: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pair near-identical notes by token overlap.

    The threshold is a real Jaccard similarity, so `0.82` means "nearly the same
    words". A same-project pair that is near-identical *but has different content*
    (one was edited) is surfaced as a contradiction to review, never auto-merged.
    """
    duplicate: list[dict[str, Any]] = []
    contradiction: list[dict[str, Any]] = []
    live = [n for n in notes if n["lifecycle"] != "archive" and n["tokens"]]

    for i, note in enumerate(live):
        for other in live[i + 1:]:
            score = _similarity(note["tokens"], other["tokens"])
            if score < threshold:
                continue
            # Keep the newer note as the survivor, the older as the duplicate.
            newer, older = note, other
            if (note["updated_ts"] or 0) < (other["updated_ts"] or 0):
                newer, older = other, note
            record = {
                "path": older["path"], "title": older["title"],
                "duplicate_of": newer["path"], "duplicate_of_title": newer["title"],
                "score": round(score, 4),
            }
            # A contradiction needs an explicit shared project; two notes in the
            # default catch-all project are just duplicates.
            same_project = (
                note["project_id"]
                and note["project_id"] != default_project
                and note["project_id"] == other["project_id"]
            )
            if same_project and note["content_hash"] != other["content_hash"]:
                contradiction.append(record)
            else:
                duplicate.append(record)
    return duplicate, contradiction


def memory_consolidation(
    parameters: dict[str, Any] | None = None,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    """Tool facade: detect | propose | apply."""
    params = dict(parameters or {})
    cfg = jm.resolve_config(params.pop("_config", None))
    operation = str(params.get("operation") or "propose").strip().lower()
    try:
        if operation in {"detect", "candidates", "what_is_stale"}:
            result = detect_candidates(cfg)
        elif operation == "propose":
            result = propose(cfg)
        elif operation in {"apply", "apply_proposal"}:
            target = str(params.get("path") or params.get("proposal") or "")
            if not target:
                result = {"ok": False, "error": "A proposal path is required to apply."}
            else:
                result = apply_proposal(target, cfg=cfg)
        else:
            result = {"ok": False, "error": f"Unknown memory_consolidation operation: {operation}"}
    except Exception as exc:
        result = {"ok": False, "operation": operation, "error": str(exc)}
    return json.dumps(result, ensure_ascii=True, indent=2)
