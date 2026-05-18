"""Gestion des sessions navigateur persistantes pour LinkedIn et Indeed.

Chaque plateforme dispose d'un `user_data_dir` dédié sous backend/data/browser_sessions/.
Une fois l'utilisateur connecté, les cookies et le localStorage sont sauvegardés
sur disque et réutilisés automatiquement par les recherches browser-use.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SESSIONS_ROOT = Path(__file__).resolve().parents[2] / "data" / "browser_sessions"


PLATFORM_CONFIG: dict[str, dict[str, str]] = {
    "linkedin": {
        "label": "LinkedIn",
        "login_url": "https://www.linkedin.com/login",
        "check_url": "https://www.linkedin.com/feed/",
        "logged_in_marker": "feed-identity-module",
    },
    "indeed": {
        "label": "Indeed",
        "login_url": "https://secure.indeed.com/auth",
        "check_url": "https://www.indeed.com/",
        "logged_in_marker": "gnav-AccountMenu",
    },
}


def get_user_data_dir(platform: str) -> Path:
    """Retourne le user_data_dir pour une plateforme donnée (crée le dossier si besoin)."""
    if platform not in PLATFORM_CONFIG:
        raise ValueError(f"Plateforme inconnue: {platform}")
    path = _SESSIONS_ROOT / platform
    path.mkdir(parents=True, exist_ok=True)
    return path


def has_session(platform: str) -> bool:
    """Vérifie heuristiquement si une session est déjà stockée.

    Ne valide pas la session côté serveur (le cookie peut être expiré) ;
    seulement la présence de données de profil Chrome.
    """
    try:
        path = get_user_data_dir(platform)
    except ValueError:
        return False
    # Chrome stocke les cookies dans Default/Cookies (SQLite)
    cookies_file = path / "Default" / "Cookies"
    if cookies_file.exists() and cookies_file.stat().st_size > 0:
        return True
    # Certaines versions stockent sous Profile 1, ou directement
    for candidate in (path / "Cookies", path / "Default" / "Network" / "Cookies"):
        if candidate.exists() and candidate.stat().st_size > 0:
            return True
    return False


def session_status(platform: str) -> dict[str, Any]:
    """Renvoie l'état actuel d'une session : configurée, dernière mise à jour."""
    cfg = PLATFORM_CONFIG.get(platform, {})
    try:
        path = get_user_data_dir(platform)
    except ValueError:
        return {"platform": platform, "configured": False, "label": cfg.get("label", platform)}

    has_data = has_session(platform)
    last_mod = None
    if has_data:
        try:
            mtime = path.stat().st_mtime
            last_mod = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        except OSError:
            last_mod = None

    return {
        "platform": platform,
        "label": cfg.get("label", platform),
        "configured": has_data,
        "last_updated": last_mod,
        "path": str(path),
    }


def clear_session(platform: str) -> bool:
    """Supprime le user_data_dir d'une plateforme."""
    import shutil

    try:
        path = get_user_data_dir(platform)
    except ValueError:
        return False
    if path.exists():
        try:
            shutil.rmtree(path)
            path.mkdir(parents=True, exist_ok=True)
            return True
        except OSError as exc:
            logger.error("Impossible de supprimer la session %s: %s", platform, exc)
            return False
    return True


# ── Gestion d'un login interactif ─────────────────────────────────────────────

class _LoginTask:
    """Représente un login en cours : navigateur ouvert, attend l'action utilisateur."""

    def __init__(self, platform: str):
        self.platform = platform
        self.status = "starting"   # starting | waiting | completed | error | cancelled
        self.error: str | None = None
        self.started_at = datetime.now(timezone.utc).isoformat()
        self._session = None       # type: ignore[assignment]
        self._task: asyncio.Task | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "status": self.status,
            "error": self.error,
            "started_at": self.started_at,
        }


_active_logins: dict[str, _LoginTask] = {}


async def start_login(platform: str, timeout_seconds: int = 300) -> dict[str, Any]:
    """Lance un browser visible pour login interactif.

    L'utilisateur se connecte manuellement, puis le navigateur reste ouvert
    `timeout_seconds` au maximum avant fermeture forcée. La session est
    sauvegardée automatiquement par browser_use via `user_data_dir`.
    """
    if platform not in PLATFORM_CONFIG:
        return {"status": "error", "error": f"Plateforme inconnue: {platform}"}

    if platform in _active_logins and _active_logins[platform].status in ("starting", "waiting"):
        return {"status": "already_running", **_active_logins[platform].to_dict()}

    task_state = _LoginTask(platform)
    _active_logins[platform] = task_state

    async def _run() -> None:
        cfg = PLATFORM_CONFIG[platform]
        user_data_dir = get_user_data_dir(platform)
        try:
            from browser_use.browser import BrowserSession

            session = BrowserSession(
                headless=False,
                user_data_dir=str(user_data_dir),
            )
            task_state._session = session
            await session.start()
            await session.navigate_to(cfg["login_url"])
            task_state.status = "waiting"
            logger.info("Login %s : navigateur ouvert, en attente d'action utilisateur", platform)

            # Garde le navigateur ouvert jusqu'au timeout (ou cancellation)
            try:
                await asyncio.sleep(timeout_seconds)
            except asyncio.CancelledError:
                logger.info("Login %s annulé par l'utilisateur", platform)
                task_state.status = "cancelled"
                return

            task_state.status = "completed"
        except Exception as exc:
            logger.error("Login %s erreur: %s", platform, exc)
            task_state.status = "error"
            task_state.error = str(exc)
        finally:
            if task_state._session is not None:
                try:
                    await task_state._session.stop()
                except Exception:
                    pass
                task_state._session = None
            if task_state.status not in ("error", "cancelled"):
                task_state.status = "completed"

    task_state._task = asyncio.create_task(_run())
    # Petite pause pour laisser le browser démarrer avant de répondre
    await asyncio.sleep(0.2)
    return {"status": "started", **task_state.to_dict()}


async def finish_login(platform: str) -> dict[str, Any]:
    """L'utilisateur signale qu'il a terminé le login : on ferme le navigateur."""
    task_state = _active_logins.get(platform)
    if not task_state:
        return {"status": "not_running"}
    if task_state._task and not task_state._task.done():
        task_state._task.cancel()
        try:
            await task_state._task
        except (asyncio.CancelledError, Exception):
            pass
    task_state.status = "completed"
    return {"status": "completed", **task_state.to_dict()}


def get_login_status(platform: str) -> dict[str, Any]:
    """Renvoie l'état du login en cours, si applicable."""
    task_state = _active_logins.get(platform)
    if not task_state:
        return {"status": "idle"}
    return task_state.to_dict()


def all_statuses() -> list[dict[str, Any]]:
    """Renvoie l'état de toutes les sessions configurables."""
    return [session_status(p) for p in PLATFORM_CONFIG.keys()]
