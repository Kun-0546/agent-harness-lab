"""Minimal, dependency-free Markdown -> HTML renderer for AHL reports.

This is NOT a general Markdown engine. It covers exactly the subset that
`report_builder` emits — ATX headings (#, ##, ###), paragraphs, bullet lists
(nested by indentation), blockquotes, fenced code blocks, pipe tables, horizontal
rules, and inline `**bold**` + `` `code` ``. Anything outside that subset renders
as escaped text.

All text is HTML-escaped before any tags are added, so report content (including a
malicious agent's output that found its way into the evidence) cannot inject markup
or script. The output is a single self-contained document with inline CSS — no
external stylesheet, no JavaScript, no network.
"""
from __future__ import annotations

import html
import re

_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_HEADING = re.compile(r"(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"(\s*)[-*]\s+(.*)$")
_HR = re.compile(r"-{3,}|\*{3,}|_{3,}")

_CSS = (
    "*{box-sizing:border-box}"
    "body{margin:0;background:#f7f7f8;color:#1c1c1e;"
    "font:16px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}"
    "main{max-width:860px;margin:0 auto;padding:32px 24px 64px;background:#fff;"
    "min-height:100vh;border-left:1px solid #ececef;border-right:1px solid #ececef}"
    "h1{font-size:1.7rem;margin:.2em 0 .6em;border-bottom:1px solid #ececef;padding-bottom:.3em}"
    "h2{font-size:1.3rem;margin:1.6em 0 .5em;border-bottom:1px solid #f0f0f2;padding-bottom:.2em}"
    "h3{font-size:1.08rem;margin:1.3em 0 .4em}"
    "p{margin:.6em 0}ul{margin:.5em 0;padding-left:1.4em}li{margin:.25em 0}"
    "code{background:#f0f0f3;border-radius:4px;padding:.1em .35em;"
    "font:0.92em ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}"
    "pre{background:#f0f0f3;border-radius:8px;padding:14px 16px;overflow:auto}"
    "pre code{background:none;padding:0}"
    "blockquote{margin:.8em 0;padding:.4em 1em;border-left:3px solid #d0d0d6;"
    "color:#48484a;background:#fafafb}"
    "table{border-collapse:collapse;width:100%;margin:1em 0;font-size:.96rem}"
    "th,td{border:1px solid #e2e2e6;padding:7px 11px;text-align:left;vertical-align:top}"
    "thead th{background:#f4f4f6;font-weight:600}"
    "tbody tr:nth-child(even){background:#fafafb}hr{border:0;border-top:1px solid #e2e2e6;margin:1.6em 0}"
)


def _inline(text: str) -> str:
    """Escape `text`, then apply inline code spans and bold.

    Code spans are stashed as placeholders BEFORE escaping/bolding so that bold can
    span a code span (the report writes e.g. ``**Winner (by `track`): ...**``) and so
    that `**` inside a code span stays literal.

    NUL is stripped from the input first, so evidence text can never forge a
    placeholder; the restore is also bounds-checked, so it can never raise.
    """
    text = text.replace("\x00", "")
    spans: list[str] = []

    def _stash(m: re.Match) -> str:
        spans.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(spans) - 1}\x00"

    tmp = _CODE.sub(_stash, text)
    tmp = html.escape(tmp)
    tmp = _BOLD.sub(r"<strong>\1</strong>", tmp)
    return re.sub(r"\x00(\d+)\x00",
                  lambda m: spans[int(m.group(1))] if int(m.group(1)) < len(spans)
                  else m.group(0), tmp)


def _is_table_sep(line: str) -> bool:
    s = line.strip()
    return bool(s) and "-" in s and "|" in s and set(s) <= set("|:- \t")


def _row_cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _table_html(header: list[str], rows: list[list[str]]) -> str:
    th = "".join(f"<th>{_inline(c)}</th>" for c in header)
    out = [f"<table><thead><tr>{th}</tr></thead><tbody>"]
    width = len(header)
    for r in rows:
        cells = (r + [""] * width)[:width]
        out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _build_list(items: list[tuple[int, str]], start: int, base: int) -> tuple[str, int]:
    """Build a <ul> for items at indent >= base from `start`. Returns (html, next_idx)."""
    out = ["<ul>"]
    i, n = start, len(items)
    while i < n:
        indent, content = items[i]
        if indent < base:
            break
        if indent > base:  # deeper -> nest under the previous <li>
            sub, i = _build_list(items, i, indent)
            if len(out) > 1 and out[-1].endswith("</li>"):
                out[-1] = out[-1][:-5] + sub + "</li>"
            else:
                out.append(sub)
        else:
            out.append(f"<li>{content}</li>")
            i += 1
    out.append("</ul>")
    return "".join(out), i


def _is_block_start(line: str) -> bool:
    s = line.strip()
    return (s.startswith("#") or s.startswith(">") or s.startswith("```")
            or s.startswith("|") or bool(_BULLET.match(line))
            or bool(_HR.fullmatch(s)))


def render(md: str, *, title: str = "Report") -> str:
    """Render the AHL report Markdown subset to a self-contained HTML document."""
    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    body: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()

        if not s:
            i += 1
            continue

        if s.startswith("```"):  # fenced code block
            i += 1
            code: list[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # skip closing fence (or run off the end)
            body.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
            continue

        if _HR.fullmatch(s):  # horizontal rule
            body.append("<hr>")
            i += 1
            continue

        m = _HEADING.match(s)
        if m:
            level = min(len(m.group(1)), 6)
            body.append(f"<h{level}>{_inline(m.group(2).strip())}</h{level}>")
            i += 1
            continue

        if s.startswith("|") and i + 1 < n and _is_table_sep(lines[i + 1]):  # pipe table
            header = _row_cells(s)
            i += 2
            rows: list[list[str]] = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_row_cells(lines[i]))
                i += 1
            body.append(_table_html(header, rows))
            continue

        if s.startswith(">"):  # blockquote
            quote: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i]).strip())
                i += 1
            inner = " ".join(q for q in quote if q)
            body.append(f"<blockquote><p>{_inline(inner)}</p></blockquote>")
            continue

        if _BULLET.match(line):  # bullet list (indent-nested)
            items: list[tuple[int, str]] = []
            while i < n:
                bm = _BULLET.match(lines[i])
                if bm:
                    indent = len(bm.group(1).replace("\t", "    "))
                    items.append((indent, _inline(bm.group(2).strip())))
                    i += 1
                elif not lines[i].strip() and i + 1 < n and _BULLET.match(lines[i + 1]):
                    i += 1  # blank line between items: keep the list together
                else:
                    break
            html_list, _ = _build_list(items, 0, items[0][0] if items else 0)
            body.append(html_list)
            continue

        # paragraph: gather consecutive plain lines
        para: list[str] = []
        while i < n and lines[i].strip() and not _is_block_start(lines[i]):
            para.append(lines[i].strip())
            i += 1
        body.append(f"<p>{_inline(' '.join(para))}</p>")

    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{html.escape(title)}</title>\n<style>{_CSS}</style>\n</head>\n"
        "<body>\n<main>\n" + "\n".join(body) + "\n</main>\n</body>\n</html>\n"
    )
