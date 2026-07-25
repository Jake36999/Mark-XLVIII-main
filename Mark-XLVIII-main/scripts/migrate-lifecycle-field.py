"""One-time, idempotent rename: frontmatter field `memory_tier` -> `lifecycle`.

Phase 0 of docs/superpowers/plans/2026-07-23-mark-project-knowledge-cartridges.md:
`memory_tier` (short_term | long_term | archive, a *lifecycle* axis) collided in
name with the owner's structural Tier 0-3 axis. The structural tiers keep the
word "tier"; the lifecycle axis is renamed to stop the collision. This script
renames the field only -- it never moves a note, never touches its `tags`, and
skips any note that already has a `lifecycle` key (safe to re-run).

A note with neither key is left untouched (its tier still resolves via
`note_tier()`'s folder-based fallback, unchanged).

Usage:
    python scripts/migrate-lifecycle-field.py            # dry run
    python scripts/migrate-lifecycle-field.py --apply    # write changes

A full Jarvis_notes backup should exist before --apply -- see
Jarvis_notes_backup_2026-07-25_pre_lifecycle_migration for the one taken
ahead of this script's own first real run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from actions import jarvis_memory as jm

SKIP_TOP = {".obsidian", ".jarvis"}


def _eligible(path: Path, root: Path) -> bool:
    parts = path.resolve().relative_to(root).parts
    return bool(parts) and parts[0] not in SKIP_TOP


def migrate(root: Path, *, apply: bool) -> dict:
    renamed, already, unset, unreadable = [], 0, 0, []
    for md in root.rglob("*.md"):
        if not _eligible(md, root):
            continue
        try:
            raw = md.read_bytes()
            markdown = raw.decode("utf-8-sig")
            metadata, body = jm.parse_frontmatter(markdown)
        except Exception as exc:
            unreadable.append((str(md.relative_to(root)), str(exc)))
            continue
        if "lifecycle" in metadata:
            already += 1
            continue
        value = metadata.get("memory_tier")
        if value is None:
            unset += 1
            continue
        renamed.append((str(md.relative_to(root)), value))
        if not apply:
            continue
        revision = jm.hashlib.sha256(raw).hexdigest()
        metadata = dict(metadata)
        del metadata["memory_tier"]
        metadata["lifecycle"] = value
        metadata["updated"] = jm._now()
        metadata["content_hash"] = jm._content_hash(body)
        jm.atomic_write(
            md,
            f"{jm.render_frontmatter(metadata)}\n\n{body.rstrip()}\n",
            expected_revision=revision,
        )
    return {"renamed": renamed, "already": already, "unset": unset, "unreadable": unreadable}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    parser.add_argument("--vault", default="", help="vault root override")
    args = parser.parse_args()

    cfg = jm.resolve_config({"jarvis_notes_root": args.vault} if args.vault else None)
    root = Path(cfg["notes_root"]).resolve()

    print(f"vault: {root}")
    print(f"mode : {'APPLY' if args.apply else 'DRY RUN'}\n")

    result = migrate(root, apply=args.apply)
    print(f"notes renamed (memory_tier -> lifecycle): {len(result['renamed'])}")
    print(f"already migrated (has 'lifecycle')       : {result['already']}")
    print(f"no memory_tier to rename (left untouched) : {result['unset']}")
    print(f"unreadable (skipped, not corrupted)       : {len(result['unreadable'])}")
    for rel, err in result["unreadable"][:10]:
        print(f"  {rel} -> {err}")
    for rel, value in result["renamed"][:20]:
        print(f"  {value:<11} {rel}")
    if len(result["renamed"]) > 20:
        print(f"  ... and {len(result['renamed']) - 20} more")

    if args.apply:
        print("\nreindexing...")
        jm.reindex_local(cfg)
        print("done.")

        from core.note_integrity import scan_vault

        health = scan_vault(root)
        errors = {
            k: v for k, v in health["counts"].items()
            if k in {"doubled_frontmatter", "unparsable_frontmatter", "exploded_tags", "unreadable"}
        }
        if errors:
            print(f"\n[!] INTEGRITY ERRORS after migration: {errors}")
            for issue in health["issues"][:15]:
                if issue["severity"] == "error":
                    print(f"    {issue['kind']}: {Path(issue['path']).name}")
            return 1
        warn = {k: v for k, v in health["counts"].items() if k not in errors}
        print(f"integrity: clean ({health['scanned']} notes; notes: {warn or 'none'})")
    else:
        print("\n(dry run -- re-run with --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
