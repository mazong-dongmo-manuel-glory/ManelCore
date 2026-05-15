from __future__ import annotations

"""Graph RAG service — retrieves structured context from Neo4j before LLM calls.

The goal is to ground ARIA's answers in real company data instead of relying
on generic training knowledge. For every user message we:
  1. Pull the company profile + sectors.
  2. Find the most relevant opportunities (keyword overlap with the message).
  3. Add recent contacts, email stats, and candidate data.
  4. Return a rich system prompt block the chat endpoint injects before the
     conversation history.
"""

import re
from typing import Any

from app.database.connection import Neo4jConnection
from app.database.repository import GraphRepository

# Keywords that suggest the user is asking about emails
_EMAIL_KEYWORDS = {"mail", "email", "courriel", "inbox", "boîte", "reçu", "message",
                   "nouveau", "unread", "réception", "reply", "répondre", "envoyer"}


# ── helpers ───────────────────────────────────────────────────────────────────

def _keywords(text: str) -> set[str]:
    """Extract meaningful French/English keywords (length > 3)."""
    words = re.findall(r"[a-zA-ZÀ-ÿ]{4,}", text.lower())
    stopwords = {
        "pour", "dans", "avec", "vous", "nous", "être", "cette",
        "comment", "quels", "quelles", "votre", "notre", "plus",
        "bien", "quel", "quelle", "peut", "sont", "tout", "from",
        "that", "this", "with", "have", "what", "which", "your",
    }
    return {w for w in words if w not in stopwords}


def _score_opp(opp: dict[str, Any], keywords: set[str]) -> float:
    """Score an opportunity by keyword overlap with the user query."""
    text = " ".join(
        str(opp.get(f, "")).lower()
        for f in ("titre", "organisation", "resume", "type", "source")
    )
    hits = sum(1 for kw in keywords if kw in text)
    base = float(opp.get("score_pertinence") or 0.0)
    return hits + base


# ── main service ──────────────────────────────────────────────────────────────

class RagService:
    """Builds a context block from Neo4j for a given user message."""

    def build_context(self, user_message: str) -> dict[str, Any]:
        """
        Returns a dict:
          system_block  — multi-line string to inject as system prompt
          sources       — list of node types that were retrieved (for the UI badge)
          opps_count    — number of opportunities included
        """
        keywords = _keywords(user_message)
        live_inbox: dict[str, Any] = {}

        # If the user is asking about emails, fetch live inbox
        if keywords & _EMAIL_KEYWORDS:
            try:
                from app.services.email_agent import get_email_agent
                import asyncio
                agent = get_email_agent()
                live_inbox = asyncio.get_event_loop().run_until_complete(
                    agent.get_inbox_summary()
                )
            except Exception:
                pass

        try:
            with Neo4jConnection() as conn:
                repo = GraphRepository(conn)
                company   = self._get_company(repo)
                opps      = self._get_opportunities(repo, keywords)
                contacts  = self._get_contacts(repo)
                candidats = self._get_candidats(repo)
                messages  = self._get_messages(repo)
                stats     = self._compute_stats(repo)
        except Exception as exc:
            return {
                "system_block": f"[Avertissement: impossible de charger le contexte Neo4j — {exc}]",
                "sources": [],
                "opps_count": 0,
            }

        block = self._format_block(company, opps, contacts, candidats, messages, stats, live_inbox)
        sources = []
        if company.get("nom"):     sources.append("entreprise")
        if opps:                   sources.append("opportunités")
        if contacts:               sources.append("contacts")
        if candidats:              sources.append("candidats")
        if messages or live_inbox: sources.append("emails")

        return {
            "system_block": block,
            "sources": sources,
            "opps_count": len(opps),
        }

    # ── Neo4j queries ─────────────────────────────────────────────────────────

    def _get_company(self, repo: GraphRepository) -> dict[str, Any]:
        entreprises = repo.find_nodes("Entreprise", limit=1)
        profils = repo.find_nodes("ProfilEntreprise", limit=1)
        c: dict[str, Any] = entreprises[0] if entreprises else {}
        if profils:
            c = {**c, **profils[0]}
        # Sectors
        sectors = repo.find_nodes("Secteur", limit=20)
        c["secteurs"] = [s.get("nom", "") for s in sectors if s.get("nom")]
        return c

    def _get_opportunities(self, repo: GraphRepository, keywords: set[str], top_n: int = 15) -> list[dict[str, Any]]:
        all_opps = repo.find_nodes("Opportunite", sort_by="score_pertinence", descending=True, limit=100)
        if keywords:
            scored = sorted(all_opps, key=lambda o: _score_opp(o, keywords), reverse=True)
        else:
            scored = all_opps
        return scored[:top_n]

    def _get_contacts(self, repo: GraphRepository) -> list[dict[str, Any]]:
        return repo.find_nodes("Contact", limit=15)

    def _get_candidats(self, repo: GraphRepository) -> list[dict[str, Any]]:
        return repo.find_nodes("Candidature", limit=10)

    def _get_messages(self, repo: GraphRepository) -> list[dict[str, Any]]:
        return repo.find_nodes("Message", limit=20)

    def _compute_stats(self, repo: GraphRepository) -> dict[str, int]:
        opps     = repo.find_nodes("Opportunite", limit=500)
        contacts = repo.find_nodes("Contact", limit=500)
        msgs     = repo.find_nodes("Message", limit=500)
        return {
            "total_opps":   len(opps),
            "validees":     sum(1 for o in opps if o.get("statut") in ("validé", "approuvé")),
            "nouvelles":    sum(1 for o in opps if o.get("statut") == "nouveau"),
            "rejettees":    sum(1 for o in opps if o.get("statut") == "rejeté"),
            "contacts":     len(contacts),
            "emails_envoyes": sum(1 for m in msgs if m.get("direction") == "sortant"),
            "emails_recus":   sum(1 for m in msgs if m.get("direction") == "entrant"),
        }

    # ── context formatter ─────────────────────────────────────────────────────

    def _format_block(
        self,
        company:    dict[str, Any],
        opps:       list[dict[str, Any]],
        contacts:   list[dict[str, Any]],
        candidats:  list[dict[str, Any]],
        messages:   list[dict[str, Any]],
        stats:      dict[str, int],
        live_inbox: dict[str, Any] | None = None,
    ) -> str:
        lines: list[str] = []

        # ── Company profile ──────────────────────────────────────────────────
        lines.append("🏛️ *PROFIL DE L'ENTREPRISE*")
        lines.append(f"• Nom: *{company.get('nom') or 'ManelCore'}*")
        if company.get("description"):
            lines.append(f"• Description: {company['description']}")
        if company.get("secteurs"):
            lines.append(f"• Secteurs cibles: _{', '.join(company['secteurs'])}_")
        if company.get("services"):
            lines.append(f"• Services: {company['services']}")
        if company.get("points_forts"):
            lines.append(f"• Points forts: {company['points_forts']}")
        lines.append("")
        lines.append("")

        # ── Statistics ───────────────────────────────────────────────────────
        lines.append("## STATISTIQUES ACTUELLES")
        lines.append(f"• {stats['total_opps']} opportunités au total  "
                     f"({stats['nouvelles']} nouvelles, {stats['validees']} validées, {stats['rejettees']} rejetées)")
        lines.append(f"• {stats['contacts']} contacts dans le CRM")
        lines.append(f"• {stats['emails_envoyes']} emails envoyés, {stats['emails_recus']} reçus")
        lines.append("")

        # ── Opportunities ────────────────────────────────────────────────────
        # ── Opportunities ────────────────────────────────────────────────────
        if opps:
            lines.append(f"🎯 *OPPORTUNITÉS PERTINENTES* ({len(opps)})")
            for i, o in enumerate(opps[:10], 1):
                titre  = o.get("titre") or "Sans titre"
                org    = o.get("organisation") or "?"
                score  = o.get("score_pertinence")
                score_str = f"{int(float(score) * 100)}%" if score else "—"
                resume = o.get("resume") or ""
                
                lines.append(f"{i}. *{titre}*")
                lines.append(f"   🏢 {org}  |  📊 Pertinence: *{score_str}*")
                if resume:
                    lines.append(f"   📝 {resume[:400]}")
            lines.append("")

        # ── Contacts ─────────────────────────────────────────────────────────
        if contacts:
            lines.append(f"## CONTACTS CRM ({len(contacts)})")
            for c in contacts[:8]:
                nom   = c.get("nom") or "?"
                email = c.get("email") or ""
                poste = c.get("poste") or ""
                org   = c.get("organisation") or ""
                parts = [nom]
                if poste: parts.append(poste)
                if org:   parts.append(org)
                if email: parts.append(f"<{email}>")
                lines.append(f"• {' — '.join(parts)}")
            lines.append("")

        # ── Candidats (RH) ───────────────────────────────────────────────────
        if candidats:
            lines.append(f"## CANDIDATURES RH ({len(candidats)})")
            for c in candidats[:6]:
                nom    = c.get("nom") or "?"
                poste  = c.get("poste") or "?"
                statut = c.get("statut") or "nouveau"
                lines.append(f"• {nom} — {poste} [{statut}]")
            lines.append("")

        # ── Recent emails ────────────────────────────────────────────────────
        if messages:
            lines.append(f"## MESSAGES RÉCENTS ({len(messages)})")
            for m in messages[:5]:
                direction = m.get("direction") or "?"
                sujet     = m.get("sujet") or "Sans sujet"
                intent    = m.get("intent") or ""
                contenu   = m.get("contenu") or ""
                sender    = m.get("from_name") or m.get("from_email") or ""
                
                header = f"• [{direction.upper()}] {sujet}"
                if sender: header += f" de {sender}"
                lines.append(header)
                if contenu:
                    lines.append(f"   Contenu: {contenu[:800]}...")
            lines.append("")

        # ── Live inbox (si demandé) ───────────────────────────────────────────
        if live_inbox:
            if not live_inbox.get("configured"):
                lines.append("## BOÎTE EMAIL")
                lines.append("⚠️ Email non configuré — renseigner les paramètres dans Configuration.")
            elif live_inbox.get("error"):
                lines.append("## BOÎTE EMAIL")
                lines.append(f"⚠️ Erreur IMAP: {live_inbox['error']}")
            else:
                unread = live_inbox.get("unread", 0)
                lines.append(f"## BOÎTE EMAIL EN TEMPS RÉEL ({unread} non lu(s))")
                emails = live_inbox.get("emails", [])
                if emails:
                    for e in emails:
                        lines.append(f"• De: {e.get('from','')} | Objet: {e.get('subject','')} | Date: {e.get('date','')}")
                else:
                    lines.append("• Aucun email non lu.")
                lines.append("")
                lines.append("CAPACITÉS EMAIL:")
                lines.append("• Tu PEUX lire les emails via IMAP et les analyser.")
                lines.append("• Tu PEUX rédiger et envoyer des réponses via SMTP.")
                lines.append("• Les emails entrants sont classifiés et des brouillons sont préparés automatiquement.")
            lines.append("")

        lines.append("=== FIN DE LA BASE DE CONNAISSANCE ===\n")
        lines.append(
            "RÈGLE CRITIQUE: Réponds TOUJOURS en te basant sur ces données réelles. "
            "Si une information n'est pas dans la base de connaissance ci-dessus, "
            "dis-le clairement plutôt que d'inventer. "
            "Formule tes réponses de manière professionnelle et actionnable."
        )

        return "\n".join(lines)
