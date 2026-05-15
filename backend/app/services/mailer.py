from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from imap_tools import AND, MailBox


class MailerService:
    def __init__(
        self,
        email: str,
        password: str,
        imap_server: str,
        smtp_server: str | None = None,
        smtp_port: int = 587,
    ):
        self.email = email
        self.password = password
        self.imap_server = imap_server
        self.smtp_server = smtp_server or imap_server
        self.smtp_port = smtp_port

    def send(self, to: str, subject: str, body: str, html: str | None = None) -> None:
        """Send an email via SMTP with TLS."""
        msg = MIMEMultipart("alternative")
        msg["From"] = self.email
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        if html:
            msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(self.email, self.password)
            server.sendmail(self.email, to, msg.as_string())

    def fetch_unread(self, limit: int = 20) -> list[dict]:
        """Return unread messages as plain dicts with ALL available metadata."""
        messages: list[dict] = []
        with MailBox(self.imap_server).login(self.email, self.password) as mailbox:
            for msg in mailbox.fetch(AND(seen=False), limit=limit):
                # Collect attachment metadata without reading binary content
                attachments = []
                for att in (msg.attachments or []):
                    attachments.append({
                        "filename": att.filename or "",
                        "content_type": att.content_type or "",
                        "size": len(att.payload) if att.payload else 0,
                    })

                messages.append({
                    "uid":              msg.uid,
                    "from":             msg.from_,
                    "from_values":      {
                        "name":  msg.from_values.name if msg.from_values else "",
                        "email": msg.from_values.email if msg.from_values else msg.from_,
                    },
                    "to":               list(msg.to),
                    "to_values":        [
                        {"name": v.name, "email": v.email}
                        for v in (msg.to_values or [])
                    ],
                    "cc":               list(msg.cc) if msg.cc else [],
                    "cc_values":        [
                        {"name": v.name, "email": v.email}
                        for v in (msg.cc_values or [])
                    ],
                    "reply_to":         list(msg.reply_to) if msg.reply_to else [],
                    "subject":          msg.subject,
                    "date":             str(msg.date),
                    "date_str":         msg.date_str,
                    "text":             msg.text or "",
                    "html":             msg.html or "",
                    "has_attachments":  bool(attachments),
                    "attachments":      attachments,
                    "message_id":       msg.headers.get("message-id", [""])[0] if msg.headers else "",
                    "in_reply_to":      msg.headers.get("in-reply-to", [""])[0] if msg.headers else "",
                    "flags":            list(msg.flags) if msg.flags else [],
                    "size":             msg.size or 0,
                })
        return messages

    def listen(self, on_message, timeout: int = 60) -> None:
        """Block and call *on_message(dict)* for every new email received."""
        try:
            with MailBox(self.imap_server).login(self.email, self.password) as mailbox:
                print(f"[MailerService] Listening on {self.imap_server}…")
                while True:
                    responses = mailbox.idle.wait(timeout=timeout)
                    if responses:
                        for msg in mailbox.fetch(AND(seen=False)):
                            attachments = []
                            for att in (msg.attachments or []):
                                attachments.append({
                                    "filename": att.filename or "",
                                    "content_type": att.content_type or "",
                                    "size": len(att.payload) if att.payload else 0,
                                })
                            on_message({
                                "uid":             msg.uid,
                                "from":            msg.from_,
                                "from_values":     {
                                    "name":  msg.from_values.name if msg.from_values else "",
                                    "email": msg.from_values.email if msg.from_values else msg.from_,
                                },
                                "to":              list(msg.to),
                                "cc":              list(msg.cc) if msg.cc else [],
                                "reply_to":        list(msg.reply_to) if msg.reply_to else [],
                                "subject":         msg.subject,
                                "date":            str(msg.date),
                                "text":            msg.text or "",
                                "html":            msg.html or "",
                                "has_attachments": bool(attachments),
                                "attachments":     attachments,
                                "message_id":      msg.headers.get("message-id", [""])[0] if msg.headers else "",
                                "size":            msg.size or 0,
                            })
        except Exception as exc:
            print(f"[MailerService] Error: {exc}")
