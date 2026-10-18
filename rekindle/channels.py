"""Outbound senders. dry_run (default) only records; live calls WhatsApp Cloud API / Gmail API."""
from __future__ import annotations

import base64
import os
from email.message import EmailMessage
from typing import Protocol

from .config import Merchant, Settings
from .models import Channel, Draft


class Sender(Protocol):
    def send(self, d: Draft, phone: str | None, email: str | None) -> str: ...


class DryRunSender:
    def __init__(self):
        self.outbox: list[dict] = []

    def send(self, d, phone, email):
        self.outbox.append({"draft_id": d.id, "channel": d.channel.value, "to": phone or email, "body": d.rendered})
        return f"dryrun-{len(self.outbox)}"


class LiveSender:
    """WhatsApp: pre-approved template message (free text is not allowed outside the 24h window).
    Email: Gmail API via a service account with domain-wide delegation. Not exercised by the test suite."""

    def __init__(self, merchant: Merchant):
        self.merchant = merchant

    def send(self, d, phone, email):
        if d.channel == Channel.whatsapp:
            return self._whatsapp(d, phone)
        return self._gmail(d, email)

    def _whatsapp(self, d, phone):
        import httpx

        hook = d.text.strip()
        first = d.customer_name.split()[0]
        r = httpx.post(
            f"https://graph.facebook.com/v20.0/{os.environ['WHATSAPP_PHONE_NUMBER_ID']}/messages",
            headers={"Authorization": f"Bearer {os.environ['WHATSAPP_TOKEN']}"},
            json={"messaging_product": "whatsapp", "to": phone.lstrip("+"), "type": "template",
                  "template": {"name": self.merchant.whatsapp_template, "language": {"code": "en"},
                               "components": [{"type": "body", "parameters": [
                                   {"type": "text", "text": first}, {"type": "text", "text": self.merchant.name},
                                   {"type": "text", "text": hook}]}]}},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()["messages"][0]["id"]

    def _gmail(self, d, email):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        sender = os.environ["GMAIL_SENDER"]
        creds = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"], scopes=["https://www.googleapis.com/auth/gmail.send"]
        ).with_subject(sender)
        msg = EmailMessage()
        msg["To"], msg["From"], msg["Subject"] = email, sender, d.subject or self.merchant.name
        msg.set_content(d.rendered)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        return build("gmail", "v1", credentials=creds).users().messages().send(userId="me", body={"raw": raw}).execute()["id"]


def make_sender(settings: Settings, merchant: Merchant) -> Sender:
    return LiveSender(merchant) if settings.send_mode == "live" else DryRunSender()
