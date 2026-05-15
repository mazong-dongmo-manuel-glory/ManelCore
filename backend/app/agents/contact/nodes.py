from __future__ import annotations

import os
from typing import Any, Dict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.database.connection import Neo4jConnection
from app.database.repository import GraphRepository
from app.services.mailer import MailerService

from .state import ContactState


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("MODEL", "google/gemma-4-e4b"),
        base_url=os.getenv("MODEL_BASE_URL", "http://localhost:1234/v1"),
        api_key=os.getenv("API_KEY", "lm-studio"),
        max_tokens=1500,
    )


def _load_opportunity(opp_id: str) -> dict[str, Any]:
    """Fetch full opportunity details from Neo4j."""
    if not opp_id:
        return {}
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            node = repo.get_node("Opportunite", opp_id)
            return node or {}
    except Exception:
        return {}


def _load_company_context() -> dict[str, Any]:
    """Load Entreprise + ProfilEntreprise from Neo4j."""
    ctx: dict[str, Any] = {}
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            entreprises = repo.find_nodes("Entreprise", limit=1)
            if entreprises:
                ctx.update(entreprises[0])
            profils = repo.find_nodes("ProfilEntreprise", limit=1)
            if profils:
                ctx["profil"] = profils[0]
    except Exception:
        pass
    return ctx


async def fetch_history(state: ContactState) -> Dict[str, Any]:
    """Fetch full opportunity details, company context, and past interactions from Neo4j."""
    history: list[dict] = []
    opp_id = state.get("opportunity_id", "")

    # Load opportunity details
    opp_details = _load_opportunity(opp_id)

    # Load company context
    company_ctx = _load_company_context()

    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            convs = repo.get_related_nodes(
                "Opportunite", opp_id, "A_CONVERSATION", "Conversation", limit=5
            )
            for conv in convs:
                conv_id = conv.get("node", {}).get("id") or conv.get("id", "")
                if conv_id:
                    msgs = repo.get_related_nodes(
                        "Conversation", conv_id, "CONTIENT", "Message", limit=10
                    )
                    history.extend(
                        {
                            "canal": m.get("node", {}).get("canal", ""),
                            "sujet": m.get("node", {}).get("sujet", ""),
                            "contenu": m.get("node", {}).get("contenu", ""),
                            "direction": m.get("node", {}).get("direction", ""),
                            "date_envoi": m.get("node", {}).get("date_envoi", ""),
                        }
                        for m in msgs
                    )
    except Exception as exc:
        return {
            "opportunity_details": opp_details,
            "company_context": company_ctx,
            "conversation_history": [],
            "error": f"fetch_history: {exc}",
            "messages": [HumanMessage(content=f"Erreur chargement historique: {exc}")],
        }

    return {
        "opportunity_details": opp_details,
        "company_context": company_ctx,
        "conversation_history": history,
    }


async def draft_response(state: ContactState) -> Dict[str, Any]:
    """Draft a detailed, context-rich professional outreach email using the LLM."""
    llm = _get_llm()
    contact = state.get("contact_info", {})
    history = state.get("conversation_history", [])
    opp = state.get("opportunity_details", {})
    company = state.get("company_context", {})
    profil = company.get("profil", {})

    # Build opportunity context block
    opp_lines = []
    if opp.get("titre"):
        opp_lines.append(f"Titre: {opp['titre']}")
    if opp.get("organisation"):
        opp_lines.append(f"Organisation: {opp['organisation']}")
    if opp.get("type"):
        opp_lines.append(f"Type: {opp['type']}")
    if opp.get("source"):
        opp_lines.append(f"Source: {opp['source']}")
    if opp.get("date_limite"):
        opp_lines.append(f"Date limite: {opp['date_limite']}")
    if opp.get("budget"):
        opp_lines.append(f"Budget: {opp['budget']}")
    if opp.get("resume"):
        opp_lines.append(f"Résumé: {opp['resume']}")
    if opp.get("exigences"):
        opp_lines.append(f"Exigences: {opp['exigences']}")
    if opp.get("url"):
        opp_lines.append(f"URL: {opp['url']}")
    opp_context = "\n".join(opp_lines) if opp_lines else f"ID: {state.get('opportunity_id', 'N/A')}"

    # Build company context block
    company_name = company.get("nom", "Manel Canada")
    company_lines = [f"Entreprise: {company_name}"]
    if company.get("description"):
        company_lines.append(f"Description: {company.get('description')}")
    if profil.get("services"):
        company_lines.append(f"Services: {profil['services']}")
    if profil.get("points_forts"):
        company_lines.append(f"Points forts: {profil['points_forts']}")
    if profil.get("resume"):
        company_lines.append(f"Profil analytique: {profil['resume']}")
    company_context = "\n".join(company_lines)

    # Build history block
    history_text = (
        "\n".join(
            f"- [{m.get('direction', '?')}] {m.get('date_envoi', '')[:10]} | "
            f"Sujet: {m.get('sujet', '')} | {m.get('contenu', '')[:300]}"
            for m in history
        )
        or "Aucun échange précédent."
    )

    contact_name = contact.get("nom", "Madame/Monsieur")
    contact_org = contact.get("organisation", "votre organisation")
    contact_poste = contact.get("poste", "")

    prompt = (
        f"Tu es l'assistant de développement des affaires de {company_name}.\n\n"
        f"=== NOTRE ENTREPRISE ===\n{company_context}\n\n"
        f"=== OPPORTUNITÉ CIBLÉE ===\n{opp_context}\n\n"
        f"=== CONTACT ===\n"
        f"Nom: {contact_name}\n"
        f"Organisation: {contact_org}\n"
        + (f"Poste: {contact_poste}\n" if contact_poste else "")
        + f"\n=== HISTORIQUE DES ÉCHANGES ===\n{history_text}\n\n"
        "Rédige un courriel professionnel, personnalisé et convaincant en français qui:\n"
        "1. Commence par une accroche personnalisée selon l'opportunité et l'organisation\n"
        "2. Présente {company_name} en liant spécifiquement nos services aux besoins de l'opportunité\n"
        "3. Met en valeur 2-3 points forts ou réalisations pertinentes de notre entreprise\n"
        "4. Propose une prochaine étape concrète (appel de 20 min, démo, rencontre virtuelle)\n"
        "5. Se termine par une formule de politesse chaleureuse et professionnelle\n\n"
        "IMPORTANT:\n"
        "- Ton chaleureux mais professionnel, pas trop formel\n"
        "- Paragraphes courts et lisibles\n"
        "- Maximum 250 mots dans le corps\n"
        "- Commence par: Objet: [sujet accrocheur et précis]\n"
        "- Puis une ligne vide, puis le corps du courriel"
    ).format(company_name=company_name)

    try:
        response = await llm.ainvoke(prompt)
        draft = response.content.strip()
        return {"draft_email": draft, "status": "awaiting_approval"}
    except Exception as exc:
        return {
            "draft_email": "",
            "status": "error",
            "error": f"draft_response: {exc}",
            "messages": [HumanMessage(content=f"Erreur génération courriel: {exc}")],
        }


async def send_email(state: ContactState) -> Dict[str, Any]:
    """Send the approved draft via SMTP and persist the message to Neo4j."""
    if not state.get("approved", False):
        return {"status": "awaiting_approval"}

    contact = state.get("contact_info", {})
    to_email = contact.get("email", "")
    if not to_email:
        return {
            "status": "error",
            "error": "send_email: adresse courriel du contact manquante",
        }

    draft = state.get("draft_email", "")
    lines = draft.split("\n", 2)
    subject = lines[0].replace("Objet:", "").strip() if lines else "Opportunité de collaboration"
    body = "\n".join(lines[2:]).strip() if len(lines) > 2 else draft

    # Determine sender — use HR email if this is a candidature context
    mailer_email = os.getenv("MAILER_EMAIL", "")
    mailer_password = os.getenv("MAILER_PASSWORD", "")
    mailer_imap = os.getenv("MAILER_IMAP_SERVER", "")

    try:
        mailer = MailerService(
            email=mailer_email,
            password=mailer_password,
            imap_server=mailer_imap,
        )
        mailer.send(to=to_email, subject=subject, body=body)
    except Exception as exc:
        return {
            "status": "error",
            "error": f"send_email SMTP: {exc}",
            "messages": [HumanMessage(content=f"Échec envoi courriel: {exc}")],
        }

    # Persist to Neo4j
    opp = state.get("opportunity_details", {})
    try:
        with Neo4jConnection() as conn:
            repo = GraphRepository(conn)
            repo.upsert_message(
                {
                    "canal": "email",
                    "sujet": subject,
                    "contenu": body[:2000],
                    "direction": "sortant",
                    "intent": "prospection",
                }
            )
    except Exception:
        pass

    return {
        "status": "sent",
        "messages": [HumanMessage(
            content=f"Courriel «{subject}» envoyé à {to_email} "
                    f"(opportunité: {opp.get('titre', state.get('opportunity_id', '?'))})."
        )],
    }
