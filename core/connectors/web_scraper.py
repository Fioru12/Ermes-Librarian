"""
core/connectors/web_scraper.py
Enterprise Web / Intranet Wiki Scraper and Crawler.
Fetches web pages, extracts clean readable text and converts them into searchable markdown.
"""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from core.connectors.base import BaseConnector, RemoteDocument

_logger = logging.getLogger(__name__)


def _html_to_markdown(html_text: str) -> str:
    """Converte frammenti HTML comuni in Markdown pulito senza dipendenze pesanti."""
    # Rimuove script e style
    clean = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    # Convert headings
    clean = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n# \1\n", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n## \1\n", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n### \1\n", clean, flags=re.IGNORECASE)
    # Convert paragraphs e list items
    clean = re.sub(r"<p[^>]*>(.*?)</p>", r"\n\1\n", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<li[^>]*>(.*?)</li>", r"\n* \1", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<br\s*/?>", "\n", clean, flags=re.IGNORECASE)
    # Remove remaining HTML tags
    clean = re.sub(r"<[^>]+>", " ", clean)
    # Unescape common entities
    clean = clean.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    # Collapse extra whitespace
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    return "\n\n".join(lines)


class WebScraperConnector(BaseConnector):
    """
    Connettore per estrazione contenuti da portali web o wiki intranet aziendali.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = config.get("base_url", "").strip()
        self.headers = config.get("headers", {"User-Agent": "Ermes-Librarian-Crawler/2.1"})
        self.max_pages = int(config.get("max_pages", 10))

    def test_connection(self) -> tuple[bool, str]:
        if not self.base_url:
            return False, "URL base non configurato"
        try:
            with httpx.Client(timeout=10.0, headers=self.headers, follow_redirects=True) as client:
                res = client.get(self.base_url)
                if res.status_code == 200:
                    return True, f"Raggiunto con successo {self.base_url} (HTTP 200)"
                return False, f"Risposta HTTP non valida: {res.status_code}"
        except Exception as e:
            return False, f"Errore connessione web: {e}"

    def fetch_documents(self) -> list[RemoteDocument]:
        if not self.base_url:
            return []

        documents: list[RemoteDocument] = []
        visited = set()
        to_visit = [self.base_url]
        parsed_base = urlparse(self.base_url)

        with httpx.Client(timeout=15.0, headers=self.headers, follow_redirects=True) as client:
            while to_visit and len(documents) < self.max_pages:
                current_url = to_visit.pop(0)
                if current_url in visited:
                    continue
                visited.add(current_url)

                try:
                    res = client.get(current_url)
                    if res.status_code != 200 or "text/html" not in res.headers.get("content-type", ""):
                        continue

                    # Estrae titolo
                    title_match = re.search(r"<title[^>]*>(.*?)</title>", res.text, re.IGNORECASE)
                    title = title_match.group(1).strip() if title_match else urlparse(current_url).path.strip("/") or "Home"
                    safe_title = re.sub(r"[^\w\s-]", "", title).strip() or "pagina_web"

                    markdown_content = _html_to_markdown(res.text)
                    if len(markdown_content) > 50:
                        doc = RemoteDocument(
                            id=current_url,
                            name=f"{safe_title}.md",
                            content=markdown_content.encode("utf-8"),
                            media_type="text/markdown",
                            source_url=current_url,
                            last_modified=res.headers.get("last-modified", ""),
                            metadata={"title": title, "length": len(markdown_content)},
                        )
                        documents.append(doc)

                    # Trova link interni
                    for href_match in re.finditer(r'href=["\']([^"\']+)["\']', res.text, re.IGNORECASE):
                        link = href_match.group(1).split("#")[0]
                        if not link or link.startswith(("mailto:", "javascript:", "tel:")):
                            continue
                        absolute_link = urljoin(current_url, link)
                        parsed_link = urlparse(absolute_link)
                        if parsed_link.netloc == parsed_base.netloc and absolute_link not in visited:
                            to_visit.append(absolute_link)

                except Exception as e:
                    _logger.warning("Scraper error su %s: %s", current_url, e)

        return documents
