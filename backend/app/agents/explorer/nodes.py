from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from typing import Any, Dict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
import logging

logger = logging.getLogger(__name__)

from app.database.connection import Neo4jConnection
from app.database.repository import GraphRepository
from app.services.opportunity_crawler import OpportunityCrawlerService
from app.services.seao_api import SeaoApiService

from .state import ExplorerState

# ── Global live-event queue (populated by browser step callbacks) ─────────────
browser_live_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
DEFAULT_SEARCH_QUERIES = [
    "informatique",
    "services professionnels",
    "technologie information",
]
DEFAULT_LLM_TIMEOUT_SECONDS = 30.0


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("MODEL", "google/gemma-4-e4b"),
        base_url=os.getenv("MODEL_BASE_URL", "http://localhost:1234/v1"),
        api_key=os.getenv("API_KEY", "lm-studio"),
        max_tokens=2000,
    )


def _get_browser_llm():
    """Retourne le LLM compatible avec browser_use (différent de LangChain).

    browser_use exige sa propre classe ChatOpenAI (qui expose `.provider`),
    pas celle de langchain_openai. Le timeout HTTP est volontairement large
    car les modèles locaux (LM Studio / Ollama) sont nettement plus lents
    que les APIs cloud.
    """
    from browser_use.llm import ChatOpenAI as BUChatOpenAI

    return BUChatOpenAI(
        model=os.getenv("MODEL", "google/gemma-4-e4b"),
        base_url=os.getenv("MODEL_BASE_URL", "http://localhost:1234/v1"),
        api_key=os.getenv("API_KEY", "lm-studio"),
        temperature=0.2,
        timeout=600.0,            # 10 min côté client HTTP
        max_completion_tokens=1024,  # Limite la longueur des réponses pour accélérer Gemma
    )


def _browser_agent_kwargs() -> dict[str, Any]:
    """Paramètres d'Agent browser_use adaptés aux LLM locaux (lents)."""
    return {
        "use_vision": False,            # Gemma ne supporte pas les images
        "llm_timeout": 300,             # 5 min par appel LLM (défaut: 75s)
        "step_timeout": 600,            # 10 min par étape complète
        "max_actions_per_step": 3,      # Réduit la charge cognitive
        "max_history_items": 5,         # Limite le contexte historique envoyé
    }


async def _emit_live_event(source: str, action: str, url: str = "", title: str = "") -> None:
    try:
        browser_live_queue.put_nowait(json.dumps({
            "source": source,
            "step": 0,
            "url": url,
            "title": title,
            "action": action,
            "screenshot": None,
        }, default=str))
    except asyncio.QueueFull:
        pass


# ── Context loaders ───────────────────────────────────────────────────────────

def _load_rich_context() -> dict[str, Any]:
    """Load full company context from Neo4j: profile, profil_entreprise, sectors, recent opps."""
    ctx: dict[str, Any] = {
        "company_profile": "",
        "company_name": "Manel Canada",
        "profil_resume": "",
        "points_forts": "",
        "services": "",
        "sectors": [],
        "sector_descriptions": [],
        "recent_opportunities": [],
        "cv_resumes": [],
    }
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)

            # Entreprise
            entreprises = repo.find_nodes("Entreprise", limit=1)
            if entreprises:
                e = entreprises[0]
                ctx["company_profile"] = e.get("description", "")
                ctx["company_name"] = e.get("nom", "Manel Canada")

            # ProfilEntreprise (detailed analysis)
            profils = repo.find_nodes("ProfilEntreprise", limit=1)
            if profils:
                p = profils[0]
                ctx["profil_resume"] = p.get("resume", "")
                ctx["points_forts"] = p.get("points_forts", "")
                ctx["services"] = p.get("services", "")

            # Sectors with descriptions
            secteurs = repo.find_nodes("Secteur", limit=20)
            ctx["sectors"] = [s["nom"] for s in secteurs if s.get("nom")]
            ctx["sector_descriptions"] = [
                f"{s['nom']}: {s['description']}"
                for s in secteurs
                if s.get("nom") and s.get("description")
            ]
            
            # CVs / Candidatures
            candidatures = repo.find_nodes("Candidature", limit=10)
            ctx["cv_resumes"] = [
                f"CV de {c.get('nom', 'Candidat')}: Poste visé {c.get('poste', 'Non spécifié')}. Résumé/Compétences: {c.get('cv_resume', '')}"
                for c in candidatures if c.get("cv_resume") or c.get("poste")
            ]

            # Charge un échantillon large pour le dedup. À grande échelle,
            # cela devrait passer par une requête Cypher dédiée plutôt que
            # tout charger en mémoire, mais 1000 est suffisant pour le
            # déploiement actuel.
            recent = repo.find_nodes(
                "Opportunite",
                sort_by="created_at",
                descending=True,
                limit=1000,
            )
            ctx["recent_opportunities"] = [
                {
                    "titre": o.get("titre", ""),
                    "source": o.get("source", ""),
                    "seao_uuid": o.get("seao_uuid", ""),
                    "numero": o.get("numero", ""),
                    "reference_id": o.get("reference_id", ""),
                    "url": o.get("url", ""),
                }
                for o in recent
            ]
    except Exception:
        pass
    return ctx


# ── Nodes ─────────────────────────────────────────────────────────────────────

async def load_profile(state: ExplorerState) -> Dict[str, Any]:
    """Load full company profile and sector context from Neo4j."""
    try:
        ctx = await asyncio.to_thread(_load_rich_context)
        profile = state.get("company_profile") or ctx["company_profile"]
        sectors = state.get("sectors") or ctx["sectors"]
        return {
            "company_profile": profile,
            "sectors": sectors,
            "context": ctx,
        }
    except Exception as exc:
        return {"errors": [f"load_profile: {exc}"]}


async def generate_queries(state: ExplorerState) -> Dict[str, Any]:
    """Use LLM to generate optimised search queries per source with full context."""
    from app.services.settings_service import load as _load_settings

    # Si l'utilisateur (chat / API) a déjà fourni des requêtes explicites,
    # on les respecte et on saute la génération LLM.
    explicit_queries = [q for q in (state.get("search_queries") or []) if q]
    if explicit_queries:
        return {"search_queries": explicit_queries[:3]}

    sectors = state.get("sectors") or []
    profile = state.get("company_profile", "")
    ctx = state.get("context", {})

    if not sectors and not profile:
        fallback = _fallback_queries(profile, sectors)
        return {
            "search_queries": fallback,
            "errors": ["generate_queries: aucun profil défini, fallback utilisé"],
        }

    llm = _get_llm()

    # Build a rich context block
    context_lines = []
    if ctx.get("company_name"):
        context_lines.append(f"Entreprise: {ctx['company_name']}")
    if profile:
        context_lines.append(f"Description: {profile}")
    if ctx.get("profil_resume"):
        context_lines.append(f"Résumé analytique: {ctx['profil_resume']}")
    if ctx.get("points_forts"):
        context_lines.append(f"Points forts: {ctx['points_forts']}")
    if ctx.get("services"):
        context_lines.append(f"Services offerts: {ctx['services']}")
    if ctx.get("sector_descriptions"):
        context_lines.append(f"Secteurs cibles: {'; '.join(ctx['sector_descriptions'])}")
    elif sectors:
        context_lines.append(f"Secteurs cibles: {', '.join(sectors)}")
    if ctx.get("cv_resumes"):
        context_lines.append(f"CVs des candidats disponibles:\n" + "\n".join(ctx["cv_resumes"]))

    company_context = "\n".join(context_lines)

    # Optional user-defined orientation for the LLM search
    hint = (state.get("search_prompt_hint") or "").strip()
    if not hint:
        hint = _load_settings().get("search_prompt_hint", "").strip()
    hint_block = f"\n### ORIENTATION SPÉCIFIQUE\n{hint}\n" if hint else ""

    prompt = (
        "Tu es un expert en intelligence d'affaires au Québec spécialisé dans la veille stratégique.\n\n"
        "### PROFIL DE L'ENTREPRISE\n"
        f"{company_context}\n"
        f"{hint_block}\n"
        "### MISSION\n"
        "Génère exactement 3 requêtes de recherche pour trouver des appels d'offres (SEAO) ou contrats (LinkedIn) PERTINENTS.\n"
        "Les requêtes doivent être en français, courtes (2-4 mots) et utiliser des mots-clés techniques ou sectoriels tirés directement du profil ci-dessus.\n"
        "Varie les angles : 1 pour le secteur d'activité, 1 pour les services spécifiques, 1 pour les expertises techniques.\n\n"
        "Réponds UNIQUEMENT en JSON valide: "
        '{"queries": ["requête1", "requête2", "requête3"]}'
    )
    try:
        response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=_llm_timeout())
        match = re.search(r'\{.*\}', response.content, re.DOTALL)
        if match:
            data = json.loads(match.group())
            queries = _normalise_queries(data.get("queries", []), profile, sectors)
            return {"search_queries": queries}
    except Exception as exc:
        fallback = _fallback_queries(profile, sectors)
        return {"errors": [f"generate_queries: {exc}"], "search_queries": fallback}
    return {"search_queries": _fallback_queries(profile, sectors)}


def _normalise_queries(raw_queries: Any, profile: str, sectors: list[str]) -> list[str]:
    queries = [
        str(query).strip()
        for query in (raw_queries if isinstance(raw_queries, list) else [])
        if str(query).strip()
    ]
    return (queries + _fallback_queries(profile, sectors))[:3]


def _fallback_queries(profile: str = "", sectors: list[str] | None = None) -> list[str]:
    candidates: list[str] = []
    candidates.extend(str(sector).strip() for sector in (sectors or []) if str(sector).strip())
    if profile:
        words = re.findall(r"[A-Za-zÀ-ÿ0-9]{4,}", profile.lower())
        stopwords = {
            "avec", "dans", "pour", "nous", "vous", "notre", "votre", "entreprise",
            "services", "solutions", "client", "clients", "quebec", "québec",
        }
        keywords = [word for word in words if word not in stopwords]
        if keywords:
            candidates.append(" ".join(keywords[:3]))
    candidates.extend(DEFAULT_SEARCH_QUERIES)

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(candidate)
        if len(unique) >= 3:
            break
    return unique or DEFAULT_SEARCH_QUERIES[:]


async def search_seao(state: ExplorerState) -> Dict[str, Any]:
    """Search SEAO through its public API."""
    queries = state.get("search_queries") or _fallback_queries(
        state.get("company_profile", ""), state.get("sectors", [])
    )
    try:
        await _emit_live_event("SEAO", "Recherche via API SEAO", "https://api.seao.gouv.qc.ca/prod/api/recherche")
        opps = await SeaoApiService().search(queries[:3], limit=10)
        await _emit_live_event("SEAO", f"{len(opps)} appel(s) d'offres trouvé(s) via API SEAO")
        return {"found_opportunities": opps, "current_source": ["SEAO"]}
    except Exception as exc:
        return {"errors": [f"search_seao: {exc}"], "current_source": ["SEAO"]}


async def search_linkedin(state: ExplorerState) -> Dict[str, Any]:
    """Search LinkedIn via API first, fallback to Browser-Use with headless=False."""
    queries = state.get("search_queries") or _fallback_queries(
        state.get("company_profile", ""), state.get("sectors", [])
    )
    query_str = " ".join(queries[:2])
    opps = []
    try:
        await _emit_live_event("LinkedIn", "Recherche via API publique LinkedIn...", "https://www.linkedin.com/jobs/search")
        try:
            opps = await OpportunityCrawlerService().search_linkedin(queries, limit=10)
        except Exception as api_exc:
            logger.warning(f"LinkedIn API failed: {api_exc}")

        if not opps:
            await _emit_live_event("LinkedIn", "Fallback: Démarrage de l'agent Browser-Use...")
            try:
                from browser_use import Agent
                from browser_use.browser import BrowserSession
                from app.services.browser_sessions import get_user_data_dir, has_session

                # Réutilise la session persistée si l'utilisateur s'est déjà connecté
                user_data_dir = str(get_user_data_dir("linkedin"))
                if has_session("linkedin"):
                    await _emit_live_event("LinkedIn", "Session persistée trouvée — réutilisation du compte connecté")
                else:
                    await _emit_live_event(
                        "LinkedIn",
                        "Aucune session persistée — connectez-vous via Paramètres > Sessions navigateur",
                    )

                browser = BrowserSession(headless=False, user_data_dir=user_data_dir)

                task = (
                    f"Go to https://www.linkedin.com/jobs/search?keywords={query_str}&location=Québec%2C%20Canada "
                    "and extract the top 3 job postings. Return ONLY a valid JSON list of objects. "
                    "Each object must have 'titre', 'organisation', 'lieu', 'url', 'resume', 'source' (set to 'LinkedIn')."
                )
                try:
                    agent = Agent(
                        task=task,
                        llm=_get_browser_llm(),
                        browser_session=browser,
                        **_browser_agent_kwargs(),
                    )
                    history = await agent.run(max_steps=15)

                    result_text = history.final_result()
                    if result_text:
                        match = re.search(r'\[.*\]', result_text, re.DOTALL)
                        if match:
                            opps = json.loads(match.group())
                finally:
                    await browser.stop()
            except Exception as bu_exc:
                logger.warning(f"Browser-use failed for LinkedIn: {bu_exc}")

        await _emit_live_event("LinkedIn", f"{len(opps)} opportunité(s) extraite(s) de LinkedIn")
        return {"found_opportunities": opps, "current_source": ["LinkedIn"]}
    except Exception as exc:
        return {"errors": [f"search_linkedin: {exc}"], "current_source": ["LinkedIn"]}


async def search_indeed(state: ExplorerState) -> Dict[str, Any]:
    """Search Indeed via RSS/API first, fallback to Browser-Use with headless=False."""
    queries = state.get("search_queries") or _fallback_queries(
        state.get("company_profile", ""), state.get("sectors", [])
    )
    query_str = " ".join(queries[:2])
    opps = []
    try:
        await _emit_live_event("Indeed", "Recherche via RSS publique Indeed...", "https://ca.indeed.com/jobs")
        try:
            opps = await OpportunityCrawlerService().search_indeed(queries, limit=10)
        except Exception as api_exc:
            logger.warning(f"Indeed API failed: {api_exc}")

        if not opps:
            await _emit_live_event("Indeed", "Fallback: Démarrage de l'agent Browser-Use...")
            try:
                from browser_use import Agent
                from browser_use.browser import BrowserSession
                from app.services.browser_sessions import get_user_data_dir, has_session

                user_data_dir = str(get_user_data_dir("indeed"))
                if has_session("indeed"):
                    await _emit_live_event("Indeed", "Session persistée trouvée — réutilisation du compte connecté")
                else:
                    await _emit_live_event(
                        "Indeed",
                        "Aucune session persistée — connectez-vous via Paramètres > Sessions navigateur",
                    )

                browser = BrowserSession(headless=False, user_data_dir=user_data_dir)

                task = (
                    f"Go to https://ca.indeed.com/jobs?q={query_str}&l=Québec%2C%20QC "
                    "and extract the top 3 job postings. Return ONLY a valid JSON list of objects. "
                    "Each object must have 'titre', 'organisation', 'lieu', 'url', 'resume', 'source' (set to 'Indeed')."
                )
                try:
                    agent = Agent(
                        task=task,
                        llm=_get_browser_llm(),
                        browser_session=browser,
                        **_browser_agent_kwargs(),
                    )
                    history = await agent.run(max_steps=15)

                    result_text = history.final_result()
                    if result_text:
                        match = re.search(r'\[.*\]', result_text, re.DOTALL)
                        if match:
                            opps = json.loads(match.group())
                finally:
                    await browser.stop()
            except Exception as bu_exc:
                logger.warning(f"Browser-use failed for Indeed: {bu_exc}")

        await _emit_live_event("Indeed", f"{len(opps)} opportunité(s) extraite(s) d'Indeed")
        return {"found_opportunities": opps, "current_source": ["Indeed"]}
    except Exception as exc:
        return {"errors": [f"search_indeed: {exc}"], "current_source": ["Indeed"]}


def _opportunity_match_key(opp: dict[str, Any]) -> str:
    for key in ("seao_uuid", "numero", "reference_id", "url", "titre", "title"):
        value = opp.get(key)
        if value:
            return str(value).strip().lower()
    return ""


def _stable_opportunity_id(opp: dict[str, Any]) -> str | None:
    """Génère un ID déterministe pour éviter les doublons lors de re-fetch.

    Priorité : seao_uuid > url > hash(titre|organisation).
    Retourne None si aucun identifiant fiable n'est disponible (création UUID classique).
    """
    seao = opp.get("seao_uuid")
    if seao:
        return f"seao_{str(seao).strip()}"
    url = opp.get("url")
    if url and str(url).startswith(("http://", "https://")):
        digest = hashlib.sha1(str(url).strip().encode("utf-8")).hexdigest()[:20]
        return f"url_{digest}"
    titre = (opp.get("titre") or opp.get("title") or "").strip().lower()
    org = (opp.get("organisation") or opp.get("organization") or "").strip().lower()
    if titre:
        digest = hashlib.sha1(f"{titre}|{org}".encode("utf-8")).hexdigest()[:20]
        return f"h_{digest}"
    return None


def _safe_float(value: Any) -> float | None:
    """Convertit budget/score en float, accepte '50 000$', '50000.00', etc."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        cleaned = re.sub(r"[^\d.,-]", "", str(value)).replace(",", ".")
        return float(cleaned) if cleaned else None
    except (ValueError, TypeError):
        return None


def _restore_source_fields(ranked: list[dict], originals: list[dict]) -> list[dict]:
    originals_by_key = {_opportunity_match_key(opp): opp for opp in originals if _opportunity_match_key(opp)}
    originals_by_title = {
        str(opp.get("titre") or opp.get("title") or "").strip().lower(): opp
        for opp in originals
        if opp.get("titre") or opp.get("title")
    }

    restored: list[dict] = []
    for index, opp in enumerate(ranked):
        if not isinstance(opp, dict):
            continue
        source = (
            originals_by_key.get(_opportunity_match_key(opp))
            or originals_by_title.get(str(opp.get("titre") or opp.get("title") or "").strip().lower())
            or (originals[index] if index < len(originals) else {})
        )
        merged = {**source, **opp}
        for field in ("url", "source", "seao_uuid", "reference_id", "numero"):
            if not merged.get(field) and source.get(field):
                merged[field] = source[field]
        seao_uuid = merged.get("seao_uuid")
        if merged.get("source") == "SEAO" and seao_uuid and not merged.get("url"):
            merged["url"] = SeaoApiService.build_notice_url(str(seao_uuid))
        restored.append(merged)
    return restored


async def rank_and_analyze(state: ExplorerState) -> Dict[str, Any]:
    """Deduplicate, rank by relevance with detailed analysis, and persist to Neo4j."""
    opportunities = state.get("found_opportunities", [])
    if not opportunities:
        return {
            "ranked_opportunities": [],
            "found_opportunities": [],
            "messages": [HumanMessage(content="Aucune opportunité trouvée.")],
            "errors": ["rank_and_save: aucune opportunité trouvée par les sources"],
        }

    # Deduplicate incoming and filter out already saved
    seen: set[str] = set()
    unique: list[dict] = []
    for opp in opportunities:
        key = _opportunity_match_key(opp)
        if key and key not in seen:
            seen.add(key)
            unique.append(opp)

    ctx = state.get("context", {})
    recent = ctx.get("recent_opportunities", [])
    recent_keys = set()
    for r in recent:
        r_key = _opportunity_match_key(r)
        if r_key:
            recent_keys.add(r_key)
            
    filtered_unique = [opp for opp in unique if _opportunity_match_key(opp) not in recent_keys]
    unique = filtered_unique
    
    if not unique:
        return {
            "ranked_opportunities": [],
            "found_opportunities": opportunities,
            "messages": [HumanMessage(content="Aucune NOUVELLE opportunité trouvée (toutes sont déjà dans la base).")],
            "errors": []
        }

    # LLM ranking with rich context
    llm = _get_llm()
    profile = state.get("company_profile", "")
    sectors = state.get("sectors", [])
    ctx = state.get("context", {})

    context_lines = []
    if ctx.get("company_name"):
        context_lines.append(f"Entreprise: {ctx['company_name']}")
    if profile:
        context_lines.append(f"Description: {profile}")
    if ctx.get("services"):
        context_lines.append(f"Services: {ctx['services']}")
    if ctx.get("points_forts"):
        context_lines.append(f"Points forts: {ctx['points_forts']}")
    if ctx.get("sector_descriptions"):
        context_lines.append(f"Secteurs cibles: {'; '.join(ctx['sector_descriptions'])}")
    elif sectors:
        context_lines.append(f"Secteurs cibles: {', '.join(sectors)}")
    if ctx.get("cv_resumes"):
        context_lines.append(f"CVs des candidats disponibles:\n" + "\n".join(ctx["cv_resumes"]))

    company_context = "\n".join(context_lines) if context_lines else f"Profil: {profile}"

    async def process_batch(batch: list[dict]) -> list[dict] | None:
        # Truncate long fields to avoid LLM context length errors (ex: n_keep >= n_ctx)
        safe_batch = []
        for opp in batch:
            safe_opp = opp.copy()
            if safe_opp.get("resume") and len(safe_opp["resume"]) > 800:
                safe_opp["resume"] = safe_opp["resume"][:800] + "..."
            if safe_opp.get("exigences") and len(safe_opp["exigences"]) > 400:
                safe_opp["exigences"] = safe_opp["exigences"][:400] + "..."
            safe_batch.append(safe_opp)

        prompt = (
            "Tu es un analyste IA TRÈS STRICT spécialisé dans l'évaluation de la pertinence d'affaires (Product-Market Fit).\n\n"
            "### CONTEXTE DE L'ENTREPRISE (CRITÈRES DE SÉLECTION)\n"
            f"{company_context}\n\n"
            "### MISSION\n"
            "Analyse chaque appel d'offres ci-dessous. Tu DOIS être extrêmement sévère. L'opportunité doit s'aligner PARFAITEMENT avec les secteurs d'activité, les services et la description de l'entreprise.\n"
            "S'il s'agit d'un domaine qui n'est pas explicitement couvert par l'entreprise (ex: placement en santé alors que l'entreprise fait du développement logiciel), attribue un score_pertinence de 0.0, même si le titre semble intéressant.\n\n"
            "Pour chaque opportunité, génère un objet JSON contenant:\n"
            '- "score_pertinence": float de 0.0 à 1.0. (0.9+ = correspond exactement au nom et aux secteurs, <0.5 = domaine différent ou hors expertise, 0.0 = rejet immédiat).\n'
            '- "contact_email": email du contact si trouvé, sinon null.\n'
            '- "contact_nom": nom de la personne ressource si trouvé, sinon null.\n'
            '- "draft_email": Si contact_email est présent et score > 0.7, rédige un email d\'introduction ultra-professionnel de la part du dirigeant, sinon null.\n'
            '- "resume": analyse critique structurée de 4-6 phrases incluant:\n'
            "  * **Adéquation Secteur (X%)**: Explique le lien direct (ou l'absence de lien) avec la description de l'entreprise.\n"
            "  * **Analyse Technique**: Les exigences de l'offre par rapport aux capacités de l'entreprise.\n"
            "  * **Recommandation**: Pourquoi soumissionner ou rejeter.\n\n"
            "### OPPORTUNITÉS À ANALYSER\n"
            f"{json.dumps(safe_batch, ensure_ascii=False, indent=2)}\n\n"
            "### FORMAT DE RÉPONSE\n"
            "Retourne UNIQUEMENT un JSON array complet trié par score_pertinence décroissant.\n"
            "IMPORTANT: Conserve tous les champs originaux et ajoute seulement 'score_pertinence', 'contact_email', 'contact_nom', 'draft_email' et 'resume'."
        )
        try:
            response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=_llm_timeout())
            content = response.content.strip()
            
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                match = re.search(r'\[.*\]', content, re.DOTALL)
                if match:
                    return json.loads(match.group())
        except Exception as e:
            logger.error(f"Error in LLM ranking batch: {repr(e)}")
        return None

    # Process in batches of 5 to avoid LLM overload
    batch_size = 5
    batches = [unique[i:i + batch_size] for i in range(0, len(unique), batch_size)]
    
    tasks = [process_batch(b) for b in batches]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    ranked = []
    for i, res in enumerate(results):
        if isinstance(res, list):
            ranked.extend(res)
        else:
            # Fallback for failed batch
            ranked.extend([{"score_pertinence": 0.0, **opp} for opp in batches[i]])
            
    # Sort the combined results by score
    ranked.sort(key=lambda x: float(x.get("score_pertinence", 0.0)), reverse=True)
    ranked = _restore_source_fields(ranked, unique)

    # Persist to Neo4j
    saved, errors = 0, []
    score_threshold = _score_threshold()
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            for opp in ranked:
                try:
                    raw_score = opp.get("score_pertinence")
                    score = float(raw_score) if raw_score is not None else 0.0
                    # Filtre configurable (par défaut 0.5)
                    if score <= score_threshold:
                        continue

                    # Préserve la description originale si le LLM a écrasé `resume` avec son analyse
                    description_originale = (
                        opp.get("description")
                        or opp.get("description_originale")
                        or ""
                    )

                    payload: dict[str, Any] = {
                        "titre":            opp.get("titre") or opp.get("title") or "Sans titre",
                        "source":           opp.get("source", ""),
                        "url":              opp.get("url", ""),
                        "statut":           "nouveau",
                        "type":             opp.get("type", ""),
                        "date_publication": str(opp.get("date_publication") or opp.get("date") or ""),
                        "date_limite":      str(opp.get("date_limite") or ""),
                        "score_pertinence": score,
                        "resume":           opp.get("resume", ""),
                        "description":      description_originale,
                        "organisation":     opp.get("organisation") or opp.get("organization", ""),
                        "lieu":             opp.get("lieu", ""),
                        "exigences":        opp.get("exigences", ""),
                        "numero":           opp.get("numero", ""),
                        "reference_id":     opp.get("reference_id", ""),
                        "seao_uuid":        opp.get("seao_uuid", ""),
                        "contact_email":    opp.get("contact_email", ""),
                        "contact_nom":      opp.get("contact_nom", ""),
                        "draft_email":      opp.get("draft_email", ""),
                    }

                    # Budget : conversion robuste, on omet le champ si non parseable
                    budget = _safe_float(opp.get("budget"))
                    if budget is not None:
                        payload["budget"] = budget

                    # ID déterministe pour éviter les doublons à chaque cycle
                    stable_id = _stable_opportunity_id(opp)
                    if stable_id:
                        payload["id"] = stable_id

                    repo.upsert_opportunite(payload)
                    saved += 1

                    # Engagement automatique suggéré si contact + pertinence haute
                    email = opp.get("contact_email")
                    if email and score > 0.7:
                        logger.info(f"Engagement automatique suggéré pour {email}")
                        await _emit_live_event(
                            "Système",
                            f"Contact suggéré pour {opp.get('organisation', 'Inconnue')} ({email})",
                        )

                except Exception as exc:
                    errors.append(f"save: {exc}")
    except Exception as exc:
        errors.append(f"DB: {exc}")

    summary = f"{saved}/{len(ranked)} opportunités sauvegardées."
    if ranked:
        top = ranked[0]
        summary += (
            f" Meilleure opportunité: «{top.get('titre', 'N/A')}» "
            f"(score: {top.get('score_pertinence', 0):.2f}, source: {top.get('source', '?')})"
        )

    return {
        "ranked_opportunities": ranked,
        "found_opportunities": ranked,
        "errors": errors,
        "messages": [HumanMessage(content=summary)],
    }


async def human_review(state: ExplorerState) -> Dict[str, Any]:
    """
    Placeholder node for human intervention.
    In a real system, the graph interrupts BEFORE this node.
    When resumed, we can process the user's manual edits or approvals.
    """
    review = state.get("review_comment", "")
    approved = state.get("approved_opportunities", [])
    
    if approved:
        # User manually approved some opportunities
        # We could trigger further nodes (e.g. email_drafting)
        return {"messages": [HumanMessage(content=f"Révision terminée: {len(approved)} opportunités validées.")]}
        
    return {"messages": [HumanMessage(content=f"En attente de révision humaine... {review}")]}


def _llm_timeout() -> float:
    try:
        return float(os.getenv("SEARCH_LLM_TIMEOUT_SECONDS", DEFAULT_LLM_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        return DEFAULT_LLM_TIMEOUT_SECONDS


def _score_threshold() -> float:
    """Seuil minimal de pertinence pour sauvegarder une opportunité (configurable)."""
    try:
        value = float(os.getenv("OPPORTUNITY_SCORE_THRESHOLD", "0.5"))
        return max(0.0, min(1.0, value))
    except (TypeError, ValueError):
        return 0.5
