"""Pure-string helpers for Obsidian-native Markdown.

The vault currently uses only frontmatter, callouts, wikilinks, and tables. These
helpers add the features consolidation needs -- transclusion, collapsible
callouts, Maps of Content, block references, aliases, tag hierarchy -- as small,
side-effect-free functions.

Untrusted text (note titles, source snippets) is passed through the shared
`core.evidence.neutralise` primitive before interpolation, so a hostile title
cannot inject a fence or forge a table row. See the injection-hardening work.
"""

from __future__ import annotations

import re
from typing import Iterable

from core.evidence import neutralise

_VALID_CALLOUTS = {
    "note", "abstract", "summary", "tldr", "info", "todo", "tip", "hint", "important",
    "success", "question", "warning", "caution", "failure", "danger", "bug", "example", "quote",
}


def _clean_inline(text: str) -> str:
    """Neutralise markers and flatten to a single safe inline string."""
    return neutralise(text, flatten_newlines=True).strip()


def _clean_block(text: str) -> str:
    """Neutralise markers but keep line structure for multi-line bodies."""
    return neutralise(text, flatten_newlines=False).rstrip()


def callout(kind: str, title: str, body: str = "", *, collapsed: bool | None = None) -> str:
    """Render an Obsidian callout.

    `collapsed=False` renders an expandable `[!kind]-`-style *foldable* callout
    that starts open (`+`); `collapsed=True` starts folded (`-`); `None` is a
    plain, non-foldable callout.
    """
    kind = str(kind or "note").strip().lower()
    if kind not in _VALID_CALLOUTS:
        kind = "note"
    fold = "" if collapsed is None else ("-" if collapsed else "+")
    header = f"> [!{kind}]{fold} {_clean_inline(title)}".rstrip()
    lines = [header]
    for line in _clean_block(body).splitlines():
        lines.append(f"> {line}" if line else ">")
    return "\n".join(lines).rstrip()


def wikilink(note: str, display: str = "") -> str:
    note = _clean_inline(note).strip("[]")
    if display:
        return f"[[{note}|{_clean_inline(display)}]]"
    return f"[[{note}]]"


def embed(note: str, *, section: str = "", block: str = "") -> str:
    """Transclude a note, a section, or a block (`![[note#section]]`)."""
    note = _clean_inline(note).strip("[]")
    if block:
        anchor = f"#^{_clean_inline(block).lstrip('^')}"
    elif section:
        anchor = f"#{_clean_inline(section).lstrip('#').strip()}"
    else:
        anchor = ""
    return f"![[{note}{anchor}]]"


_BLOCK_ID_RE = re.compile(r"[^a-z0-9-]+")


def block_id(text: str, ident: str) -> str:
    """Append a stable block id so a claim can be cited with `[[note#^id]]`."""
    slug = _BLOCK_ID_RE.sub("-", str(ident or "").strip().lower()).strip("-") or "ref"
    return f"{_clean_block(text).rstrip()} ^{slug}"


def moc_table(entries: Iterable[dict], *, columns: tuple[str, ...] = ("Note", "Why it matters")) -> str:
    """Render a Map-of-Content table of linked notes.

    Each entry is `{"note": basename, "display": optional, "note_note": text}`.
    Links use basename form so the table survives the linked notes being moved.
    """
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    rows = [header, divider]
    for entry in entries:
        link = wikilink(str(entry.get("note") or ""), str(entry.get("display") or ""))
        note = _clean_inline(str(entry.get("note_note") or entry.get("summary") or ""))
        rows.append(f"| {link} | {note} |")
    return "\n".join(rows)


_FILE_CITATION_RE = re.compile(r"\[file:([^\]\n]+)\](?!\()")
# Citation tokens that name inventory metadata, not a real file on disk.
_NON_FILE_TOKENS = {"deterministic_ground_truth", "root_readme_excerpt"}


def file_uri(base: str, rel: str) -> str:
    """A `file:///` URI Obsidian can open, for a repo-relative path."""
    from urllib.parse import quote

    base_fwd = str(base or "").replace("\\", "/").rstrip("/")
    rel_fwd = str(rel or "").replace("\\", "/").lstrip("/")
    full = f"{base_fwd}/{rel_fwd}" if base_fwd else rel_fwd
    return "file:///" + quote(full, safe="/:")


def link_file_citations(text: str, base: str) -> str:
    """Turn `[file:repo/path]` citations into clickable Obsidian file links.

    The repository files these cite live outside the vault, so a `[[wikilink]]`
    cannot reach them; a `file:///` markdown link opens them in the OS. The
    `[file:...]` form is kept as the link *text* so the citation stays readable
    and greppable. Inventory-metadata tokens are left untouched.
    """
    def repl(match: re.Match) -> str:
        rel = match.group(1).strip()
        if rel in _NON_FILE_TOKENS or rel.lower().startswith("root:"):
            return match.group(0)
        return f"[{rel}]({file_uri(base, rel)})"

    return _FILE_CITATION_RE.sub(repl, text or "")


def tier_tags(tier: str) -> list[str]:
    """The hierarchical tag for a memory tier, e.g. `#tier/short-term`."""
    tier = str(tier or "").strip().lower().replace("_", "-")
    return [f"tier/{tier}"] if tier else []
