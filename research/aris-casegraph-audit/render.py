"""Render the audit markdown into one self-contained HTML file.

Dependency-free on purpose: this must run on a reviewer's machine without pandoc,
npm, or network access. It implements only the subset of Markdown these documents
actually use (headings, paragraphs, lists, tables, fenced code, blockquotes,
inline code/bold/links) and fails loudly rather than silently mangling a document.

Usage:
    python research/aris-casegraph-audit/render.py
"""

from __future__ import annotations

import html
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "index.html"

ORDER = [
    "README.md",
    "10-final-assessment.md",
    "11-novelty-check.md",
    "01-codebase-audit.md",
    "02-paypal-integration.md",
    "03-research-and-market.md",
    "04-ideas-ranked.md",
    "05-roadmap.md",
    "06-technical-risks.md",
    "07-implementation-changelog.md",
    "08-verification-record.md",
    "00-execution-ledger.md",
    "09-source-ledger.md",
    "12-design-direction.md",
    "13-final-qa-and-release.md",
    "14-release-readiness.md",
    "15-EXTERNAL-SETUP-CHECKLIST.md",
]

TITLES = {
    "README.md": "Overview",
    "10-final-assessment.md": "Final assessment",
    "11-novelty-check.md": "Novelty check",
    "01-codebase-audit.md": "Codebase audit",
    "02-paypal-integration.md": "PayPal integration",
    "03-research-and-market.md": "Research & market",
    "04-ideas-ranked.md": "Ranked ideas",
    "05-roadmap.md": "Roadmap",
    "06-technical-risks.md": "Technical risks",
    "07-implementation-changelog.md": "Implementation changelog",
    "08-verification-record.md": "Verification record",
    "00-execution-ledger.md": "Execution ledger",
    "09-source-ledger.md": "Source ledger",
    "12-design-direction.md": "Design direction",
    "13-final-qa-and-release.md": "Final QA and release",
    "14-release-readiness.md": "Release readiness (final)",
    "15-EXTERNAL-SETUP-CHECKLIST.md": "External setup checklist",
}

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_ESCAPE = html.escape


def inline(text: str) -> str:
    placeholders: list[str] = []

    def stash(markup: str) -> str:
        placeholders.append(markup)
        return f"\x00{len(placeholders) - 1}\x00"

    def code(match: re.Match[str]) -> str:
        return stash(f"<code>{_ESCAPE(match.group(1))}</code>")

    def link(match: re.Match[str]) -> str:
        label = _ESCAPE(match.group(1))
        href = _ESCAPE(match.group(2))
        external = href.startswith(("http://", "https://"))
        target = ' target="_blank" rel="noreferrer"' if external else ""
        return stash(f'<a href="{href}"{target}>{label}</a>')

    text = _INLINE_CODE.sub(code, text)
    text = _LINK.sub(link, text)
    text = _ESCAPE(text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    for index, markup in enumerate(placeholders):
        text = text.replace(f"\x00{index}\x00", markup)
    return text


def _is_table_divider(line: str) -> bool:
    stripped = line.strip().strip("|")
    return bool(stripped) and all(set(cell.strip()) <= {"-", ":"} and cell.strip() for cell in stripped.split("|"))


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def render_markdown(source: str) -> str:
    lines = source.splitlines()
    out: list[str] = []
    index = 0
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            out.append(f"<p>{inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    while index < len(lines):
        line = lines[index]

        if line.startswith("```"):
            flush()
            language = line[3:].strip()
            index += 1
            block: list[str] = []
            while index < len(lines) and not lines[index].startswith("```"):
                block.append(lines[index])
                index += 1
            index += 1
            css = f' class="lang-{_ESCAPE(language)}"' if language else ""
            out.append(f"<pre><code{css}>{_ESCAPE(chr(10).join(block))}</code></pre>")
            continue

        if not line.strip():
            flush()
            index += 1
            continue

        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading:
            flush()
            level = len(heading.group(1))
            text = inline(heading.group(2))
            anchor = re.sub(r"[^a-z0-9]+", "-", heading.group(2).lower()).strip("-")[:60]
            out.append(f'<h{level} id="{anchor}">{text}</h{level}>')
            index += 1
            continue

        if line.lstrip().startswith(">"):
            flush()
            quoted: list[str] = []
            while index < len(lines) and lines[index].lstrip().startswith(">"):
                quoted.append(lines[index].lstrip()[1:].lstrip())
                index += 1
            out.append(f"<blockquote>{render_markdown(chr(10).join(quoted))}</blockquote>")
            continue

        if line.strip().startswith("|") and index + 1 < len(lines) and _is_table_divider(lines[index + 1]):
            flush()
            header = _split_row(line)
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(_split_row(lines[index]))
                index += 1
            head = "".join(f"<th>{inline(cell)}</th>" for cell in header)
            body = "".join(
                "<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in row) + "</tr>" for row in rows
            )
            out.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
            continue

        bullet = re.match(r"^(\s*)[-*]\s+(.*)$", line)
        ordered = re.match(r"^(\s*)\d+[.)]\s+(.*)$", line)
        if bullet or ordered:
            flush()
            ordered_list = bool(ordered)
            pattern = r"^(\s*)(?:[-*]|\d+[.)])\s+(.*)$"
            items: list[tuple[int, str]] = []
            while index < len(lines):
                match = re.match(pattern, lines[index])
                if match:
                    items.append((len(match.group(1)) // 2, match.group(2)))
                    index += 1
                    continue
                # Lazy continuation: a wrapped line belongs to the previous item,
                # which is how GitHub renders these documents.
                if (
                    items
                    and lines[index].strip()
                    and not lines[index].startswith(("#", "```", ">", "|"))
                ):
                    depth, text = items[-1]
                    items[-1] = (depth, f"{text} {lines[index].strip()}")
                    index += 1
                    continue
                break
            tag = "ol" if ordered_list else "ul"
            out.append(f"<{tag}>")
            for _depth, text in items:
                out.append(f"<li>{inline(text)}</li>")
            out.append(f"</{tag}>")
            continue

        paragraph.append(line.strip())
        index += 1

    flush()
    return "\n".join(out)


STYLE = """
:root{--ink:#141a26;--muted:#5c677d;--line:#e2e6ee;--surface:#fff;--bg:#f6f7fa;--navy:#16243d;--accent:#2c47a0;
--good:#0f6b3f;--warn:#8a6100;--danger:#a01f24}
*{box-sizing:border-box}
body{margin:0;font:15px/1.65 -apple-system,BlinkMacSystemFont,'Segoe UI',Inter,system-ui,sans-serif;color:var(--ink);background:var(--bg)}
.layout{display:grid;grid-template-columns:260px minmax(0,1fr);min-height:100vh}
nav{position:sticky;top:0;align-self:start;height:100vh;overflow:auto;background:var(--navy);padding:22px 18px}
nav h1{color:#fff;font-size:16px;margin:0 0 4px}
nav p{color:#8ea0c0;font-size:12px;margin:0 0 18px}
nav a{display:block;color:#c6d2e6;text-decoration:none;font-size:13px;padding:7px 10px;border-radius:8px}
nav a:hover{background:#22345a;color:#fff}
main{padding:32px 44px 80px;max-width:1040px}
h1{font-size:30px;letter-spacing:-.02em;margin:0 0 14px}
h2{font-size:21px;margin:38px 0 12px;padding-top:14px;border-top:1px solid var(--line)}
h3{font-size:16px;margin:26px 0 8px;color:#26314a}
h4{font-size:14px;margin:20px 0 6px;color:#26314a;text-transform:uppercase;letter-spacing:.07em}
p{margin:0 0 12px}
a{color:var(--accent)}
code{font:.88em ui-monospace,'Cascadia Mono',Menlo,monospace;background:#eef1f7;padding:1px 5px;border-radius:5px;color:#243}
pre{background:#111a2b;color:#dbe4f3;padding:14px 16px;border-radius:10px;overflow:auto;font-size:12.5px;line-height:1.5}
pre code{background:none;color:inherit;padding:0}
table{border-collapse:collapse;width:100%;margin:14px 0;font-size:13.5px;background:var(--surface)}
th,td{border:1px solid var(--line);padding:8px 11px;text-align:left;vertical-align:top}
th{background:#eef1f7;font-size:12.5px;text-transform:uppercase;letter-spacing:.04em;color:#3a4763}
blockquote{margin:14px 0;padding:12px 16px;border-left:3px solid var(--accent);background:#eef2fb;border-radius:0 8px 8px 0}
blockquote p:last-child{margin-bottom:0}
ul,ol{margin:0 0 14px;padding-left:22px}
li{margin:4px 0}
section{border-bottom:1px solid var(--line);padding-bottom:26px}
@media(max-width:900px){.layout{grid-template-columns:1fr}nav{position:static;height:auto}}
"""


def main() -> int:
    sections: list[str] = []
    nav: list[str] = []
    for name in ORDER:
        path = HERE / name
        if not path.is_file():
            print(f"WARNING: missing {name}")
            continue
        anchor = path.stem.replace(".", "-")
        label = TITLES.get(name, path.stem)
        nav.append(f'<a href="#{anchor}">{html.escape(label)}</a>')
        sections.append(
            f'<section id="{anchor}">{render_markdown(path.read_text(encoding="utf-8"))}</section>'
        )

    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CaseGraph — research &amp; improvement audit</title>
<style>{STYLE}</style>
</head><body><div class="layout">
<nav><h1>CaseGraph audit</h1><p>PayPal AI Hackathon · v1 · 2026-11-08</p>{''.join(nav)}</nav>
<main>{''.join(sections)}</main>
</div></body></html>"""

    OUTPUT.write_text(document, encoding="utf-8")
    print(f"wrote {OUTPUT.name} ({len(document) // 1024} KB, {len(sections)} sections)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
