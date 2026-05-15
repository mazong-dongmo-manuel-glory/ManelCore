from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from typing import AsyncGenerator, List, Optional

import httpx
from bs4 import BeautifulSoup
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from langchain_openai import ChatOpenAI

from app.agents.contact.graph import create_contact_graph
from app.agents.explorer.graph import create_explorer_graph
from app.agents.explorer.nodes import browser_live_queue
from app.database.connection import Neo4jConnection
from app.database.repository import GraphRepository
from app.services.email_agent import get_email_agent
from app.services.rag_service import RagService
from app.services.settings_service import load as load_settings, save as save_settings
from app.services.telegram_service import TelegramService
from app.services.explorer_service import get_explorer_service

_rag = RagService()

app = FastAPI(title="ManelCore AI Agent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Telegram bot (démarré en background au lancement)
_telegram: TelegramService | None = None

@app.on_event("startup")
async def _startup():
    global _telegram
    settings = load_settings()

    # ── Telegram bot ────────────────────────────────────────────────────────
    token = settings.get("telegram_token") or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if token:
        _telegram = TelegramService(token=token)
        asyncio.create_task(_telegram.start_polling_async())

    # ── Email agent (polling IMAP toutes les 5 min) ──────────────────────────
    agent = get_email_agent()
    asyncio.create_task(agent.start_background_loop(interval_minutes=5))

    # ── Explorer agent (polling opportunités) ───────────────────────────────
    explorer_service = get_explorer_service()
    asyncio.create_task(explorer_service.start_background_loop())


@app.on_event("shutdown")
async def _shutdown():
    if _telegram:
        await _telegram.stop_polling_async()


# ─── Pydantic models ──────────────────────────────────────────────────────────

class ConfigUpdate(BaseModel):
    company_name: str
    company_profile: str
    sectors: List[str]
    company_url: Optional[str] = None
    telegram_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

class ExplorerRunRequest(BaseModel):
    company_profile: Optional[str] = None
    sectors: Optional[List[str]] = None

class ContactDraftRequest(BaseModel):
    opportunity_id: str
    contact_info: dict

class ContactApproveRequest(BaseModel):
    thread_id: str
    approved: bool

class ContactCreate(BaseModel):
    nom: str
    email: Optional[str] = None
    telephone: Optional[str] = None
    poste: Optional[str] = None
    organisation: Optional[str] = None
    source: Optional[str] = None
    niveau_importance: Optional[str] = "normal"

class CandidatCreate(BaseModel):
    nom: str
    email: Optional[str] = None
    poste: Optional[str] = None
    statut: Optional[str] = "nouveau"
    cv_resume: Optional[str] = None
    source: Optional[str] = None

class ChatRequest(BaseModel):
    messages: List[dict]
    model: Optional[str] = None
    temperature: float = 0.4
    max_tokens: int = 1200
    use_rag: bool = True          # inject Neo4j context by default

class OpportunityStatusUpdate(BaseModel):
    statut: str

class OpportunityCreate(BaseModel):
    titre: str
    organisation: Optional[str] = None
    source: Optional[str] = "Manuel"
    url: Optional[str] = None
    statut: Optional[str] = "nouveau"
    type: Optional[str] = None
    date_publication: Optional[str] = None
    date_limite: Optional[str] = None
    score_pertinence: Optional[float] = 0.5
    resume: Optional[str] = None
    exigences: Optional[str] = None
    budget: Optional[float] = None

class OpportunityUpdate(BaseModel):
    titre: Optional[str] = None
    organisation: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    statut: Optional[str] = None
    type: Optional[str] = None
    date_publication: Optional[str] = None
    date_limite: Optional[str] = None
    score_pertinence: Optional[float] = None
    resume: Optional[str] = None
    exigences: Optional[str] = None
    budget: Optional[float] = None

class ContactUpdate(BaseModel):
    nom: Optional[str] = None
    email: Optional[str] = None
    telephone: Optional[str] = None
    poste: Optional[str] = None
    organisation: Optional[str] = None
    source: Optional[str] = None
    niveau_importance: Optional[str] = None

class CandidatUpdate(BaseModel):
    nom: Optional[str] = None
    email: Optional[str] = None
    poste: Optional[str] = None
    statut: Optional[str] = None
    cv_resume: Optional[str] = None
    source: Optional[str] = None


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    neo4j_status = "disconnected"
    llm_status = "disconnected"
    try:
        with Neo4jConnection() as conn:
            conn.verify()
            neo4j_status = "connected"
    except Exception as exc:
        neo4j_status = f"error: {exc}"
    try:
        base = os.getenv("MODEL_BASE_URL", "http://localhost:1234/v1").rstrip("/")
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{base}/models")
            llm_status = "connected" if r.status_code == 200 else f"error {r.status_code}"
    except Exception as exc:
        llm_status = f"error: {exc}"
    return {"status": "ok", "neo4j": neo4j_status, "llm": llm_status}


# ─── Dashboard stats ──────────────────────────────────────────────────────────

@app.get("/dashboard/stats")
async def dashboard_stats():
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            all_opps = repo.find_nodes("Opportunite", limit=500)
            contacts = repo.find_nodes("Contact", limit=500)
            messages = repo.find_nodes("Message", limit=500)
        total = len(all_opps)
        validated = sum(1 for o in all_opps if o.get("statut") in ("validé", "approuvé"))
        new_opps = sum(1 for o in all_opps if o.get("statut") == "nouveau")
        emails_sent = sum(1 for m in messages if m.get("direction") == "sortant")
        return {
            "opportunities": total,
            "validated": validated,
            "new": new_opps,
            "emails_sent": emails_sent,
            "contacts": len(contacts),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/data/erase")
async def erase_all_data():
    """Erase all application graph data from Neo4j."""
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            deleted = repo.delete_all_data()
        return {"status": "ok", "deleted": deleted}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Configuration ────────────────────────────────────────────────────────────

@app.post("/config")
async def update_config(config: ConfigUpdate):
    global _telegram
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            repo.upsert_entreprise({
                "nom": config.company_name,
                "description": config.company_profile,
                "site_web": config.company_url or "",
                "secteur_principal": config.sectors[0] if config.sectors else None,
                "telegram_token": config.telegram_token,
                "telegram_chat_id": config.telegram_chat_id,
            })
            for sector in config.sectors:
                repo.upsert_secteur({"nom": sector})
        
        # Re-initialiser le bot si le token a changé
        if config.telegram_token:
            if _telegram:
                await _telegram.stop_polling_async()
            _telegram = TelegramService(token=config.telegram_token)
            asyncio.create_task(_telegram.start_polling_async())
            
        return {"status": "ok", "message": "Configuration mise à jour et bot initialisé."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/config")
async def get_config():
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            entreprises = repo.find_nodes("Entreprise", limit=1)
            sectors = repo.find_nodes("Secteur", limit=50)
        return {
            "entreprise": entreprises[0] if entreprises else {},
            "sectors": [s.get("nom") for s in sectors],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Settings persistants (JSON) ──────────────────────────────────────────────

class SettingsPayload(BaseModel):
    llm_url:            Optional[str] = None
    llm_model:          Optional[str] = None
    llm_api_key:        Optional[str] = None
    neo4j_uri:          Optional[str] = None
    neo4j_password:     Optional[str] = None
    email:              Optional[str] = None
    email_password:     Optional[str] = None
    imap_server:        Optional[str] = None
    telegram_token:     Optional[str] = None
    telegram_chat_id:   Optional[str] = None
    explorer_interval:  Optional[int] = None
    search_prompt_hint: Optional[str] = None
    google_api_key:     Optional[str] = None


class ScrapeProfileRequest(BaseModel):
    url: str


@app.get("/settings")
async def get_settings():
    """Return all persisted runtime settings (passwords masked)."""
    s = load_settings()
    # Mask passwords in the response
    masked = {**s}
    for field in ("llm_api_key", "neo4j_password", "email_password", "telegram_token", "google_api_key"):
        if masked.get(field):
            masked[field] = "********"
    return masked


@app.post("/settings")
async def update_settings(payload: SettingsPayload):
    """Persist runtime settings to data/settings.json and sync env vars."""
    global _telegram
    data = payload.model_dump(exclude_none=True)
    saved = save_settings(data)

    # Restart Telegram bot if token changed
    new_token = data.get("telegram_token")
    if new_token and new_token != "********":
        if _telegram:
            await _telegram.stop_polling_async()
        _telegram = TelegramService(token=new_token)
        asyncio.create_task(_telegram.start_polling_async())

    return {"status": "ok", "saved": list(saved.keys())}


# ─── Scrape & generate company profile ───────────────────────────────────────

@app.post("/scrape-profile")
async def scrape_profile(req: ScrapeProfileRequest):
    """Fetch the company website and ask the LLM to generate a structured profile."""
    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # 1. Fetch the page
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0 (compatible; ManelCore/1.0)"}) as client:
            r = await client.get(url)
            r.raise_for_status()
            html = r.text
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Impossible de récupérer l'URL : {exc}")

    # 2. Extract readable text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "meta", "link"]):
        tag.decompose()
    raw_text = soup.get_text(separator="\n")
    cleaned = re.sub(r"\n{3,}", "\n\n", raw_text).strip()[:3000]

    if len(cleaned) < 80:
        raise HTTPException(status_code=422, detail="Le contenu extrait est trop court — vérifiez l'URL.")

    # 3. Ask LLM to generate the profile
    llm = ChatOpenAI(
        model=os.getenv("MODEL", "google/gemma-4-e4b"),
        base_url=os.getenv("MODEL_BASE_URL", "http://localhost:1234/v1"),
        api_key=os.getenv("API_KEY", "lm-studio"),
        max_tokens=800,
    )
    prompt = (
        "Tu es un expert en développement des affaires au Québec.\n"
        "À partir du texte extrait du site web d'une entreprise ci-dessous, "
        "rédige un profil d'entreprise structuré en français de 150 à 250 mots.\n"
        "Le profil doit inclure : description générale, services offerts, secteurs d'activité, "
        "points forts et clientèle cible.\n"
        "Ne commence PAS par 'Voici' ou 'Ce site'. Commence directement par le nom ou la description.\n\n"
        f"=== CONTENU DU SITE ({url}) ===\n{cleaned}\n\n"
        "=== PROFIL GÉNÉRÉ ==="
    )
    try:
        response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=45.0)
        profile = response.content.strip()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur LLM : {exc}")

    return {"profile": profile, "url": url, "chars_scraped": len(cleaned)}


# ─── Explorer agent ───────────────────────────────────────────────────────────

_explorer_events: list[str] = []
_explorer_running = False

@app.post("/agent/run")
async def run_explorer(req: ExplorerRunRequest, background_tasks: BackgroundTasks):
    global _explorer_running, _explorer_events
    if _explorer_running:
        return {"status": "already_running"}

    profile = req.company_profile
    sectors = req.sectors
    if not profile or not sectors:
        try:
            with Neo4jConnection() as conn:
                repo = GraphRepository(conn)
                entreprises = repo.find_nodes("Entreprise", limit=1)
                sector_nodes = repo.find_nodes("Secteur", limit=50)
            if entreprises and not profile:
                profile = entreprises[0].get("description", "")
            if sector_nodes and not sectors:
                sectors = [s.get("nom") for s in sector_nodes if s.get("nom")]
        except Exception:
            pass

    initial_state = {
        "company_profile": profile or "",
        "sectors": sectors or [],
        "search_queries": [],
        "found_opportunities": [],
        "ranked_opportunities": [],
        "messages": [],
        "current_source": [],
        "approved_opportunities": [],
        "review_comment": "",
        "errors": [],
    }

    async def _run():
        global _explorer_running, _explorer_events
        _explorer_running = True
        _explorer_events = []
        config = {"configurable": {"thread_id": "explorer_default"}}
        try:
            explorer = create_explorer_graph()
            async for event in explorer.astream_events(initial_state, config=config, version="v2"):
                kind = event.get("event", "")
                name = event.get("name", "")
                if kind == "on_chain_end" and name in (
                    "load_profile", "generate_queries",
                    "search_seao", "search_linkedin", "search_indeed", "rank_and_analyze", "human_review"
                ):
                    payload = json.dumps(
                        {"node": name, "data": event.get("data", {})},
                        ensure_ascii=False, default=str,
                    )
                    _explorer_events.append(payload)
                    # Notifier Telegram quand les opportunités sont classées
                    if name == "rank_and_analyze" and _telegram:
                        ranked = event.get("data", {}).get("output", {}).get("ranked_opportunities", [])
                        chat_id = _telegram.chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
                        if not chat_id:
                            try:
                                with Neo4jConnection() as conn:
                                    repo = GraphRepository(conn)
                                    entreprises = repo.find_nodes("Entreprise", limit=1)
                                    if entreprises:
                                        chat_id = entreprises[0].get("telegram_chat_id", "")
                            except Exception:
                                pass
                                
                        if chat_id:
                            for opp in ranked[:3]:
                                await _telegram.send_opportunity_notification(chat_id, opp)
                    
                    if name == "human_review":
                         _explorer_events.append(json.dumps({"node": "human_review", "status": "waiting_for_approval"}))
        except Exception as exc:
            _explorer_events.append(json.dumps({"error": str(exc)}))
        finally:
            _explorer_running = False

    background_tasks.add_task(_run)
    return {"status": "started"}

@app.get("/agent/stream")
async def stream_explorer():
    async def _generator() -> AsyncGenerator[str, None]:
        sent = 0
        while _explorer_running or sent < len(_explorer_events):
            while sent < len(_explorer_events):
                yield f"data: {_explorer_events[sent]}\n\n"
                sent += 1
            await asyncio.sleep(0.5)
        yield 'data: {"done": true}\n\n'
    return StreamingResponse(_generator(), media_type="text/event-stream")

@app.get("/agent/status")
async def agent_status():
    global _explorer_running, _explorer_events
    try:
        explorer = create_explorer_graph()
        state = explorer.get_state({"configurable": {"thread_id": "explorer_default"}})
        waiting = False
        if state and state.next:
            waiting = "human_review" in state.next
        
        return {
            "running": _explorer_running, 
            "events_count": len(_explorer_events),
            "waiting_for_approval": waiting
        }
    except Exception as exc:
        return {
            "running": _explorer_running,
            "events_count": len(_explorer_events),
            "waiting_for_approval": False,
            "error": str(exc)
        }


@app.post("/agent/approve")
async def approve_explorer(body: dict, background_tasks: BackgroundTasks):
    """Resume the explorer graph after human review."""
    global _explorer_running, _explorer_events
    if _explorer_running:
        return {"status": "already_running"}
    
    config = {"configurable": {"thread_id": "explorer_default"}}
    explorer = create_explorer_graph()
    
    # Update state with approvals if provided
    if "approved_opportunities" in body:
        explorer.update_state(config, {"approved_opportunities": body["approved_opportunities"], "review_comment": body.get("comment", "")})

    async def _resume():
        global _explorer_running, _explorer_events
        _explorer_running = True
        try:
            # Resume by passing None to input (it uses existing state)
            async for event in explorer.astream_events(None, config=config, version="v2"):
                kind = event.get("event", "")
                name = event.get("name", "")
                if kind == "on_chain_end" and name in ("human_review", "rank_and_analyze"):
                    _explorer_events.append(json.dumps({"node": name, "data": event.get("data", {})}, default=str))
        except Exception as exc:
            _explorer_events.append(json.dumps({"error": str(exc)}))
        finally:
            _explorer_running = False

    background_tasks.add_task(_resume)
    return {"status": "resumed"}


@app.post("/agent/config")
async def agent_config(body: dict):
    """Update agent configuration (e.g., search interval)."""
    if "interval" in body:
        interval = int(body["interval"])
        save_settings({"explorer_interval": interval})
        return {"status": "ok", "interval": interval}
    return {"status": "no_change"}


@app.get("/agent/summary")
async def agent_summary():
    """Generates a high-level executive summary using the RAG context."""
    try:
        # We use a special query to trigger a comprehensive summary in RAG
        context = await asyncio.to_thread(_rag.build_context, "donne moi un résumé exécutif de la situation actuelle")
        
        # We can also use an LLM to specifically condense this into a professional text
        # For now, we return the structured system block which is already quite rich
        return {
            "summary": context["system_block"],
            "opps_count": context["opps_count"],
            "sources": context["sources"]
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/agent/live-stream")
async def agent_live_stream():
    """SSE: streams live browser steps (URL, title, action, screenshot) in real-time."""
    async def _gen() -> AsyncGenerator[str, None]:
        while True:
            try:
                event = await asyncio.wait_for(browser_live_queue.get(), timeout=30.0)
                yield f"data: {event}\n\n"
            except asyncio.TimeoutError:
                if not _explorer_running:
                    yield 'data: {"done": true}\n\n'
                    return
                yield "data: {\"ping\": true}\n\n"  # keep-alive
    return StreamingResponse(_gen(), media_type="text/event-stream")


@app.post("/agent/run/mock")
async def run_mock(background_tasks: BackgroundTasks):
    """Inject realistic test opportunities directly — no browser agent needed."""
    import datetime
    mock_opps = [
        {
            "titre": "Services de consultation en transformation numérique",
            "organisation": "Ville de Montréal",
            "source": "SEAO",
            "url": "https://seao.gouv.qc.ca/test/1",
            "statut": "nouveau",
            "type": "appel_offres",
            "date_publication": datetime.date.today().isoformat(),
            "date_limite": (datetime.date.today() + datetime.timedelta(days=30)).isoformat(),
            "score_pertinence": 0.92,
            "resume": "La Ville de Montréal cherche un partenaire pour accompagner sa transformation numérique sur 18 mois.",
            "organisation_type": "municipalité",
        },
        {
            "titre": "Développement d'une plateforme RH pour le secteur de la santé",
            "organisation": "Centre hospitalier universitaire de Québec",
            "source": "SEAO",
            "url": "https://seao.gouv.qc.ca/test/2",
            "statut": "nouveau",
            "type": "appel_offres",
            "date_publication": datetime.date.today().isoformat(),
            "date_limite": (datetime.date.today() + datetime.timedelta(days=45)).isoformat(),
            "score_pertinence": 0.87,
            "resume": "Développement d'une solution RH intégrée pour la gestion du personnel infirmier et médical.",
            "organisation_type": "santé",
        },
        {
            "titre": "Consultant en recrutement international — secteur manufacturier",
            "organisation": "Fédération des chambres de commerce du Québec",
            "source": "LinkedIn",
            "url": "https://linkedin.com/test/3",
            "statut": "nouveau",
            "type": "opportunite",
            "date_publication": datetime.date.today().isoformat(),
            "date_limite": (datetime.date.today() + datetime.timedelta(days=20)).isoformat(),
            "score_pertinence": 0.85,
            "resume": "Besoin d'un expert en recrutement international pour des PME québécoises du manufacturier.",
        },
        {
            "titre": "Plateforme de placement de personnel temporaire — logistique",
            "organisation": "Sobeys Québec Inc.",
            "source": "Indeed",
            "url": "https://indeed.ca/test/4",
            "statut": "nouveau",
            "type": "emploi",
            "date_publication": datetime.date.today().isoformat(),
            "date_limite": (datetime.date.today() + datetime.timedelta(days=15)).isoformat(),
            "score_pertinence": 0.78,
            "resume": "Partenariat pour le recrutement de 200 préposés en entrepôt dans la grande région de Montréal.",
        },
        {
            "titre": "Services d'immigration professionnelle — programme travailleurs spécialisés",
            "organisation": "Ministère de l'Immigration, Francisation et Intégration",
            "source": "SEAO",
            "url": "https://seao.gouv.qc.ca/test/5",
            "statut": "nouveau",
            "type": "appel_offres",
            "date_publication": datetime.date.today().isoformat(),
            "date_limite": (datetime.date.today() + datetime.timedelta(days=60)).isoformat(),
            "score_pertinence": 0.95,
            "resume": "Appel à des organismes spécialisés pour accompagner les travailleurs étrangers dans leur intégration professionnelle au Québec.",
        },
    ]

    async def _inject():
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            for opp in mock_opps:
                repo.upsert_opportunite(opp)

    background_tasks.add_task(_inject)
    return {"status": "ok", "count": len(mock_opps), "message": f"{len(mock_opps)} opportunités de test injectées."}


# ─── Opportunities ────────────────────────────────────────────────────────────

@app.get("/opportunities")
async def get_opportunities(limit: int = 50, statut: Optional[str] = None):
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            filters = {"statut": statut} if statut else None
            opps = repo.find_nodes("Opportunite", filters=filters,
                                   sort_by="score_pertinence", descending=True, limit=limit)
        return {"opportunities": opps, "count": len(opps)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.delete("/opportunities")
async def delete_all_opportunities():
    """Delete all opportunities from Neo4j."""
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            opps = repo.find_nodes("Opportunite", limit=10000)
            for o in opps:
                repo.delete_node("Opportunite", o["id"])
        return {"status": "ok", "deleted": len(opps)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/opportunities/{opp_id}/send-draft")
async def send_opportunity_draft(opp_id: str):
    """Send the pre-generated draft for this opportunity."""
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            opp = repo.get_node("Opportunite", opp_id)
            if not opp:
                raise HTTPException(status_code=404, detail="Opportunité non trouvée")
            
            to = opp.get("contact_email")
            body = opp.get("draft_email")
            titre = opp.get("titre", "Opportunité")
            
            if not to or not body:
                raise HTTPException(status_code=400, detail="Aucun brouillon ou contact disponible")
            
            # Use the existing email service
            from app.services.email_service import get_email_service
            email_service = get_email_service()
            await email_service.send_email(to, f"Intérêt pour : {titre}", body)
            
            # Update status
            repo.upsert_opportunite({"id": opp_id, "statut": "en_cours"})
            
        return {"status": "ok", "message": f"Email envoyé à {to}"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/opportunities/{opp_id}")
async def get_opportunity(opp_id: str):
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            opp = repo.get_node("Opportunite", opp_id)
        if not opp:
            raise HTTPException(status_code=404, detail="Opportunité non trouvée")
        return opp
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/opportunities")
async def create_opportunity(body: OpportunityCreate):
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            node = repo.upsert_opportunite(body.model_dump(exclude_none=True))
        return node
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.put("/opportunities/{opp_id}")
async def update_opportunity(opp_id: str, body: OpportunityUpdate):
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            node = repo.upsert_opportunite({"id": opp_id, **body.model_dump(exclude_none=True)})
        return node
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.patch("/opportunities/{opp_id}/status")
async def update_opportunity_status(opp_id: str, body: OpportunityStatusUpdate):
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            repo.upsert_opportunite({"id": opp_id, "statut": body.statut})
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.delete("/opportunities/{opp_id}")
async def delete_opportunity(opp_id: str):
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            repo.delete_node("Opportunite", opp_id)
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Contacts ─────────────────────────────────────────────────────────────────

@app.get("/contacts")
async def get_contacts(limit: int = 100):
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            contacts = repo.find_nodes("Contact", limit=limit)
        return {"contacts": contacts, "count": len(contacts)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/contacts")
async def create_contact(contact: ContactCreate):
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            node = repo.upsert_contact(contact.model_dump(exclude_none=True))
        return node
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.put("/contacts/{contact_id}")
async def update_contact(contact_id: str, body: ContactUpdate):
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            node = repo.upsert_contact({"id": contact_id, **body.model_dump(exclude_none=True)})
        return node
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str):
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            repo.delete_node("Contact", contact_id)
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Candidats (RH) ───────────────────────────────────────────────────────────

@app.get("/candidats")
async def get_candidats(limit: int = 100):
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            candidats = repo.find_nodes("Candidature", limit=limit)
        return {"candidats": candidats, "count": len(candidats)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/candidats")
async def create_candidat(candidat: CandidatCreate):
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            node = repo.upsert_candidature(candidat.model_dump(exclude_none=True))
        return node
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.put("/candidats/{candidat_id}")
async def update_candidat(candidat_id: str, body: CandidatUpdate):
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            node = repo.upsert_candidature({"id": candidat_id, **body.model_dump(exclude_none=True)})
        return node
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.patch("/candidats/{candidat_id}/status")
async def update_candidat_status(candidat_id: str, statut: str):
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            repo.upsert_candidature({"id": candidat_id, "statut": statut})
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.delete("/candidats/{candidat_id}")
async def delete_candidat(candidat_id: str):
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            repo.delete_node("Candidature", candidat_id)
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Email agent ─────────────────────────────────────────────────────────────

class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str


@app.post("/email/check")
async def email_check(background_tasks: BackgroundTasks):
    """Trigger an immediate check on all configured inboxes."""
    agent = get_email_agent()
    background_tasks.add_task(agent.check_all_inboxes)
    return {"status": "started", "message": "Vérification de toutes les boîtes de réception lancée."}


@app.get("/email/inbox")
async def email_inbox(account: str = "principal"):
    """Return a live summary of unread emails for a given account (principal|hr|company)."""
    agent = get_email_agent()
    summary = await agent.get_inbox_summary(account)
    return summary


@app.get("/email/inbox/all")
async def email_inbox_all():
    """Return unread counts for all configured email accounts."""
    agent = get_email_agent()
    accounts = ["principal", "hr", "company"]
    summaries = await asyncio.gather(*(agent.get_inbox_summary(a) for a in accounts))
    return {"accounts": [s for s in summaries if s.get("configured")]}


@app.post("/email/send")
async def email_send(req: SendEmailRequest):
    """Send an email directly via SMTP (compte principal)."""
    agent = get_email_agent()
    ok = await agent.send_email(req.to, req.subject, req.body, account="principal")
    if ok:
        return {"status": "sent"}
    raise HTTPException(status_code=500, detail="Envoi échoué — vérifiez la configuration email.")


@app.post("/email/send/hr")
async def email_send_hr(req: SendEmailRequest):
    """Send an email from the HR account (candidatures, recrutement)."""
    agent = get_email_agent()
    ok = await agent.send_email(req.to, req.subject, req.body, account="hr")
    if ok:
        return {"status": "sent", "account": "hr"}
    raise HTTPException(status_code=500, detail="Envoi RH échoué — vérifiez MAILER_HR_EMAIL.")


@app.get("/email/conversations")
async def email_conversations(limit: int = 30, classification: Optional[str] = None):
    """Return all email conversations with sender contact info."""
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            filters: dict = {"canal": "email"}
            if classification:
                filters["statut"] = classification
            convs = repo.find_nodes(
                "Conversation", filters=filters,
                sort_by="updated_at", descending=True, limit=limit,
            )
            # Enrichir chaque conversation avec le contact expéditeur
            enriched = []
            for conv in convs:
                conv_id = conv.get("id", "")
                contacts = repo.get_related_nodes(
                    "Conversation", conv_id, "IMPLIQUE", "Contact", limit=1
                ) if conv_id else []
                sender = contacts[0].get("node", contacts[0]) if contacts else {}
                enriched.append({**conv, "sender": sender})
        return {"conversations": enriched, "count": len(enriched)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/email/conversations/{conv_id}")
async def email_conversation_detail(conv_id: str):
    """Return a conversation with ALL its messages (full content) and sender info."""
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            conv = repo.get_node("Conversation", conv_id)
            if not conv:
                raise HTTPException(status_code=404, detail="Conversation non trouvée")

            # Tous les messages de la conversation
            msg_relations = repo.get_related_nodes(
                "Conversation", conv_id, "CONTIENT", "Message", limit=100
            )
            messages = []
            for rel in msg_relations:
                node = rel.get("node", rel)
                messages.append(node)
            # Trier par date_envoi
            messages.sort(key=lambda m: m.get("date_envoi", ""), reverse=False)

            # Contact expéditeur
            contact_rels = repo.get_related_nodes(
                "Conversation", conv_id, "IMPLIQUE", "Contact", limit=5
            )
            contacts = [r.get("node", r) for r in contact_rels]

            # Candidature liée si applicable
            cand_rels = repo.get_related_nodes(
                "Conversation", conv_id, "CONCERNE", "Candidature", limit=1
            )
            candidature = cand_rels[0].get("node", cand_rels[0]) if cand_rels else None

        return {
            "conversation": conv,
            "messages": messages,
            "messages_count": len(messages),
            "contacts": contacts,
            "candidature": candidature,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/email/messages")
async def email_messages(
    limit: int = 50,
    direction: Optional[str] = None,
    classification: Optional[str] = None,
):
    """Return recent email messages with all fields."""
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            filters: dict = {"canal": "email"}
            if direction:
                filters["direction"] = direction
            if classification:
                filters["classification"] = classification
            messages = repo.find_nodes(
                "Message", filters=filters,
                sort_by="date_envoi", descending=True, limit=limit,
            )
        return {"messages": messages, "count": len(messages)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/email/messages/{msg_id}")
async def email_message_detail(msg_id: str):
    """Return a single message with its full content, HTML body, and attachments info."""
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            msg = repo.get_node("Message", msg_id)
        if not msg:
            raise HTTPException(status_code=404, detail="Message non trouvé")
        return msg
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Chat LLM avec Graph RAG ──────────────────────────────────────────────────

@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    base_url = os.getenv("MODEL_BASE_URL", "http://localhost:1234/v1").rstrip("/")
    model    = req.model or os.getenv("MODEL", "google/gemma-4-e4b")
    api_key  = os.getenv("API_KEY", "lm-studio")

    # ── Build RAG context from Neo4j ─────────────────────────────────────────
    rag_meta: dict = {"sources": [], "opps_count": 0}
    enriched_messages = list(req.messages)

    if req.use_rag:
        # Extract last user message for context retrieval
        last_user = next(
            (m["content"] for m in reversed(req.messages) if m.get("role") == "user"),
            "",
        )
        try:
            rag_result = await asyncio.to_thread(_rag.build_context, last_user)
            rag_meta = rag_result

            # Prepend RAG system prompt (or replace existing system message)
            rag_system = {
                "role": "system",
                "content": (
                    "Tu es ARIA, l'assistante exécutive intelligente de ManelCore. "
                    "Ta mission est d'aider le dirigeant à identifier les meilleures opportunités et à gérer ses communications de façon ultra-professionnelle.\n\n"
                    "CONSIGNES DE STYLE :\n"
                    "- Réponds en français impeccable, sur un ton calme, confiant et expert.\n"
                    "- Utilise un formatage structuré (points de liste, gras) pour faciliter la lecture sur mobile.\n"
                    "- Sois proactive : si tu vois une opportunité à haut score (90%+), souligne-la immédiatement.\n\n"
                    "CAPACITÉS :\n"
                    "- Tu as un accès direct aux données Neo4j (CRM, opportunités, RH).\n"
                    "- Tu peux analyser les emails et proposer des brouillons pertinents.\n"
                    "- Tu peux lancer des recherches de nouveaux contrats (SEAO, LinkedIn).\n\n"
                    "CONTEXTE DE L'ENTREPRISE :\n"
                    + rag_result["system_block"]
                ),
            }
            # Remove any existing system message then prepend the enriched one
            enriched_messages = [m for m in enriched_messages if m.get("role") != "system"]
            enriched_messages = [rag_system] + enriched_messages
        except Exception as exc:
            # RAG failure is non-blocking — fall back to bare system prompt
            enriched_messages = [
                {"role": "system", "content": "Tu es ARIA, l'assistante intelligente de ManelCore."}
            ] + [m for m in enriched_messages if m.get("role") != "system"]

    async def _generate() -> AsyncGenerator[str, None]:
        # First event: send RAG metadata so the UI can show the context badge
        if req.use_rag:
            yield f"data: {json.dumps({'rag': rag_meta})}\n\n"

        payload = {
            "model": model,
            "messages": enriched_messages,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as response:
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data = line.removeprefix("data:").strip()
                        if data == "[DONE]":
                            yield "data: [DONE]\n\n"
                            return
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield f"data: {json.dumps({'content': content})}\n\n"
                        except Exception:
                            continue
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")


# ─── Contact agent ────────────────────────────────────────────────────────────

_contact_threads: dict[str, dict] = {}

@app.post("/contact/draft")
async def draft_contact(req: ContactDraftRequest):
    thread_id = str(uuid.uuid4())
    graph = create_contact_graph()
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "opportunity_id": req.opportunity_id,
        "contact_info": req.contact_info,
        "opportunity_details": {},
        "company_context": {},
        "conversation_history": [],
        "draft_email": "",
        "status": "drafting",
        "approved": False,
        "error": "",
        "messages": [],
    }
    try:
        state = await graph.ainvoke(initial_state, config)
        _contact_threads[thread_id] = {"graph": graph, "config": config}
        return {
            "thread_id": thread_id,
            "draft_email": state.get("draft_email", ""),
            "status": state.get("status", ""),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/contact/approve")
async def approve_contact(req: ContactApproveRequest):
    thread = _contact_threads.get(req.thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread non trouvé")
    graph, config = thread["graph"], thread["config"]
    try:
        state = await graph.ainvoke(
            {"approved": req.approved, "status": "approved" if req.approved else "rejected"},
            config,
        )
        if req.approved:
            del _contact_threads[req.thread_id]
        return {"status": state.get("status", ""), "error": state.get("error", "")}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
