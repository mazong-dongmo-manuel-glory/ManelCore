from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
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
        self._interval = 30  # minutes (mode "interval")
        # _next_run_at sert pour le mode "daily" (heure quotidienne fixe)

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

    def _compute_next_delay(self, settings: dict[str, Any]) -> float:
        """Retourne le nombre de secondes jusqu'au prochain run.

        Deux modes :
        - mode='daily' avec scheduled_time='HH:MM' → run quotidien à cette heure
        - mode='interval' (défaut) avec explorer_interval (minutes) → toutes les X min
        """
        mode = settings.get("scheduler_mode", "interval")
        if mode == "daily":
            raw = (settings.get("scheduled_time") or "").strip()
            try:
                hour_str, minute_str = raw.split(":")
                target_hour = int(hour_str)
                target_minute = int(minute_str)
            except (ValueError, AttributeError):
                logger.warning("scheduled_time invalide (%r), fallback en mode interval.", raw)
                return max(int(settings.get("explorer_interval", 30)), 1) * 60

            now = datetime.now()
            target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            if target <= now:
                target = target + timedelta(days=1)
            delay = (target - now).total_seconds()
            logger.info("Prochain cycle planifié à %s (dans %.1f min).", target.isoformat(), delay / 60)
            return delay

        # Mode interval par défaut
        minutes = int(settings.get("explorer_interval", 30))
        minutes = max(minutes, 1)
        self._interval = minutes
        logger.info("Prochain cycle dans %d minutes (mode interval).", minutes)
        return minutes * 60

    async def _loop(self):
        while self._running:
            settings = load_settings()
            delay = self._compute_next_delay(settings)
            await asyncio.sleep(delay)
            if not self._running:
                break

            logger.info("Starting scheduled exploration cycle...")
            try:
                await self.run_once()
            except Exception as e:
                logger.error(f"Error during scheduled exploration: {e}")

            logger.info("Exploration cycle complete.")

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
