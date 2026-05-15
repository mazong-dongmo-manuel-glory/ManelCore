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
            
            if fetch_details:
                # Hydrate descriptions for top results
                tasks = [self.get_details(str(o["seao_uuid"])) for o in found if o.get("seao_uuid")]
                details = await asyncio.gather(*tasks, return_exceptions=True)
                for i, detail in enumerate(details):
                    if isinstance(detail, dict) and detail.get("resume"):
                        found[i]["resume"] = detail["resume"]
                        if detail.get("exigences"):
                            found[i]["exigences"] = detail["exigences"]

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
    def _normalise_opportunity(item: dict[str, Any]) -> dict[str, Any]:
        uuid = str(item.get("uuid") or "")
        url = "https://seao.gouv.qc.ca/avis-resultat-recherche/consulter"
        if uuid:
            url = SeaoApiService.build_notice_url(uuid)

        return {
            "titre": item.get("titre") or item.get("numero") or "Sans titre",
            "organisation": item.get("nomDonneurOuvrage") or "",
            "date_publication": item.get("datePublicationUtc") or "",
            "date_limite": item.get("dateFermetureUtc") or "",
            "url": url,
            "source": "SEAO",
            "type": "appel_offres",
            "statut": "nouveau",
            "numero": item.get("numero") or "",
            "reference_id": item.get("id"),
            "seao_uuid": uuid,
            "resume": "",
        }
