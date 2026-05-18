from __future__ import annotations

import asyncio
import os
import re
from typing import Any

import httpx


class SeaoApiService:
    """Small client for SEAO's public search API."""

    DEFAULT_TYPE_IDS = "2,3,5,6,7,8,10,14,15,17,18"
    DEFAULT_STATUS_IDS = "6"

    def __init__(self, base_url: str | None = None, timeout: float = 30.0):
        self.base_url = (base_url or os.getenv(
            "SEAO_API_BASE_URL",
            "https://api.seao.gouv.qc.ca/prod/api",
        )).rstrip("/")
        self.timeout = timeout

    async def search(self, queries: list[str], limit: int = 10, fetch_details: bool = True) -> list[dict[str, Any]]:
        cleaned_queries = [q.strip() for q in queries if q and q.strip()]
        if not cleaned_queries:
            return []

        found: list[dict[str, Any]] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for query in cleaned_queries:
                try:
                    response = await client.get(
                        f"{self.base_url}/recherche",
                        params={
                            "flTxtAllWrds": query,
                            "statIds": self.DEFAULT_STATUS_IDS,
                            "tpIds": self.DEFAULT_TYPE_IDS,
                        },
                        headers={"Accept": "application/json"},
                    )
                    response.raise_for_status()
                except Exception:
                    # Une requête échouée ne doit pas faire planter toute la recherche
                    continue

                payload = response.json()
                results = payload.get("apiData", {}).get("results", [])
                for item in results:
                    if not isinstance(item, dict):
                        continue
                    uuid = str(item.get("uuid") or "")
                    key = uuid or str(item.get("id") or item.get("numero") or item.get("titre") or "")
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    found.append(self._normalise_opportunity(item))
                    if len(found) >= limit:
                        break

            if fetch_details and found:
                # Hydratation : on garde la correspondance index ↔ uuid pour éviter le mismatch
                indexed = [(i, o["seao_uuid"]) for i, o in enumerate(found) if o.get("seao_uuid")]
                if indexed:
                    details = await asyncio.gather(
                        *(self.get_details(str(uuid)) for _, uuid in indexed),
                        return_exceptions=True,
                    )
                    for (idx, _), detail in zip(indexed, details):
                        if not isinstance(detail, dict):
                            continue
                        if detail.get("resume"):
                            found[idx]["resume"] = detail["resume"]
                            found[idx]["description"] = detail["resume"]
                        if detail.get("exigences"):
                            found[idx]["exigences"] = detail["exigences"]
                        if detail.get("budget"):
                            found[idx]["budget"] = detail["budget"]

        return found

    async def get_details(self, uuid: str) -> dict[str, Any]:
        """Fetch full notice details from SEAO."""
        url = f"{self.base_url}/avis/{uuid}/consulter"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers={"Accept": "application/json"})
                if response.status_code != 200:
                    return {}
                
                data = response.json()
                api_data = data.get("apiData", {})
                
                # Extract description/summary
                desc_obj = api_data.get("avisResumeDescription") or {}
                resume = desc_obj.get("descriptionHtml") or ""
                
                # Extract conditions/requirements
                cond_obj = api_data.get("avisResumeConditions") or {}
                exigences = cond_obj.get("descriptionHtml") or ""
                
                # Extract info/budget
                info_obj = api_data.get("avisResumeInformation") or {}
                budget = info_obj.get("valeurEstime") or ""

                return {
                    "resume": self._clean_html(resume),
                    "exigences": self._clean_html(exigences),
                    "budget": budget,
                }
        except Exception:
            return {}

    @staticmethod
    def _clean_html(value: str) -> str:
        """Remove HTML tags and compact whitespace."""
        if not value:
            return ""
        # Basic regex to strip tags
        clean = re.sub(r"<[^>]+>", " ", value)
        # Compact whitespace
        return re.sub(r"\s+", " ", clean).strip()

    @staticmethod
    def build_notice_url(uuid: str) -> str:
        return f"https://seao.gouv.qc.ca/avis-resultat-recherche/consulter?ItemId={uuid}&prov=RechercheAvancee"

    @staticmethod
    def _clean_date(value: Any) -> str:
        """Normalise les dates SEAO (ISO 8601 → YYYY-MM-DD) et écarte les valeurs vides."""
        if not value or str(value).lower() in ("none", "null"):
            return ""
        text = str(value).strip()
        # SEAO renvoie souvent "2025-01-15T00:00:00Z" → on garde la partie date
        if "T" in text:
            text = text.split("T", 1)[0]
        return text

    @staticmethod
    def _normalise_opportunity(item: dict[str, Any]) -> dict[str, Any]:
        uuid = str(item.get("uuid") or "")
        url = "https://seao.gouv.qc.ca/avis-resultat-recherche/consulter"
        if uuid:
            url = SeaoApiService.build_notice_url(uuid)

        return {
            "titre": item.get("titre") or item.get("numero") or "Sans titre",
            "organisation": item.get("nomDonneurOuvrage") or "",
            "date_publication": SeaoApiService._clean_date(item.get("datePublicationUtc")),
            "date_limite": SeaoApiService._clean_date(item.get("dateFermetureUtc")),
            "url": url,
            "source": "SEAO",
            "type": "appel_offres",
            "statut": "nouveau",
            "numero": item.get("numero") or "",
            "reference_id": item.get("id"),
            "seao_uuid": uuid,
            "resume": "",
            "description": "",
        }
