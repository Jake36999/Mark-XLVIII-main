"""One-time, idempotent migration to the tiered memory model.

Backfills `memory_tier: short_term` (and the `#tier/short-term` tag) onto existing
notes that lack the field, and seeds an empty Map-of-Content per tier. It moves
nothing: existing notes stay exactly where they are, which is why re-running is
safe.

Supports Task B3 of docs/superpowers/plans/2026-07-22-mark-memory-consolidation-and-tiers.md.

Usage:
    python scripts/migrate-memory-tiers.py            # dry run
    python scripts/migrate-memory-tiers.py --apply    # write changes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from actions import jarvis_memory as jm
from actions import obsidian_render as obs

SKIP_TOP = {".obsidian", ".jarvis", "Templates"}


def _eligible(path: Path, root: Path) -> bool:
    parts = path.resolve().relative_to(root).parts
    return bool(parts) and parts[0] not in SKIP_TOP


def backfill(root: Path, cfg: dict, *, apply: bool) -> dict:
    changed, already, skipped = [], 0, 0
    for md in root.rglob("*.md"):
        if not _eligible(md, root):
            skipped += 1
            continue
        try:
            metadata, _, _ = jm.read_note(md)
        except Exception:
            skipped += 1
            continue
        if str(metadata.get("memory_tier") or "").strip():
            already += 1
            continue
        tier = jm.note_tier(metadata, md, cfg)  # honour folder placement
        if apply:
            # _coerce_tags never explodes a string into characters, unlike list().
            tags = jm._coerce_tags(metadata.get("tags"))
            for tag in obs.tier_tags(tier):
                if tag not in tags:
                    tags.append(tag)
            jm.update_note_frontmatter(md, {"memory_tier": tier, "tags": tags})
        changed.append((str(md.relative_to(root)), tier))
    return {"changed": changed, "already_tiered": already, "skipped": skipped}


def seed_mocs(root: Path, cfg: dict, *, apply: bool) -> list[str]:
    created = []
    targets = {
        cfg["memory_long_term_root"]: ("Long-Term Map", "long_term",
            "Machine-curated durable knowledge, organised by project. Consolidations land here."),
        cfg["memory_archive_root"]: ("Archive Map", "archive",
            "Retired notes, mostly user-managed. Nothing here is preferred in retrieval."),
    }
    for folder, (title, tier, blurb) in targets.items():
        moc = root / folder / f"{title}.md"
        if moc.exists():
            continue
        body = (
            obs.callout("info", title, blurb) + "\n\n"
            + "## Notes\n\n"
            + obs.moc_table([], columns=("Note", "Why it matters"))
            + "\n"
        )
        created.append(str(moc.relative_to(root)))
        if apply:
            jm.create_note(
                note_type="memory", title=title, content=f"# {title}\n\n{body}", content_mode="full_body",
                cfg=cfg, sync=False,
                metadata_extra={"memory_tier": tier, "type": "map_of_content", "rag_index": False},
                path=moc,
            )
    return created


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    parser.add_argument("--vault", default="", help="vault root override")
    args = parser.parse_args()

    overrides = {"memory_tiers_enabled": True}
    if args.vault:
        overrides["jarvis_notes_root"] = args.vault
    cfg = jm.resolve_config(overrides)
    root = Path(cfg["notes_root"]).resolve()

    print(f"vault: {root}")
    print(f"mode : {'APPLY' if args.apply else 'DRY RUN'}\n")

    result = backfill(root, cfg, apply=args.apply)
    print(f"notes needing a tier : {len(result['changed'])}")
    print(f"already tiered        : {result['already_tiered']}")
    print(f"skipped (system/tmpl) : {result['skipped']}")
    for rel, tier in result["changed"][:20]:
        print(f"  {tier:<11} {rel}")
    if len(result["changed"]) > 20:
        print(f"  ... and {len(result['changed']) - 20} more")

    mocs = seed_mocs(root, cfg, apply=args.apply)
    print(f"\nMOCs to seed: {mocs or 'none'}")

    if args.apply:
        print("\nreindexing...")
        jm.reindex_local(cfg)
        print("done.")

        # Self-check: a bulk write must never leave the vault corrupted silently.
        from core.note_integrity import scan_vault

        health = scan_vault(root)
        errors = {k: v for k, v in health["counts"].items()
                  if k in {"doubled_frontmatter", "unparsable_frontmatter", "exploded_tags", "unreadable"}}
        if errors:
            print(f"\n[!] INTEGRITY ERRORS after migration: {errors}")
            for issue in health["issues"][:15]:
                if issue["severity"] == "error":
                    print(f"    {issue['kind']}: {Path(issue['path']).name}")
            return 1
        warn = {k: v for k, v in health["counts"].items() if k not in errors}
        print(f"integrity: clean ({health['scanned']} notes; notes: {warn or 'none'})")
    else:
        print("\n(dry run — re-run with --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
