"""Outils exposés au LLM pour exécuter des actions dans l'application.

Le chat (et le bot Telegram) peuvent appeler ces outils en émettant un bloc :

    <action>{"tool": "send_email", "args": {"to": "...", "subject": "...", "body": "..."}}</action>

Le runtime intercepte ce bloc, exécute l'outil, renvoie le résultat dans la
conversation, puis le LLM continue sa réponse.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Awaitable, Callable

from app.database.connection import Neo4jConnection
from app.database.repository import GraphRepository
from app.services.email_agent import get_email_agent
from app.services.settings_service import save as save_settings

logger = logging.getLogger(__name__)

# ── Définitions des outils ────────────────────────────────────────────────────

ToolFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


async def _tool_send_email(args: dict[str, Any]) -> dict[str, Any]:
    to = (args.get("to") or "").strip()
    subject = (args.get("subject") or "").strip()
    body = (args.get("body") or "").strip()
    account = (args.get("account") or "principal").strip()
    if not (to and subject and body):
        return {"ok": False, "error": "Paramètres manquants (to, subject, body requis)."}
    agent = get_email_agent()
    ok = await agent.send_email(to, subject, body, account=account)
    return {"ok": ok, "to": to, "subject": subject,
            "message": f"Email envoyé à {to}" if ok else "Envoi échoué — vérifiez la configuration email."}


async def _tool_check_inbox(args: dict[str, Any]) -> dict[str, Any]:
    account = (args.get("account") or "principal").strip()
    agent = get_email_agent()
    summary = await agent.get_inbox_summary(account)
    return {"ok": True, **summary}


def _coerce_list(value: Any) -> list[str]:
    """Convertit string CSV / list / None en list[str] propre."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [p.strip() for p in value.replace(";", ",").split(",") if p.strip()]
    return []


async def _tool_run_explorer(args: dict[str, Any]) -> dict[str, Any]:
    """Lance un cycle d'exploration en arrière-plan.

    Args supportés (tous optionnels) :
      - profile (str)        : description/profil à viser (remplace la valeur Neo4j)
      - sectors (list|str)   : secteurs cibles (liste ou CSV)
      - queries (list|str)   : requêtes textuelles à utiliser tel quel
      - query (str)          : requête unique (alias de queries=[query])
      - hint (str)           : orientation libre injectée dans le prompt LLM

    Sans aucun argument, on retombe sur le comportement par défaut
    (profil + secteurs de l'entreprise dans Neo4j).
    """
    from app.api import main as api_main  # import paresseux pour éviter les cycles

    if api_main._explorer_running:
        return {"ok": False, "status": "already_running",
                "message": "Un cycle d'exploration est déjà en cours."}

    # ── Inputs explicites depuis le LLM ──────────────────────────────────────
    arg_profile = (args.get("profile") or args.get("company_profile") or "").strip()
    arg_sectors = _coerce_list(args.get("sectors") or args.get("secteurs"))
    arg_queries = _coerce_list(args.get("queries") or args.get("search_queries"))
    single_query = (args.get("query") or "").strip()
    if single_query and single_query not in arg_queries:
        arg_queries.insert(0, single_query)
    arg_hint = (args.get("hint") or args.get("search_prompt_hint") or "").strip()

    # ── Fallback Neo4j si certains champs manquent ───────────────────────────
    profile = arg_profile
    sectors = list(arg_sectors)
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            if not profile:
                entreprises = repo.find_nodes("Entreprise", limit=1)
                if entreprises:
                    profile = entreprises[0].get("description", "")
            if not sectors:
                sector_nodes = repo.find_nodes("Secteur", limit=50)
                if sector_nodes:
                    sectors = [s.get("nom") for s in sector_nodes if s.get("nom")]
    except Exception:
        pass

    # Si l'utilisateur a fourni des requêtes explicites, on saute la
    # génération LLM et on passe directement dans les nodes de recherche.
    initial_state: dict[str, Any] = {
        "company_profile": profile,
        "sectors": sectors,
        "search_queries": arg_queries[:3],  # le pipeline n'en consomme que 2-3
        "search_prompt_hint": arg_hint,
        "found_opportunities": [],
        "ranked_opportunities": [],
        "messages": [],
        "current_source": [],
        "approved_opportunities": [],
        "review_comment": "",
        "errors": [],
    }

    # Déclenchement non-bloquant via la même mécanique que /agent/run
    import asyncio
    from app.agents.explorer.graph import create_explorer_graph

    async def _run() -> None:
        api_main._explorer_running = True
        api_main._explorer_events = []
        try:
            explorer = create_explorer_graph()
            config = {"configurable": {"thread_id": "explorer_chat"}}
            async for _ in explorer.astream_events(initial_state, config=config, version="v2"):
                pass
        except Exception as exc:
            logger.error("run_explorer (chat) erreur : %s", exc)
        finally:
            api_main._explorer_running = False

    asyncio.create_task(_run())

    # Message de retour reflète les critères utilisés
    detail_parts: list[str] = []
    if arg_queries:
        detail_parts.append(f"requêtes={arg_queries[:3]}")
    if sectors and not arg_queries:
        detail_parts.append(f"secteurs={sectors[:5]}")
    if arg_hint:
        detail_parts.append("avec orientation personnalisée")
    detail = " ; ".join(detail_parts) if detail_parts else "profil entreprise par défaut"

    return {
        "ok": True,
        "status": "started",
        "queries": arg_queries[:3],
        "sectors": sectors,
        "message": f"Cycle d'exploration lancé en arrière-plan ({detail}).",
    }


async def _tool_list_opportunities(args: dict[str, Any]) -> dict[str, Any]:
    statut = args.get("statut")
    limit = int(args.get("limit") or 5)
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            filters = {"statut": statut} if statut else None
            opps = repo.find_nodes(
                "Opportunite",
                filters=filters,
                sort_by="score_pertinence",
                descending=True,
                limit=limit,
            )
        compact = [
            {
                "id": o.get("id", ""),
                "titre": o.get("titre", ""),
                "organisation": o.get("organisation", ""),
                "score": o.get("score_pertinence"),
                "statut": o.get("statut", ""),
                "url": o.get("url", ""),
            }
            for o in opps
        ]
        return {"ok": True, "count": len(compact), "opportunities": compact}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def _tool_update_opportunity_status(args: dict[str, Any]) -> dict[str, Any]:
    opp_id = (args.get("id") or "").strip()
    statut = (args.get("statut") or "").strip()
    if not opp_id or statut not in ("validé", "rejeté", "en_cours", "nouveau"):
        return {"ok": False, "error": "id et statut (validé|rejeté|en_cours|nouveau) requis."}
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            repo.upsert_opportunite({"id": opp_id, "statut": statut})
        return {"ok": True, "id": opp_id, "statut": statut}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def _tool_send_opportunity_draft(args: dict[str, Any]) -> dict[str, Any]:
    opp_id = (args.get("id") or "").strip()
    if not opp_id:
        return {"ok": False, "error": "id requis."}
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            opp = repo.get_node("Opportunite", opp_id)
            if not opp:
                return {"ok": False, "error": "Opportunité introuvable."}
            to = opp.get("contact_email")
            body = opp.get("draft_email")
            titre = opp.get("titre", "Opportunité")
            if not to or not body:
                return {"ok": False, "error": "Aucun brouillon ou contact disponible pour cette opportunité."}
            agent = get_email_agent()
            ok = await agent.send_email(to, f"Intérêt pour : {titre}", body)
            if ok:
                repo.upsert_opportunite({"id": opp_id, "statut": "en_cours"})
            return {"ok": ok, "to": to,
                    "message": f"Brouillon envoyé à {to}" if ok else "Envoi échoué."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def _tool_list_contacts(args: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit") or 10)
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            contacts = repo.find_nodes("Contact", limit=limit)
        return {"ok": True, "count": len(contacts), "contacts": [
            {"id": c.get("id"), "nom": c.get("nom"), "email": c.get("email"),
             "organisation": c.get("organisation"), "poste": c.get("poste")}
            for c in contacts
        ]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def _tool_create_contact(args: dict[str, Any]) -> dict[str, Any]:
    nom = (args.get("nom") or "").strip()
    if not nom:
        return {"ok": False, "error": "nom requis."}
    payload = {
        "nom": nom,
        "email": args.get("email"),
        "telephone": args.get("telephone"),
        "poste": args.get("poste"),
        "organisation": args.get("organisation"),
        "niveau_importance": args.get("niveau_importance", "normale"),
    }
    payload = {k: v for k, v in payload.items() if v}
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            node = repo.upsert_contact(payload)
        return {"ok": True, "id": node.get("id"), "contact": node}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def _tool_set_explorer_interval(args: dict[str, Any]) -> dict[str, Any]:
    try:
        minutes = int(args.get("minutes"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "minutes (entier) requis."}
    if minutes < 1:
        return {"ok": False, "error": "L'intervalle doit être >= 1 minute."}
    save_settings({"explorer_interval": minutes})
    return {"ok": True, "minutes": minutes,
            "message": f"Intervalle réglé à {minutes} minutes."}


async def _tool_dashboard_stats(_args: dict[str, Any]) -> dict[str, Any]:
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            opps = repo.find_nodes("Opportunite", limit=500)
            contacts = repo.find_nodes("Contact", limit=500)
            messages = repo.find_nodes("Message", limit=500)
        return {
            "ok": True,
            "opportunities": len(opps),
            "validated": sum(1 for o in opps if o.get("statut") in ("validé", "approuvé")),
            "new": sum(1 for o in opps if o.get("statut") == "nouveau"),
            "emails_sent": sum(1 for m in messages if m.get("direction") == "sortant"),
            "contacts": len(contacts),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# Registry — chaque entrée : (description, schema_args, fonction)
TOOLS: dict[str, dict[str, Any]] = {
    "send_email": {
        "description": "Envoie un email via SMTP depuis le compte principal (ou hr/company).",
        "args": {"to": "string", "subject": "string", "body": "string", "account": "string (optionnel)"},
        "fn": _tool_send_email,
    },
    "check_inbox": {
        "description": "Renvoie le résumé de la boîte de réception (non lus, derniers expéditeurs).",
        "args": {"account": "string (optionnel, defaults to principal)"},
        "fn": _tool_check_inbox,
    },
    "run_explorer": {
        "description": (
            "Lance un cycle de recherche d'opportunités (SEAO + LinkedIn + Indeed) "
            "en arrière-plan. Si l'utilisateur précise un domaine (ex. mécanicien, "
            "infirmier, transport...), passe-le dans `query` ou `sectors`. "
            "Sinon les secteurs cibles de l'entreprise sont utilisés."
        ),
        "args": {
            "query": "string (optionnel — terme de recherche unique, ex. 'mécanicien Québec')",
            "queries": "list[string] (optionnel — plusieurs requêtes)",
            "sectors": "list[string] (optionnel — secteurs cibles)",
            "profile": "string (optionnel — profil/contexte custom pour le ranking)",
            "hint": "string (optionnel — orientation libre pour le LLM)",
        },
        "fn": _tool_run_explorer,
    },
    "list_opportunities": {
        "description": "Liste les opportunités triées par pertinence.",
        "args": {"statut": "string (optionnel)", "limit": "int (défaut 5)"},
        "fn": _tool_list_opportunities,
    },
    "update_opportunity_status": {
        "description": "Change le statut d'une opportunité (validé, rejeté, en_cours, nouveau).",
        "args": {"id": "string", "statut": "string"},
        "fn": _tool_update_opportunity_status,
    },
    "send_opportunity_draft": {
        "description": "Envoie le brouillon d'email pré-généré pour une opportunité (utilise contact_email).",
        "args": {"id": "string"},
        "fn": _tool_send_opportunity_draft,
    },
    "list_contacts": {
        "description": "Liste les contacts du CRM.",
        "args": {"limit": "int (défaut 10)"},
        "fn": _tool_list_contacts,
    },
    "create_contact": {
        "description": "Crée un nouveau contact dans le CRM.",
        "args": {"nom": "string", "email": "string (optionnel)", "telephone": "string (optionnel)",
                 "poste": "string (optionnel)", "organisation": "string (optionnel)"},
        "fn": _tool_create_contact,
    },
    "set_explorer_interval": {
        "description": "Modifie l'intervalle du cycle automatique d'exploration (en minutes).",
        "args": {"minutes": "int"},
        "fn": _tool_set_explorer_interval,
    },
    "dashboard_stats": {
        "description": "Renvoie les chiffres clés du tableau de bord.",
        "args": {},
        "fn": _tool_dashboard_stats,
    },
}


# ── Système d'invocation ──────────────────────────────────────────────────────

# Pattern : <action>{"tool":"...", "args":{...}}</action>
_ACTION_PATTERN = re.compile(
    r"<action>\s*(\{.*?\})\s*</action>",
    flags=re.DOTALL | re.IGNORECASE,
)


def extract_action(text: str) -> tuple[str, dict[str, Any]] | None:
    """Cherche un bloc <action>{...}</action> et le parse."""
    match = _ACTION_PATTERN.search(text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    tool = payload.get("tool") or payload.get("name")
    args = payload.get("args") or payload.get("arguments") or {}
    if not tool or not isinstance(args, dict):
        return None
    return tool, args


async def invoke_tool(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    entry = TOOLS.get(tool)
    if not entry:
        return {"ok": False, "error": f"Outil inconnu : {tool}"}
    try:
        return await entry["fn"](args)
    except Exception as exc:
        logger.exception("Erreur outil %s", tool)
        return {"ok": False, "error": str(exc)}


def tools_system_prompt() -> str:
    """Bloc à injecter dans le system prompt pour expliquer comment appeler les outils."""
    lines = [
        "## OUTILS DISPONIBLES",
        "Tu peux exécuter des actions dans l'application en émettant un bloc dans ta réponse :",
        "",
        '<action>{"tool": "NOM_OUTIL", "args": {...}}</action>',
        "",
        "Règles :",
        "- N'utilise un outil QUE si l'utilisateur le demande explicitement (envoyer un email, lancer une recherche, etc.).",
        "- Émets UN SEUL bloc <action> par réponse. Continue ta réponse normalement après.",
        "- Le résultat te sera renvoyé via un message système ; tu pourras alors confirmer à l'utilisateur.",
        "- Pour les questions de pure consultation, réponds directement avec les données déjà fournies dans le contexte.",
        "",
        "Outils disponibles :",
    ]
    for name, meta in TOOLS.items():
        args_desc = ", ".join(f"{k}={v}" for k, v in meta["args"].items()) if meta["args"] else "aucun"
        lines.append(f"- `{name}` — {meta['description']}  (args : {args_desc})")
    return "\n".join(lines)
