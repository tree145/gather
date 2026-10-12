"""Local HTML-to-text cleanup adapted from the 0815 project; no fetching."""

import json
import re

from bs4 import BeautifulSoup


META_KEYS = ("og:title", "og:description", "og:type", "description", "keywords",
             "price", "product:", "twitter:title", "twitter:description")


def _jsonld_blocks(soup: BeautifulSoup) -> list[str]:
    out = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (tag.string or tag.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
            out.append(json.dumps(data, ensure_ascii=False)[:3500])
        except Exception:
            out.append(raw[:2500])
    return out[:3]


def _meta_lines(soup: BeautifulSoup) -> list[str]:
    lines, seen = [], set()
    for m in soup.find_all("meta"):
        key = (m.get("property") or m.get("name") or m.get("itemprop") or "").lower()
        content = (m.get("content") or "").strip()
        if not key or not content:
            continue
        if any(k in key for k in META_KEYS) and key not in seen:
            seen.add(key)
            lines.append(f"{key}: {content[:300]}")
    return lines[:15]


def clean_html(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""

    # harvest structured data BEFORE stripping scripts
    ld_blocks = _jsonld_blocks(soup)
    meta_lines = _meta_lines(soup)

    for tag in soup(["script", "style", "noscript", "svg", "iframe", "nav", "footer", "header",
                     "form", "button"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text(separator="\n")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if len(ln) > 2]
    out: list[str] = []
    for ln in lines:
        if not out or out[-1] != ln:
            out.append(ln)
    body = "\n".join(out)

    parts = []
    if title:
        parts.append(f"Page title: {title}")
    if meta_lines:
        parts.append("Page metadata:\n" + "\n".join(meta_lines))
    if ld_blocks:
        parts.append("Structured data (JSON-LD):\n" + "\n\n".join(ld_blocks))
    if body:
        parts.append("Page text:\n" + body)
    return title, "\n\n".join(parts)[:16000]
