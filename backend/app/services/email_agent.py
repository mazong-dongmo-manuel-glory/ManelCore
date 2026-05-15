from __future__ import annotations

"""Email Agent Service — lit, classifie, répond automatiquement aux emails entrants.

Pipeline pour chaque email non lu:
  1. Fetch via IMAP (compte principal ou RH selon la boîte)
  2. Classifie avec LLM → lead | spam | urgent | general | candidature
  3. Rédige une réponse automatique si pertinent
  4. Envoie automatiquement pour les candidatures et les leads urgents
  5. Persiste Conversation + Message nodes dans Neo4j
  6. Notifie Telegram si configuré
  7. Marque comme traité pour éviter le retraitement
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

from app.database.connection import Neo4jConnection
from app.database.repository import GraphRepository
from app.services.mailer import MailerService

logger = logging.getLogger(__name__)

_PROCESSED_UIDS: set[str] = set()
_PROCESSED_HR_UIDS: set[str] = set()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _llm_url() -> str:
    return os.getenv("MODEL_BASE_URL", "http://localhost:1234/v1").rstrip("/") + "/chat/completions"


def _llm_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.getenv('API_KEY', 'lm-studio')}",
        "Content-Type": "application/json",
    }


async def _llm_call(prompt: str, max_tokens: int = 1000) -> str:
    payload = {
        "model": os.getenv("MODEL", "google/gemma-4-e4b"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.15,
        "max_tokens": max_tokens,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(_llm_url(), headers=_llm_headers(), json=payload)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        return ""


async def _classify_email(email: dict[str, Any], company_name: str, company_services: str = "") -> dict[str, Any]:
    """Classify an incoming email and draft a reply if relevant."""
    services_context = f"\nServices de l'entreprise: {company_services}" if company_services else ""

    prompt = (
        f"Tu es l'assistant email de {company_name}.{services_context}\n\n"
        f"Email reçu:\n"
        f"De: {email.get('from', '')}\n"
        f"Objet: {email.get('subject', '')}\n"
        f"Corps: {str(email.get('text', ''))[:2000]}\n\n"
        "Analyse cet email et retourne UNIQUEMENT un JSON valide avec ces champs:\n"
        '{\n'
        '  "classification": "lead|spam|urgent|general|candidature",\n'
        '  "should_reply": true|false,\n'
        '  "auto_send": true|false,\n'
        '  "summary": "résumé analytique en 2-3 phrases",\n'
        '  "draft_subject": "objet de réponse si applicable",\n'
        '  "draft_body": "corps de réponse complet et professionnel si applicable",\n'
        '  "rationale": "raison courte de la classification",\n'
        '  "sender_name": "nom de l\'expéditeur si détectable",\n'
        '  "priority": "haute|normale|basse"\n'
        '}\n\n'
        "Règles de classification:\n"
        "- candidature: email de candidature à un poste, CV reçu, demande d'emploi → auto_send=true\n"
        "- lead: prospect intéressé par nos services → should_reply=true, auto_send=false\n"
        "- urgent: demande urgente d'un client existant → should_reply=true, auto_send=true\n"
        "- general: échange courant, info générale → should_reply selon contexte\n"
        "- spam: publicité non sollicitée, phishing → should_reply=false, auto_send=false\n\n"
        "Pour draft_body: rédige une réponse complète, professionnelle et chaleureuse en français. "
        "Pour les candidatures: accuse réception, remercie, explique le processus de sélection."
    )
    content = await _llm_call(prompt, max_tokens=1200)
    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(content[start: end + 1])
        except Exception:
            pass
    return {
        "classification": "general",
        "should_reply": False,
        "auto_send": False,
        "summary": email.get("subject", ""),
        "draft_subject": "",
        "draft_body": "",
        "rationale": "Parsing failed",
        "sender_name": "",
        "priority": "normale",
    }


def _save_email_to_neo4j(
    email: dict[str, Any],
    result: dict[str, Any],
    account_type: str = "principal",
) -> str:
    """Persist complete email data to Neo4j with all relationships.

    Graph créé:
      (Contact) -[:PARTICIPE]-> (Conversation)
      (Conversation) -[:CONTIENT]-> (Message entrant)
      (Conversation) -[:CONTIENT]-> (Message brouillon, si applicable)
      (Candidature) -[:SOUMISE_PAR]-> (Contact), si classification=candidature
    """
    conv_id = str(uuid4())
    msg_id = str(uuid4())
    now = _utc_now()

    # ── Extraire les métadonnées expéditeur ───────────────────────────────────
    sender_raw = email.get("from", "")
    from_values = email.get("from_values", {})
    sender_email_addr = from_values.get("email") or _extract_email_address(sender_raw) or sender_raw
    sender_name = (
        result.get("sender_name")
        or from_values.get("name")
        or sender_raw.split("<")[0].strip()
        or sender_email_addr
    )

    # ── Destinataires et CC ───────────────────────────────────────────────────
    to_list = email.get("to", [])
    cc_list = email.get("cc", [])
    to_email_str = ", ".join(str(t) for t in to_list) if to_list else ""
    cc_email_str = ", ".join(str(c) for c in cc_list) if cc_list else ""
    reply_to_str = ", ".join(str(r) for r in email.get("reply_to", []))

    # ── Pièces jointes ────────────────────────────────────────────────────────
    attachments = email.get("attachments", [])
    attachment_names = ", ".join(a.get("filename", "") for a in attachments if a.get("filename"))

    # ── Corps complet (texte + HTML conservés) ────────────────────────────────
    body_text = email.get("text", "")
    body_html = email.get("html", "")

    with Neo4jConnection() as conn:
        repo = GraphRepository(conn)

        # ── 1. Contact expéditeur ─────────────────────────────────────────────
        contact_node = repo.upsert_contact({
            "nom":              sender_name,
            "email":            sender_email_addr,
            "source":           f"email_entrant_{account_type}",
            "niveau_importance": (
                "haute" if result.get("classification") in ("lead", "urgent", "candidature")
                else "normale"
            ),
        })
        contact_id = contact_node.get("id", "")

        # ── 2. Conversation ───────────────────────────────────────────────────
        repo.upsert_conversation({
            "id":         conv_id,
            "canal":      "email",
            "statut":     result.get("classification", "general"),
            "sujet":      email.get("subject", ""),
            "created_at": now,
            "updated_at": now,
        })

        # ── 3. Message entrant (données complètes) ────────────────────────────
        repo.upsert_message({
            "id":               msg_id,
            "canal":            "email",
            "sujet":            email.get("subject", ""),
            "contenu":          body_text,          # corps complet, pas tronqué
            "contenu_html":     body_html,
            "direction":        "entrant",
            "date_envoi":       email.get("date", now),
            "intent":           result.get("classification", "general"),
            "sentiment":        result.get("rationale", ""),
            "resume_ia":        result.get("summary", ""),
            "from_email":       sender_email_addr,
            "from_name":        sender_name,
            "to_email":         to_email_str,
            "cc_email":         cc_email_str,
            "reply_to":         reply_to_str,
            "message_id_header": email.get("message_id", ""),
            "in_reply_to":      email.get("in_reply_to", ""),
            "uid_imap":         str(email.get("uid", "")),
            "priorite":         result.get("priority", "normale"),
            "classification":   result.get("classification", "general"),
            "auto_replied":     False,
            "compte_recepteur": account_type,
            "has_attachments":  bool(attachments),
            "attachment_names": attachment_names,
            "taille_octets":    email.get("size", 0),
        })

        # ── 4. Relations Conversation → Contact / Conversation → Message ─────────
        # Sens : Conversation -[:IMPLIQUE]-> Contact  (requêtable depuis la conv)
        if contact_id:
            repo.create_relationship(
                "Conversation", conv_id,
                "IMPLIQUE",
                "Contact", contact_id,
                {"role": "expediteur", "created_at": now},
            )
        repo.create_relationship(
            "Conversation", conv_id,
            "CONTIENT",
            "Message", msg_id,
            {"ordre": 1, "created_at": now},
        )

        # ── 5. Brouillon de réponse (si applicable) ───────────────────────────
        if result.get("should_reply") and result.get("draft_body"):
            draft_id = str(uuid4())
            repo.upsert_message({
                "id":             draft_id,
                "canal":          "email",
                "sujet":          result.get("draft_subject", "Re: " + email.get("subject", "")),
                "contenu":        result.get("draft_body", ""),
                "direction":      "brouillon",
                "date_envoi":     now,
                "intent":         result.get("classification", "general"),
                "from_email":     "",        # sera rempli à l'envoi
                "to_email":       sender_email_addr,
                "classification": result.get("classification", "general"),
                "auto_replied":   result.get("auto_send", False),
                "compte_recepteur": account_type,
            })
            repo.create_relationship(
                "Conversation", conv_id,
                "CONTIENT",
                "Message", draft_id,
                {"ordre": 2, "created_at": now},
            )

        # ── 6. Nœud Candidature pour les RH ──────────────────────────────────
        if result.get("classification") == "candidature":
            candidature_node = repo.upsert_candidature({
                "statut":          "nouveau",
                "date_soumission": now,
                "note_interne":    result.get("summary", ""),
                "proposition":     email.get("subject", ""),
            })
            cand_id = candidature_node.get("id", "")
            if cand_id and contact_id:
                repo.create_relationship(
                    "Candidature", cand_id,
                    "SOUMISE_PAR",
                    "Contact", contact_id,
                    {"created_at": now},
                )
            if cand_id:
                repo.create_relationship(
                    "Conversation", conv_id,
                    "CONCERNE",
                    "Candidature", cand_id,
                    {"created_at": now},
                )

    return conv_id


class EmailAgentService:
    """Orchestrates the full email automation pipeline for multiple accounts."""

    def __init__(self) -> None:
        self._running = False

    def _make_mailer(self, account: str = "principal") -> MailerService | None:
        """Build a MailerService for 'principal', 'hr', or 'company' account."""
        if account == "hr":
            email = os.getenv("MAILER_HR_EMAIL", "")
            password = os.getenv("MAILER_HR_PASSWORD", "")
            imap = os.getenv("MAILER_HR_IMAP_SERVER", os.getenv("MAILER_IMAP_SERVER", ""))
        elif account == "company":
            email = os.getenv("MAILER_COMPANY_EMAIL", os.getenv("MAILER_EMAIL", ""))
            password = os.getenv("MAILER_COMPANY_PASSWORD", os.getenv("MAILER_PASSWORD", ""))
            imap = os.getenv("MAILER_COMPANY_IMAP_SERVER", os.getenv("MAILER_IMAP_SERVER", ""))
        else:
            email = os.getenv("MAILER_EMAIL", "")
            password = os.getenv("MAILER_PASSWORD", "")
            imap = os.getenv("MAILER_IMAP_SERVER", "")

        if not (email and password and imap):
            return None
        return MailerService(email=email, password=password, imap_server=imap)

    def _get_company_context(self) -> dict[str, str]:
        ctx = {"name": "ManelCore", "services": ""}
        try:
            with Neo4jConnection() as conn:
                repo = GraphRepository(conn)
                entreprises = repo.find_nodes("Entreprise", limit=1)
                if entreprises:
                    ctx["name"] = entreprises[0].get("nom", "ManelCore")
                profils = repo.find_nodes("ProfilEntreprise", limit=1)
                if profils:
                    ctx["services"] = profils[0].get("services", "")
        except Exception:
            pass
        return ctx

    async def _send_auto_reply(
        self,
        mailer: MailerService,
        to_email: str,
        subject: str,
        body: str,
        conv_id: str,
        classification: str = "general",
        account_type: str = "principal",
    ) -> None:
        """Send auto-reply, persist the outbound message, and link it to the conversation."""
        now = _utc_now()
        try:
            await asyncio.to_thread(mailer.send, to_email, subject, body)
            sent_id = str(uuid4())
            with Neo4jConnection() as conn:
                repo = GraphRepository(conn)
                repo.upsert_message({
                    "id":               sent_id,
                    "canal":            "email",
                    "sujet":            subject,
                    "contenu":          body,
                    "direction":        "sortant",
                    "date_envoi":       now,
                    "intent":           "reponse_automatique",
                    "classification":   classification,
                    "auto_replied":     True,
                    "to_email":         to_email,
                    "from_email":       mailer.email,
                    "compte_recepteur": account_type,
                })
                # Lier le message envoyé à la conversation
                repo.create_relationship(
                    "Conversation", conv_id,
                    "CONTIENT",
                    "Message", sent_id,
                    {"ordre": 99, "created_at": now},
                )
            logger.info("Auto-reply sent to %s (conv %s)", to_email, conv_id)
        except Exception as exc:
            logger.error("Auto-reply failed to %s: %s", to_email, exc)

    async def check_inbox(self, account: str = "principal") -> list[dict[str, Any]]:
        """
        Fetch unread emails, classify each, auto-send replies when appropriate.
        Returns list of processed email summaries.
        """
        mailer = self._make_mailer(account)
        if mailer is None:
            logger.warning("Email account '%s' not configured — skipping.", account)
            return []

        processed_set = _PROCESSED_HR_UIDS if account == "hr" else _PROCESSED_UIDS
        company_ctx = self._get_company_context()

        try:
            emails = await asyncio.to_thread(mailer.fetch_unread, 20)
        except Exception as exc:
            err_msg = str(exc)
            if "nodename nor servname provided" in err_msg or "getaddrinfo failed" in err_msg:
                logger.error("IMAP fetch failed (%s): Serveur IMAP introuvable. Vérifiez MAILER_IMAP_SERVER dans votre .env.", account)
            else:
                logger.error("IMAP fetch failed (%s): %s", account, repr(exc))
            return []

        results: list[dict[str, Any]] = []
        for email in emails:
            uid = email.get("uid", "")
            if uid in processed_set:
                continue

            try:
                result = await _classify_email(
                    email,
                    company_ctx["name"],
                    company_ctx["services"],
                )
                conv_id = _save_email_to_neo4j(email, result, account_type=account)
                processed_set.add(uid)

                # Auto-send reply for candidatures and urgent emails
                sender = email.get("from", "")
                sender_address = _extract_email_address(sender)
                classification = result.get("classification", "general")
                should_auto_send = (
                    result.get("auto_send", False)
                    and result.get("draft_body", "")
                    and sender_address
                    and classification in ("candidature", "urgent")
                )

                if should_auto_send:
                    reply_subject = result.get(
                        "draft_subject",
                        "Re: " + email.get("subject", ""),
                    )
                    # Candidatures reply from HR account if configured
                    reply_mailer = mailer
                    if classification == "candidature":
                        hr_mailer = self._make_mailer("hr")
                        if hr_mailer:
                            reply_mailer = hr_mailer

                    await self._send_auto_reply(
                        reply_mailer,
                        sender_address,
                        reply_subject,
                        result["draft_body"],
                        conv_id,
                        classification=classification,
                        account_type="hr" if classification == "candidature" and self._make_mailer("hr") else account,
                    )

                results.append({
                    "uid": uid,
                    "from": sender,
                    "subject": email.get("subject", ""),
                    "classification": classification,
                    "priority": result.get("priority", "normale"),
                    "should_reply": result.get("should_reply", False),
                    "auto_sent": should_auto_send,
                    "summary": result.get("summary", ""),
                    "conv_id": conv_id,
                    "account": account,
                })
                logger.info(
                    "Processed email uid=%s account=%s classification=%s auto_sent=%s",
                    uid, account, classification, should_auto_send,
                )
            except Exception as exc:
                logger.error("Failed to process email uid=%s account=%s: %s", uid, account, exc)

        return results

    async def check_all_inboxes(self) -> list[dict[str, Any]]:
        """Check all configured email accounts."""
        tasks = [self.check_inbox("principal")]
        if os.getenv("MAILER_HR_EMAIL"):
            tasks.append(self.check_inbox("hr"))
        if os.getenv("MAILER_COMPANY_EMAIL") and os.getenv("MAILER_COMPANY_EMAIL") != os.getenv("MAILER_EMAIL"):
            tasks.append(self.check_inbox("company"))

        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        combined: list[dict[str, Any]] = []
        for r in all_results:
            if isinstance(r, list):
                combined.extend(r)
        return combined

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        account: str = "principal",
    ) -> bool:
        """Send an email via SMTP from the specified account. Returns True on success."""
        mailer = self._make_mailer(account)
        if mailer is None:
            return False
        try:
            await asyncio.to_thread(mailer.send, to, subject, body)
            with Neo4jConnection() as conn:
                repo = GraphRepository(conn)
                repo.upsert_message({
                    "canal": "email",
                    "sujet": subject,
                    "contenu": body[:3000],
                    "direction": "sortant",
                    "date_envoi": _utc_now(),
                    "intent": "prospection",
                })
            return True
        except Exception as exc:
            logger.error("Send email failed (%s): %s", account, exc)
            return False

    async def get_inbox_summary(self, account: str = "principal") -> dict[str, Any]:
        """Return a lightweight inbox status."""
        mailer = self._make_mailer(account)
        if mailer is None:
            return {"configured": False, "account": account, "unread": 0, "emails": []}
        try:
            emails = await asyncio.to_thread(mailer.fetch_unread, 5)
            return {
                "configured": True,
                "account": account,
                "unread": len(emails),
                "emails": [
                    {"from": e.get("from", ""), "subject": e.get("subject", ""), "date": e.get("date", "")}
                    for e in emails[:5]
                ],
            }
        except Exception as exc:
            return {"configured": True, "account": account, "unread": 0, "emails": [], "error": str(exc)}

    # ── Background polling loop ───────────────────────────────────────────────

    async def start_background_loop(self, interval_minutes: int = 5) -> None:
        """Poll all configured inboxes every `interval_minutes`."""
        self._running = True
        logger.info("Email agent background loop started (every %d min).", interval_minutes)
        while self._running:
            try:
                processed = await self.check_all_inboxes()
                if processed:
                    logger.info("Email agent: processed %d new email(s).", len(processed))
                    for item in processed:
                        if item.get("auto_sent"):
                            logger.info(
                                "Auto-reply sent: account=%s from=%s subject=%s",
                                item.get("account"), item.get("from"), item.get("subject"),
                            )
            except Exception as exc:
                logger.error("Email agent loop error: %s", exc)
            await asyncio.sleep(interval_minutes * 60)

    def stop(self) -> None:
        self._running = False


def _extract_email_address(raw: str) -> str:
    """Extract clean email address from 'Name <email>' or plain 'email' string."""
    match = re.search(r'<([^>]+)>', raw)
    if match:
        return match.group(1).strip()
    raw = raw.strip()
    if "@" in raw:
        return raw
    return ""


# Singleton
_email_agent = EmailAgentService()


def get_email_agent() -> EmailAgentService:
    return _email_agent
