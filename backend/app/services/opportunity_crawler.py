from __future__ import annotations

import asyncio
import html
import json
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse, urlunparse

import httpx


class _AnchorExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a" or self._current is not None:
            return
        attr_map = {key.lower(): value or "" for key, value in attrs}
        href = attr_map.get("href", "")
        if href:
            self._current = attr_map
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current is None:
            return
        text = _compact_text(" ".join(self._text))
        self.links.append({"href": self._current.get("href", ""), "text": text})
        self._current = None
        self._text = []


class OpportunityCrawlerService:
    """Lightweight crawler for opportunity/job sources.

    Uses LinkedIn's jobs-guest API (no login required) and Indeed's RSS feed
    for reliable extraction without browser automation.
    """

    def __init__(self, timeout: float = 25.0) -> None:
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-CA,fr;q=0.9,en-CA;q=0.8,en;q=0.7",
        }

    # ── LinkedIn ──────────────────────────────────────────────────────────────

    async def search_linkedin(self, queries: list[str], limit: int = 10) -> list[dict[str, Any]]:
        query = _query_string(queries)
        if not query:
            return []

        # LinkedIn jobs-guest API — public endpoint, no login required
        guest_url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={quote_plus(query)}"
            f"&location={quote_plus('Québec, Canada')}"
            f"&start=0&count={min(limit, 25)}&f_TPR=r604800"
        )
        async with self._client() as client:
            try:
                html_text = await self._fetch(client, guest_url)
                results = _parse_linkedin_guest(html_text, limit)
                if results:
                    return await self._hydrate_links(client, results, "LinkedIn", "opportunite", limit)
            except Exception:
                pass

            # Fallback: public search page
            search_url = (
                "https://www.linkedin.com/jobs/search"
                f"?keywords={quote_plus(query)}"
                f"&location={quote_plus('Québec, Canada')}&f_TPR=r604800"
            )
            try:
                html_text = await self._fetch(client, search_url)
                links = self._extract_links(
                    html_text,
                    search_url,
                    lambda url: "linkedin.com/jobs/view/" in url,
                    limit=limit,
                )
                return await self._hydrate_links(client, links, "LinkedIn", "opportunite", limit)
            except Exception:
                return []

    # ── Indeed ────────────────────────────────────────────────────────────────

    async def search_indeed(self, queries: list[str], limit: int = 10) -> list[dict[str, Any]]:
        query = _query_string(queries)
        if not query:
            return []

        async with self._client() as client:
            # Primary: Indeed RSS feed — stable and doesn't require JS
            rss_url = (
                "https://ca.indeed.com/rss"
                f"?q={quote_plus(query)}&l={quote_plus('Québec, QC')}&fromage=14"
            )
            try:
                rss_text = await self._fetch(client, rss_url)
                links = _parse_indeed_rss(rss_text, limit)
                if links:
                    return await self._hydrate_links(client, links, "Indeed", "emploi", limit)
            except Exception:
                pass

            # Fallback: standard HTML search + data-jk extraction
            search_url = (
                "https://ca.indeed.com/jobs"
                f"?q={quote_plus(query)}&l={quote_plus('Québec, QC')}&fromage=14"
            )
            try:
                html_text = await self._fetch(client, search_url)
                links = self._extract_links(
                    html_text,
                    search_url,
                    lambda url: "ca.indeed.com/rc/clk" in url or "ca.indeed.com/viewjob" in url,
                    limit=limit,
                )
                links.extend(self._extract_indeed_data_jk_links(html_text, limit - len(links)))
                links.extend(_extract_indeed_json_data(html_text, limit - len(links)))
                return await self._hydrate_links(client, links, "Indeed", "emploi", limit)
            except Exception:
                return []

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers,
            follow_redirects=True,
            timeout=self.timeout,
        )

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> str:
        response = await client.get(url)
        response.raise_for_status()
        return response.text

    def _extract_links(
        self,
        html_text: str,
        base_url: str,
        include: Any,
        limit: int,
    ) -> list[dict[str, str]]:
        parser = _AnchorExtractor()
        parser.feed(html_text)

        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for link in parser.links:
            url = _canonical_url(urljoin(base_url, html.unescape(link.get("href", ""))))
            if not url or url in seen or not include(url):
                continue
            seen.add(url)
            results.append({"url": url, "titre": link.get("text", "")})
            if len(results) >= limit:
                break
        return results

    def _extract_indeed_data_jk_links(self, html_text: str, limit: int) -> list[dict[str, str]]:
        if limit <= 0:
            return []
        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for match in re.finditer(r'data-jk=["\']([^"\']+)["\']', html_text):
            job_key = match.group(1)
            if not job_key or job_key in seen:
                continue
            seen.add(job_key)
            window = html_text[max(0, match.start() - 2500) : match.end() + 2500]
            title = _extract_first(window, [
                r'aria-label=["\']([^"\']+)["\']',
                r'title=["\']([^"\']+)["\']',
                r'<span[^>]*>(.*?)</span>',
            ])
            results.append({
                "url": f"https://ca.indeed.com/viewjob?jk={job_key}",
                "titre": _clean_html(title),
            })
            if len(results) >= limit:
                break
        return results

    async def _hydrate_links(
        self,
        client: httpx.AsyncClient,
        links: list[dict[str, str]],
        source: str,
        opportunity_type: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        semaphore = asyncio.Semaphore(4)

        async def hydrate(link: dict[str, str]) -> dict[str, Any] | None:
            async with semaphore:
                extracted: dict[str, Any] = {}
                try:
                    html_text = await self._fetch(client, link["url"])
                    extracted = _extract_job_posting(html_text)
                except Exception:
                    pass
                title = extracted.get("titre") or link.get("titre") or _title_from_url(link["url"])
                if not title:
                    return None
                return {
                    "titre": title,
                    "organisation": extracted.get("organisation", link.get("organisation", "")),
                    "lieu": extracted.get("lieu", ""),
                    "date_publication": extracted.get("date_publication", ""),
                    "date_limite": extracted.get("date_limite", ""),
                    "url": extracted.get("url") or link["url"],
                    "source": source,
                    "type": opportunity_type,
                    "statut": "nouveau",
                    "resume": extracted.get("resume", link.get("resume", "")),
                }

        hydrated = await asyncio.gather(*(hydrate(link) for link in links[:limit]))
        return [item for item in hydrated if item is not None]


# ── LinkedIn jobs-guest parser ────────────────────────────────────────────────

def _parse_linkedin_guest(html_text: str, limit: int) -> list[dict[str, Any]]:
    """Extract structured job cards from LinkedIn jobs-guest API response."""
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Each job is wrapped in a <li> or <div> with data-entity-urn
    for match in re.finditer(
        r'data-entity-urn=["\']urn:li:jobPosting:(\d+)["\']',
        html_text,
    ):
        job_id = match.group(1)
        if job_id in seen:
            continue
        seen.add(job_id)

        # Grab surrounding context to extract title / company / location
        start = max(0, match.start() - 200)
        end = min(len(html_text), match.end() + 3000)
        window = html_text[start:end]

        title = _extract_first(window, [
            r'class="[^"]*base-search-card__title[^"]*"[^>]*>\s*(.*?)\s*</(?:span|h3|h4|a)',
            r'class="[^"]*job-search-card__title[^"]*"[^>]*>\s*(.*?)\s*</(?:span|h3|h4|a)',
            r'aria-label=["\']([^"\']+)["\']',
        ])
        company = _extract_first(window, [
            r'class="[^"]*base-search-card__subtitle[^"]*"[^>]*>\s*(.*?)\s*</(?:span|h4|a)',
            r'class="[^"]*job-search-card__company-name[^"]*"[^>]*>\s*(.*?)\s*</(?:span|a)',
        ])
        location = _extract_first(window, [
            r'class="[^"]*job-search-card__location[^"]*"[^>]*>\s*(.*?)\s*</span>',
        ])

        results.append({
            "titre": _clean_html(title) or f"Emploi LinkedIn #{job_id}",
            "organisation": _clean_html(company),
            "lieu": _clean_html(location),
            "url": f"https://www.linkedin.com/jobs/view/{job_id}/",
            "source": "LinkedIn",
            "type": "opportunite",
            "statut": "nouveau",
            "resume": "",
        })
        if len(results) >= limit:
            break

    # Fallback: href pattern if no data-entity-urn found
    if not results:
        for match in re.finditer(
            r'href=["\'](https://www\.linkedin\.com/jobs/view/(\d+)/[^"\']*)["\']',
            html_text,
        ):
            job_id = match.group(2)
            if job_id in seen:
                continue
            seen.add(job_id)
            results.append({
                "titre": "",
                "organisation": "",
                "lieu": "",
                "url": f"https://www.linkedin.com/jobs/view/{job_id}/",
                "source": "LinkedIn",
                "type": "opportunite",
                "statut": "nouveau",
                "resume": "",
            })
            if len(results) >= limit:
                break

    return results


# ── Indeed RSS parser ─────────────────────────────────────────────────────────

def _parse_indeed_rss(rss_text: str, limit: int) -> list[dict[str, str]]:
    """Parse Indeed RSS feed into link dicts for hydration."""
    results: list[dict[str, str]] = []
    try:
        root = ET.fromstring(rss_text)
    except ET.ParseError:
        return []

    for item in root.findall(".//item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        description = item.findtext("description") or ""
        if not link:
            continue
        jk_match = re.search(r'jk=([a-zA-Z0-9]+)', link)
        clean_url = (
            f"https://ca.indeed.com/viewjob?jk={jk_match.group(1)}"
            if jk_match else link
        )
        results.append({
            "url": clean_url,
            "titre": _clean_html(title),
            "resume": _clean_html(description)[:500],
        })
        if len(results) >= limit:
            break
    return results


def _extract_indeed_json_data(html_text: str, limit: int) -> list[dict[str, str]]:
    """Extract job data from Indeed's embedded window.__INDEED_DATA__ JSON."""
    if limit <= 0:
        return []
    results: list[dict[str, str]] = []
    match = re.search(r'window\.__INDEED_DATA__\s*=\s*(\{.*?\});\s*</script>', html_text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
        jobs = data.get("jobs") or data.get("jobResults") or []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            job_key = job.get("jobKey") or job.get("jk") or ""
            title = job.get("title") or job.get("displayTitle") or ""
            company = job.get("company") or job.get("companyName") or ""
            if job_key and title:
                results.append({
                    "url": f"https://ca.indeed.com/viewjob?jk={job_key}",
                    "titre": _clean_html(title),
                    "organisation": _clean_html(company),
                })
            if len(results) >= limit:
                break
    except Exception:
        pass
    return results


# ── Generic helpers ───────────────────────────────────────────────────────────

def _query_string(queries: list[str]) -> str:
    return " ".join(q.strip() for q in queries[:2] if q and q.strip())


def _canonical_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    if "linkedin.com/jobs/view/" in url:
        match = re.search(r"/jobs/view/(\d+)", parsed.path)
        if match:
            return f"https://www.linkedin.com/jobs/view/{match.group(1)}/"
    if "indeed.com/rc/clk" in url or "indeed.com/viewjob" in url:
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


def _extract_job_posting(html_text: str) -> dict[str, Any]:
    results = {}
    for data in _json_ld_objects(html_text):
        job = _find_job_posting(data)
        if not job:
            continue
        
        results = {
            "titre": _compact_text(str(job.get("title", ""))),
            "organisation": _organisation_name(job.get("hiringOrganization")),
            "lieu": _job_location(job.get("jobLocation")),
            "date_publication": str(job.get("datePosted", "")),
            "date_limite": str(job.get("validThrough", "")),
            "url": str(job.get("url", "")),
            "resume": _clean_html(str(job.get("description", "")))[:1000],
        }
        # Si on a déjà une description riche, on s'arrête
        if len(results.get("resume", "")) > 200:
            return results

    # Fallback: extraction brute depuis le DOM
    title = results.get("titre") or _extract_meta(html_text, "og:title") or _extract_title(html_text)
    
    # Tentative d'extraction de la description/résumé LinkedIn/Indeed
    resume = _extract_meta(html_text, "og:description")
    if not resume or len(resume) < 500:
        # LinkedIn guest page selectors - handle multiline classes and flexible tags
        resume = _extract_first(html_text, [
            r'class\s*=\s*["\'][^"\']*show-more-less-html__markup[^"\']*["\'][^>]*>(.*?)</(?:div|section)>',
            r'class\s*=\s*["\'][^"\']*description__text[^"\']*["\'][^>]*>(.*?)</(?:div|section)>',
            r'id\s*=\s*["\']job-description["\'][^>]*>(.*?)</(?:div|section)>',
        ])
    
    # Try one more: looking for large blocks of text if all else fails
    if not resume or len(resume) < 50:
        # Look for the largest <div content>
        matches = re.findall(r'<div[^>]*>(.{200,})</div>', html_text, re.DOTALL)
        if matches:
            resume = max(matches, key=len)
    
    return {
        "titre": title,
        "resume": _clean_html(resume)[:1000] if resume else ""
    }


def _json_ld_objects(html_text: str) -> list[Any]:
    objects: list[Any] = []
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html_text):
        raw = html.unescape(match.group(1)).strip()
        if not raw:
            continue
        try:
            objects.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return objects


def _find_job_posting(data: Any) -> dict[str, Any] | None:
    if isinstance(data, list):
        for item in data:
            found = _find_job_posting(item)
            if found:
                return found
    if isinstance(data, dict):
        type_value = data.get("@type")
        types = type_value if isinstance(type_value, list) else [type_value]
        if "JobPosting" in types:
            return data
        for key in ("@graph", "mainEntity", "itemListElement"):
            found = _find_job_posting(data.get(key))
            if found:
                return found
    return None


def _organisation_name(value: Any) -> str:
    if isinstance(value, dict):
        return _compact_text(str(value.get("name", "")))
    return _compact_text(str(value or ""))


def _job_location(value: Any) -> str:
    locations = value if isinstance(value, list) else [value]
    pieces: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        address = location.get("address", {})
        if isinstance(address, dict):
            city = address.get("addressLocality") or address.get("streetAddress") or ""
            region = address.get("addressRegion") or ""
            country = address.get("addressCountry") or ""
            pieces.append(_compact_text(", ".join(str(p) for p in (city, region, country) if p)))
    return "; ".join(piece for piece in pieces if piece)


def _extract_meta(html_text: str, property_name: str) -> str:
    escaped = re.escape(property_name)
    patterns = [
        rf'<meta[^>]+property=["\']{escaped}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{escaped}["\']',
    ]
    return _clean_html(_extract_first(html_text, patterns))


def _extract_title(html_text: str) -> str:
    return _clean_html(_extract_first(html_text, [r"<title[^>]*>(.*?)</title>"]))


def _extract_first(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1)
    return ""


def _clean_html(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"<script.*?</script>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style.*?</style>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    return _compact_text(value)


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def _title_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/").split("/")[-1]
    return _compact_text(path.replace("-", " "))
