from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any

from app.agents.explorer.graph import create_explorer_graph
from app.database.connection import Neo4jConnection
from app.database.repository import GraphRepository
from app.services.settings_service import load as load_settings, save as save_settings

logger = logging.getLogger(__name__)

class ExplorerService:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._interval = 30 # minutes

    async def start_background_loop(self):
        """Starts the background exploration loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Background Explorer Service started.")

    async def stop_background_loop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Background Explorer Service stopped.")

    async def _loop(self):
        while self._running:
            settings = load_settings()
            self._interval = int(settings.get("explorer_interval", 30))
            
            logger.info("Starting scheduled exploration cycle...")
            try:
                await self.run_once()
            except Exception as e:
                logger.error(f"Error during scheduled exploration: {e}")
            
            logger.info(f"Exploration cycle complete. Waiting {self._interval} minutes.")
            await asyncio.sleep(self._interval * 60)

    async def run_once(self):
        """Runs one cycle of the explorer graph."""
        # Load company profile and sectors from Neo4j
        profile = ""
        sectors = []
        try:
            with Neo4jConnection() as conn:
                repo = GraphRepository(conn)
                entreprises = repo.find_nodes("Entreprise", limit=1)
                sector_nodes = repo.find_nodes("Secteur", limit=50)
            if entreprises:
                profile = entreprises[0].get("description", "")
            if sector_nodes:
                sectors = [s.get("nom") for s in sector_nodes if s.get("nom")]
        except Exception as e:
            logger.error(f"Failed to load context for background explorer: {e}")
            return

        initial_state = {
            "company_profile": profile,
            "sectors": sectors,
            "search_queries": [],
            "found_opportunities": [],
            "ranked_opportunities": [],
            "messages": [],
            "current_source": [],
            "approved_opportunities": [],
            "review_comment": "",
            "errors": [],
        }
        
        config = {"configurable": {"thread_id": "explorer_scheduled"}}
        explorer = create_explorer_graph()
        
        try:
            # We use astream_events to catch 'rank_and_analyze' and notify Telegram
            async for event in explorer.astream_events(initial_state, config=config, version="v2"):
                kind = event.get("event", "")
                name = event.get("name", "")
                
                if kind == "on_chain_end" and name == "rank_and_analyze":
                    # Import here to avoid circular dependency
                    from app.api.main import _telegram
                    if _telegram:
                        ranked = event.get("data", {}).get("output", {}).get("ranked_opportunities", [])
                        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
                        if chat_id:
                            # Notify only the top 3 high-quality matches
                            for opp in ranked[:3]:
                                if float(opp.get("score_pertinence", 0)) > 0.6:
                                    await _telegram.send_opportunity_notification(chat_id, opp)
            
            logger.info("Background exploration cycle complete.")
        except Exception as e:
            logger.error(f"Explorer graph execution failed: {e}")

_instance: ExplorerService | None = None

def get_explorer_service() -> ExplorerService:
    global _instance
    if _instance is None:
        _instance = ExplorerService()
    return _instance
