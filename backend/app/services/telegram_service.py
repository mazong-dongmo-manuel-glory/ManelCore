from __future__ import annotations

import asyncio
import json
import logging
import os
import contextlib
import re

import httpx
import tempfile
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Conflict, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logger = logging.getLogger(__name__)

_API = "http://localhost:8000"
_MAX_MSG = 4000  # Telegram limit is 4096


def _chunk(text: str, size: int = _MAX_MSG) -> list[str]:
    """Split long text into Telegram-safe chunks."""
    return [text[i : i + size] for i in range(0, len(text), size)]


def _match_first(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
    return ""


def _strip_markdown_noise(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = text.replace("***", "").replace("**", "").replace("__", "")
    text = re.sub(r"^\s*[-#]+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n\s*(?:Approuves-tu|Veuillez confirmer|J'ai gardé ce brouillon).*", "", text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()


def _escape_markdown_v2(text: str) -> str:
    """Escapes characters for Telegram MarkdownV2."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)


async def _api(method: str, path: str, **kwargs) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        fn = getattr(client, method)
        r = await fn(f"{_API}{path}", **kwargs)
        r.raise_for_status()
        return r.json()


class TelegramService:
    _active_tokens: set[str] = set()

    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self._app: Application | None = None
        self._conflict_logged = False
        self._chat_memory: dict[str, list[dict[str, str]]] = {}
        self._pending_emails: dict[str, dict[str, str]] = {}

    # ── Envoi de notifications ────────────────────────────────────────────────

    async def send_opportunity_notification(self, chat_id: str, opportunity: dict) -> None:
        if not self.token:
            return
        bot = Bot(token=self.token)
        titre    = opportunity.get("titre") or "Sans titre"
        org      = opportunity.get("organisation") or "?"
        source   = opportunity.get("source", "?")
        score    = opportunity.get("score_pertinence")
        score_str= f"{int(float(score) * 100)}%" if score is not None else "N/A"
        url      = opportunity.get("url", "")
        opp_id   = opportunity.get("id", "")
        resume   = opportunity.get("resume", "")

        try:
            # We use a mix of escaped text and raw markers
            escaped_titre = _escape_markdown_v2(titre[:80])
            escaped_org = _escape_markdown_v2(org)
            escaped_source = _escape_markdown_v2(source)
            escaped_resume = _escape_markdown_v2(resume[:250])
            
            contact_nom = opportunity.get("contact_nom")
            contact_email = opportunity.get("contact_email")
            
            text = (
                "🎯 *Nouvelle Opportunité*\n\n"
                f"📌 *{escaped_titre}*\n"
                f"🏢 {escaped_org}\n"
                f"📡 {escaped_source}  •  📊 {score_str}\n"
            )
            
            if contact_nom or contact_email:
                c_nom = _escape_markdown_v2(contact_nom or "Inconnu")
                c_mail = _escape_markdown_v2(contact_email or "Non spécifié")
                text += f"\n👤 *Contact:* {c_nom} \\({c_mail}\\)\n"

            if resume:
                text += f"\n_{escaped_resume}_\n"
            if url:
                text += f"\n🔗 [Voir l'offre]({url})"

            keyboard = [
                [
                    InlineKeyboardButton("✅ Valider", callback_data=f"val_{opp_id}"),
                    InlineKeyboardButton("❌ Rejeter", callback_data=f"rej_{opp_id}"),
                ]
            ]
            
            if opportunity.get("draft_email") and opportunity.get("contact_email"):
                keyboard.insert(0, [
                    InlineKeyboardButton("📧 Envoyer Email", callback_data=f"send_draft_{opp_id}")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton("📬 Contacter", callback_data=f"contact_{opp_id}")
                ])

            await bot.send_message(chat_id=chat_id, text=text, parse_mode="MarkdownV2",
                                   reply_markup=InlineKeyboardMarkup(keyboard),
                                   disable_web_page_preview=False)
        except Exception as exc:
            logger.error("send_opportunity_notification: %s", exc)

    async def send_email_notification(self, chat_id: str, email: dict, classification: dict) -> None:
        if not self.token:
            return
        bot = Bot(token=self.token)
        tag  = {"lead": "🟢 LEAD", "urgent": "🔴 URGENT", "general": "⚪ Général", "spam": "🚫 Spam"}.get(
            classification.get("classification", "general"), "📧 Email")
        text = (
            f"📧 *Nouvel email — {tag}*\n\n"
            f"*De:* {email.get('from', '?')[:60]}\n"
            f"*Objet:* {email.get('subject', '?')[:80]}\n\n"
            f"_{classification.get('summary', '')[:200]}_"
        )
        keyboard = []
        if classification.get("should_reply") and classification.get("draft_body"):
            keyboard.append([
                InlineKeyboardButton("📤 Envoyer brouillon", callback_data=f"send_draft_{email.get('uid','')}"),
                InlineKeyboardButton("👁 Voir brouillon",    callback_data=f"view_draft_{email.get('uid','')}"),
            ])
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
        except Exception as exc:
            logger.error("send_email_notification: %s", exc)

    async def send_message(self, chat_id: str, text: str) -> None:
        if not self.token:
            return
        bot = Bot(token=self.token)
        for chunk in _chunk(text):
            try:
                # Try MarkdownV2 first with auto-escaping for the whole block
                # Note: this is risky if the block has manual markers. 
                # Better to let the caller handle it or use a simple heuristic.
                await bot.send_message(chat_id=chat_id, text=_escape_markdown_v2(chunk), parse_mode="MarkdownV2")
            except Exception:
                try:
                    await bot.send_message(chat_id=chat_id, text=chunk)
                except Exception as exc:
                    logger.error("ARIA reply error: %s", exc)

    # ── Helpers partagés ─────────────────────────────────────────────────────

    async def _aria_reply(self, chat_id: str, question: str) -> str:
        """Call ARIA (LM Studio + RAG + tools) and return the formatted response.

        Les actions (tool_call/tool_result) sont jointes au texte avec un
        préfixe lisible pour Telegram. Les blocs <action>...</action> bruts
        sont supprimés du texte affiché.
        """
        messages = self._conversation_messages(chat_id)
        pending = self._pending_emails.get(chat_id)
        if pending:
            messages.append({
                "role": "assistant",
                "content": (
                    "Action en attente: un brouillon email attend confirmation. "
                    f"Destinataire: {pending.get('to', '')}. "
                    f"Objet: {pending.get('subject', '')}. "
                    "Si l'utilisateur confirme avec oui/envoie/procède, il faut envoyer ce brouillon."
                ),
            })
        messages.append({"role": "user", "content": question})
        payload  = {"messages": messages, "use_rag": True, "max_tokens": 1000, "temperature": 0.3}
        text_buffer = ""
        actions_log: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream("POST", f"{_API}/chat/stream",
                                         headers={"Content-Type": "application/json"},
                                         content=json.dumps(payload)) as resp:
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw in ("[DONE]", ""):
                            continue
                        try:
                            chunk = json.loads(raw)
                        except Exception:
                            continue
                        if "content" in chunk:
                            text_buffer += chunk["content"]
                        elif "tool_call" in chunk:
                            tool = chunk["tool_call"].get("tool", "?")
                            actions_log.append(f"⚙️ *Action :* `{tool}`")
                        elif "tool_result" in chunk:
                            tr = chunk["tool_result"]
                            res = tr.get("result") or {}
                            ok = res.get("ok", True)
                            msg = res.get("message") or res.get("error") or ""
                            emoji = "✅" if ok else "❌"
                            actions_log.append(f"{emoji} `{tr.get('tool','?')}` — {msg}" if msg else f"{emoji} `{tr.get('tool','?')}`")
        except Exception as exc:
            return f"❌ ARIA indisponible: {exc}"

        # Supprime les blocs <action>{...}</action> du texte visible
        cleaned = re.sub(r"<action>.*?</action>", "", text_buffer, flags=re.DOTALL | re.IGNORECASE).strip()
        parts: list[str] = []
        if actions_log:
            parts.append("\n".join(actions_log))
        if cleaned:
            parts.append(cleaned)
        return "\n\n".join(parts) or "Je n'ai pas pu générer une réponse."

    def _conversation_messages(self, chat_id: str) -> list[dict[str, str]]:
        return list(self._chat_memory.get(chat_id, [])[-10:])

    def _remember(self, chat_id: str, role: str, content: str) -> None:
        history = self._chat_memory.setdefault(chat_id, [])
        history.append({"role": role, "content": content[:2500]})
        del history[:-12]

    @staticmethod
    def _is_confirmation(text: str) -> bool:
        normalized = text.lower().strip()
        return bool(re.search(
            r"\b(oui|ok|d'accord|vas-y|envoi|envoie|envoyer|proc[eè]de|confirme|go|yes)\b",
            normalized,
        ))

    @staticmethod
    def _extract_email_draft(text: str) -> dict[str, str] | None:
        recipient = _match_first(text, [
            r"(?:Destinataire|À|A)\s*:?\s*\*{0,2}\s*([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})",
            r"env(?:oyer|oi)\s+(?:à|a)\s+([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})",
            r"([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})",
        ])
        subject = _match_first(text, [
            r"Objet\s*:?\s*\*{0,2}\s*([^\n\r]+)",
            r"Sujet\s*:?\s*\*{0,2}\s*([^\n\r]+)",
        ])
        if not recipient or not subject:
            return None

        body = ""
        body_match = re.search(
            r"(?:Corps du message|Message|Contenu)\s*:?\s*(.*)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if body_match:
            body = body_match.group(1)
        else:
            bonjour_match = re.search(r"(Bonjour,?.*)", text, flags=re.IGNORECASE | re.DOTALL)
            if bonjour_match:
                body = bonjour_match.group(1)

        body = _strip_markdown_noise(body)
        subject = _strip_markdown_noise(subject).strip(" :")
        if not body:
            return None
        return {"to": recipient, "subject": subject, "body": body}

    async def _send_pending_email(self, chat_id: str, update: Update) -> bool:
        draft = self._pending_emails.get(chat_id)
        if not draft:
            return False
        try:
            result = await _api("post", "/email/send", json={
                "to": draft["to"],
                "subject": draft["subject"],
                "body": draft["body"],
            })
            if result.get("status") == "sent":
                self._pending_emails.pop(chat_id, None)
                await update.message.reply_text(
                    f"📤 Email envoyé à {draft['to']}.\n\nObjet: {draft['subject']}"
                )
                self._remember(chat_id, "assistant", f"Email envoyé à {draft['to']} avec l'objet {draft['subject']}.")
                return True
        except Exception as exc:
            await update.message.reply_text(f"❌ Envoi impossible: {exc}")
            return True
        return False

    # ── Commandes ────────────────────────────────────────────────────────────

    async def _cmd_start(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = str(update.effective_chat.id)
        if not self.chat_id:
            os.environ["TELEGRAM_CHAT_ID"] = chat_id
            self.chat_id = chat_id
        await update.message.reply_text(
            "👋 *ManelCore ARIA* est connecté\\!\n\n"
            "Tu peux m'écrire directement pour poser une question \\(ARIA répond\\) ou utiliser une commande:\n\n"
            "📊 /stats — Tableau de bord rapide\n"
            "📋 /briefing — Résumé exécutif complet\n"
            "🎯 /opportunites — Dernières opportunités\n"
            "📧 /mails — Vérifier la boîte de réception\n"
            "📝 /brouillons — Emails en attente d'envoi\n"
            "👥 /contacts — Contacts récents\n"
            "🚀 /run — Lancer une recherche complète\n"
            "⏲ /frequence <min> — Régler l'intervalle\n"
            "ℹ️ /aide — Aide complète",
            parse_mode="MarkdownV2",
        )

    async def _cmd_stats(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            data = await _api("get", "/dashboard/stats")
            opps      = data.get("opportunities", 0)
            validated = data.get("validated", 0)
            new_opps  = data.get("new", 0)
            emails    = data.get("emails_sent", 0)
            contacts  = data.get("contacts", 0)
            rate      = f"{int(validated/opps*100)}%" if opps > 0 else "—"
            await update.message.reply_text(
                "📊 *TABLEAU DE BORD EXÉCUTIF*\n\n"
                f"🎯 Opportunités: *{opps}* _({new_opps} nouvelles)_\n"
                f"✅ Validées: *{validated}* — _Taux de succès: {rate}_\n"
                f"📧 Emails envoyés: *{emails}*\n"
                f"👥 Contacts CRM: *{contacts}*\n\n"
                "💡 _Conseil: Utilise /briefing pour une analyse détaillée._",
                parse_mode="Markdown",
            )
        except Exception as exc:
            await update.message.reply_text(f"❌ Erreur: {exc}")

    async def _cmd_opportunites(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            data = await _api("get", "/opportunities?limit=5")
            opps = data.get("opportunities", [])
            if not opps:
                await update.message.reply_text("Aucune opportunité pour l'instant.\n\nUtilise /run ou /test pour en créer.")
                return
            lines = [f"🎯 *{len(opps)} opportunités récentes:*\n"]
            for i, o in enumerate(opps, 1):
                titre  = (o.get("titre") or "?")[:55]
                score  = o.get("score_pertinence")
                pct    = f"{int(float(score)*100)}%" if score else "?"
                statut = o.get("statut", "?")
                lines.append(f"{i}\\. *{titre}*\n   📊 {pct}  •  {statut}")
            await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")
        except Exception as exc:
            await update.message.reply_text(f"❌ Erreur: {exc}")

    async def _cmd_mails(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("📬 Vérification de la boîte de réception…")
        try:
            # Trigger check
            await _api("post", "/email/check")
            # Get live summary
            data = await _api("get", "/email/inbox")
            if not data.get("configured"):
                await update.message.reply_text(
                    "⚠️ Email non configuré\\.\nRenseigne IMAP/SMTP dans la page *Configuration* de l'app\\.",
                    parse_mode="MarkdownV2")
                return
            unread = data.get("unread", 0)
            emails = data.get("emails", [])
            if unread == 0:
                await update.message.reply_text("✅ Boîte vide — aucun email non lu.")
                return
            lines = [f"📧 *{unread} email(s) non lu(s)*\n"]
            for e in emails[:5]:
                sender  = (e.get("from") or "?")[:40]
                subject = (e.get("subject") or "?")[:50]
                lines.append(f"• *{sender}*\n  {subject}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception as exc:
            await update.message.reply_text(f"❌ Erreur: {exc}")

    async def _cmd_brouillons(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            data = await _api("get", "/email/messages?limit=20")
            msgs = data.get("messages", [])
            drafts = [m for m in msgs if m.get("direction") == "brouillon"]
            if not drafts:
                await update.message.reply_text("📭 Aucun brouillon en attente.")
                return
            lines = [f"📝 *{len(drafts)} brouillon(s) en attente:*\n"]
            for i, d in enumerate(drafts[:5], 1):
                sujet = (d.get("sujet") or "?")[:60]
                lines.append(f"{i}. {sujet}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception as exc:
            await update.message.reply_text(f"❌ Erreur: {exc}")

    async def _cmd_contacts(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            data = await _api("get", "/contacts?limit=8")
            contacts = data.get("contacts", [])
            if not contacts:
                await update.message.reply_text("👥 Aucun contact dans le CRM.")
                return
            lines = [f"👥 *{len(contacts)} contact(s) récents:*\n"]
            for c in contacts[:8]:
                nom   = c.get("nom") or "?"
                email = c.get("email") or ""
                org   = c.get("organisation") or ""
                detail = " — ".join(filter(None, [org, email]))
                lines.append(f"• *{nom}*{f'  _{detail}_' if detail else ''}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception as exc:
            await update.message.reply_text(f"❌ Erreur: {exc}")

    async def _cmd_run(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("🚀 Lancement de la recherche d'opportunités…")
        try:
            await _api("post", "/agent/run", json={})
            await update.message.reply_text(
                "✅ Agent démarré en arrière-plan\\.\nTu recevras une notification pour chaque opportunité trouvée\\.",
                parse_mode="MarkdownV2")
        except Exception as exc:
            await update.message.reply_text(f"❌ Erreur: {exc}")

    async def _cmd_test(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("🧪 Injection de données de test…")
        try:
            data = await _api("post", "/agent/run/mock", json={})
            count = data.get("count", 0)
            await update.message.reply_text(
                f"✅ *{count} opportunités* injectées dans Neo4j\\!\n"
                "Utilise /opportunites pour les voir\\.",
                parse_mode="MarkdownV2")
        except Exception as exc:
            await update.message.reply_text(f"❌ Erreur: {exc}")

    async def _cmd_briefing(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.chat.send_action("typing")
        try:
            data = await _api("get", "/agent/summary")
            summary = data.get("summary", "Aucun résumé disponible.")
            # The summary from RAG is already formatted in Markdown
            for chunk in _chunk(f"📋 *RÉSUMÉ EXÉCUTIF ARIA*\n\n{summary}"):
                await update.message.reply_text(chunk, parse_mode="Markdown")
        except Exception as exc:
            await update.message.reply_text(f"❌ Erreur: {exc}")

    async def _cmd_frequence(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        args = _context.args
        if not args:
            settings = load_settings()
            current = settings.get("explorer_interval", 30)
            await update.message.reply_text(f"⏲ L'intervalle actuel est de *{current} minutes*.\n\nUtilise `/frequence <minutes>` pour le modifier.", parse_mode="Markdown")
            return
        try:
            minutes = int(args[0])
            if minutes < 5:
                await update.message.reply_text("⚠️ L'intervalle minimum est de 5 minutes.")
                return
            save_settings({"explorer_interval": minutes})
            await update.message.reply_text(f"✅ Intervalle mis à jour : *{minutes} minutes*.", parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("❌ Veuillez entrer un nombre valide (ex: /frequence 60).")

    async def _cmd_aide(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "*ManelCore ARIA — Guide des Commandes*\n\n"
            "📊 */stats* — Dashboard rapide (chiffres clés)\n"
            "📋 */briefing* — Analyse complète de la situation (RAG)\n"
            "🎯 */opportunites* — 5 dernières opportunités avec scores\n"
            "📧 */mails* — État de la boîte IMAP\n"
            "📝 */brouillons* — Emails IA en attente\n"
            "👥 */contacts* — Liste CRM\n"
            "🚀 */run* — Lancer un cycle de recherche\n"
            "⏲ */frequence* — Régler l'intervalle automatique\n"
            "ℹ️ */aide* — Ce guide\n\n"
            "*Mode Conversationnel :*\n"
            "Écris librement pour analyser un dossier, préparer un email ou demander un avis stratégique. ARIA utilise l'ensemble de tes données Neo4j.",
            parse_mode="Markdown",
        )

    # ── Chat libre → ARIA ─────────────────────────────────────────────────────

    async def _handle_message(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        """Route tout texte libre vers ARIA (LM Studio + Graph RAG)."""
        question = (update.message.text or "").strip()
        if not question:
            return
        chat_id = str(update.effective_chat.id)

        if self._is_confirmation(question) and await self._send_pending_email(chat_id, update):
            self._remember(chat_id, "user", question)
            return

        # Indicateur de frappe
        await update.message.chat.send_action("typing")

        reply = await self._aria_reply(chat_id, question)
        self._remember(chat_id, "user", question)
        self._remember(chat_id, "assistant", reply)

        draft = self._extract_email_draft(reply)
        if draft:
            self._pending_emails[chat_id] = draft
            reply = (
                f"{reply}\n\n"
                "J'ai gardé ce brouillon en contexte. Réponds simplement "
                "`oui envoie` pour que je l'envoie."
            )

        for chunk in _chunk(reply):
            try:
                await update.message.reply_text(chunk, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(chunk)

    async def _handle_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Transcrit l'audio et traite le texte résultant."""
        audio = update.message.voice or update.message.audio
        if not audio:
            return

        chat_id = str(update.effective_chat.id)
        
        # Message d'attente
        status_msg = await update.message.reply_text("🎙️ _Transcription en cours..._", parse_mode="Markdown")

        try:
            # Téléchargement
            file = await context.bot.get_file(audio.file_id)
            ext = ".oga" if update.message.voice else os.path.splitext(file.file_path)[1] or ".mp3"
            
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp_path = tmp.name
            
            await file.download_to_drive(tmp_path)

            # Transcription
            from app.services.transcription_service import get_transcription_service
            ts = get_transcription_service()
            text = await ts.transcribe(tmp_path)

            # Nettoyage
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

            # Supprimer le message d'attente
            await status_msg.delete()

            if text.startswith("[Erreur"):
                await update.message.reply_text(f"❌ {text}")
                return

            # Afficher la transcription
            await update.message.reply_text(f"📝 *Transcription :*\n_{text}_", parse_mode="Markdown")

            # Traiter comme un message texte normal
            update.message.text = text
            await self._handle_message(update, context)

        except Exception as exc:
            logger.error(f"Erreur handle_audio: {exc}")
            await status_msg.edit_text(f"❌ Erreur lors du traitement audio: {exc}")

    # ── Callback queries ──────────────────────────────────────────────────────

    async def _handle_callback(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        data = query.data or ""

        # ── Opportunité : envoyer brouillon pré-généré ──────────────────────
        if data.startswith("send_draft_"):
            opp_id = data[11:]
            try:
                res = await _api("post", f"/opportunities/{opp_id}/send-draft")
                await query.edit_message_reply_markup(reply_markup=None)
                await query.message.reply_text(f"🚀 {res.get('message', 'Email envoyé')}")
            except Exception as exc:
                await query.message.reply_text(f"❌ {exc}")

        # ── Opportunité : valider ─────────────────────────────────────────────
        elif data.startswith("val_"):
            opp_id = data[4:]
            try:
                await _api("patch", f"/opportunities/{opp_id}/status", json={"statut": "validé"})
                await query.edit_message_reply_markup(reply_markup=None)
                await query.message.reply_text("✅ Opportunité *validée*.", parse_mode="Markdown")
            except Exception as exc:
                await query.message.reply_text(f"❌ {exc}")

        # ── Opportunité : rejeter ─────────────────────────────────────────────
        elif data.startswith("rej_"):
            opp_id = data[4:]
            try:
                await _api("patch", f"/opportunities/{opp_id}/status", json={"statut": "rejeté"})
                await query.edit_message_reply_markup(reply_markup=None)
                await query.message.reply_text("❌ Opportunité *rejetée*.", parse_mode="Markdown")
            except Exception as exc:
                await query.message.reply_text(f"❌ {exc}")

        # ── Opportunité : contacter (génère un brouillon) ─────────────────────
        elif data.startswith("contact_"):
            opp_id = data[8:]
            await query.message.reply_text("📬 Génération du brouillon d'email…")
            try:
                result = await _api("post", "/contact/draft", json={
                    "opportunity_id": opp_id,
                    "contact_info": {"email": "", "nom": "Responsable", "organisation": ""},
                })
                draft = result.get("draft_email", "")
                if draft:
                    thread_id = result.get("thread_id", "")
                    for chunk in _chunk(f"📝 *Brouillon généré:*\n\n{draft}"):
                        await query.message.reply_text(chunk, parse_mode="Markdown")
                    # Bouton d'envoi
                    keyboard = [[
                        InlineKeyboardButton("📤 Envoyer", callback_data=f"approve_{thread_id}"),
                        InlineKeyboardButton("🗑 Annuler",  callback_data=f"reject_{thread_id}"),
                    ]]
                    await query.message.reply_text(
                        "Approuves-tu l'envoi de ce brouillon ?",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                    )
                else:
                    await query.message.reply_text("⚠️ Le brouillon est vide.")
            except Exception as exc:
                await query.message.reply_text(f"❌ Erreur: {exc}")

        # ── Brouillon email : approuver l'envoi ───────────────────────────────
        elif data.startswith("approve_"):
            thread_id = data[8:]
            try:
                await _api("post", "/contact/approve", json={"thread_id": thread_id, "approved": True})
                await query.edit_message_reply_markup(reply_markup=None)
                await query.message.reply_text("📤 Email *envoyé* avec succès\\!", parse_mode="MarkdownV2")
            except Exception as exc:
                await query.message.reply_text(f"❌ {exc}")

        # ── Brouillon email : rejeter ─────────────────────────────────────────
        elif data.startswith("reject_"):
            thread_id = data[7:]
            try:
                await _api("post", "/contact/approve", json={"thread_id": thread_id, "approved": False})
                await query.edit_message_reply_markup(reply_markup=None)
                await query.message.reply_text("🗑 Brouillon annulé.")
            except Exception as exc:
                await query.message.reply_text(f"❌ {exc}")

        # ── Email entrant : voir brouillon ────────────────────────────────────
        elif data.startswith("view_draft_"):
            try:
                data_msgs = await _api("get", "/email/messages?limit=50")
                drafts = [m for m in data_msgs.get("messages", []) if m.get("direction") == "brouillon"]
                found = drafts[0] if drafts else None
                if found:
                    for chunk in _chunk(f"📝 *Brouillon:*\n\n{found.get('contenu', '')}"):
                        await query.message.reply_text(chunk, parse_mode="Markdown")
                else:
                    await query.message.reply_text("Brouillon introuvable.")
            except Exception as exc:
                await query.message.reply_text(f"❌ {exc}")

    # ── Démarrage du polling ──────────────────────────────────────────────────

    async def start_polling_async(self) -> None:
        if not self.token:
            logger.warning("TELEGRAM_BOT_TOKEN non défini — bot désactivé.")
            return
        if self.token in self._active_tokens:
            logger.info("Bot Telegram déjà actif dans ce process — démarrage ignoré.")
            return
        self._active_tokens.add(self.token)
        try:
            self._app = Application.builder().token(self.token).build()
            # Commandes
            for cmd, handler in [
                ("start",       self._cmd_start),
                ("stats",       self._cmd_stats),
                ("opportunites",self._cmd_opportunites),
                ("briefing",    self._cmd_briefing),
                ("mails",       self._cmd_mails),
                ("brouillons",  self._cmd_brouillons),
                ("contacts",    self._cmd_contacts),
                ("run",         self._cmd_run),
                ("frequence",   self._cmd_frequence),
                ("test",        self._cmd_test),
                ("aide",        self._cmd_aide),
            ]:
                self._app.add_handler(CommandHandler(cmd, handler))

            self._app.add_handler(CallbackQueryHandler(self._handle_callback))
            self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
            self._app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self._handle_audio))

            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling(
                drop_pending_updates=True,
                error_callback=self._handle_polling_error,
            )
            logger.info("Bot Telegram démarré avec %d commandes.", 9)
        except Exception as exc:
            self._active_tokens.discard(self.token)
            logger.error("Erreur démarrage bot Telegram: %s", exc)

    def _handle_polling_error(self, exc: TelegramError) -> None:
        if isinstance(exc, Conflict):
            if not self._conflict_logged:
                logger.warning(
                    "Polling Telegram désactivé: un autre process utilise déjà getUpdates pour ce bot."
                )
                self._conflict_logged = True
            asyncio.create_task(self.stop_polling_async())
            return
        logger.error("Erreur polling Telegram: %s", exc)

    async def stop_polling_async(self) -> None:
        app = self._app
        if app is None:
            self._active_tokens.discard(self.token)
            return
        # On suppresse TOUTES les exceptions de teardown : python-telegram-bot
        # lève parfois RuntimeError("This HTTPXRequest is not initialized!")
        # quand le client httpx a déjà été fermé, c'est inoffensif au shutdown.
        try:
            updater = getattr(app, "updater", None)
            if updater is not None and getattr(updater, "running", False):
                with contextlib.suppress(Exception):
                    await updater.stop()
            if getattr(app, "running", False):
                with contextlib.suppress(Exception):
                    await app.stop()
            with contextlib.suppress(Exception):
                await app.shutdown()
        except Exception as exc:
            logger.warning("Erreur ignorée pendant l'arrêt du bot Telegram : %s", exc)
        finally:
            self._app = None
            self._active_tokens.discard(self.token)
