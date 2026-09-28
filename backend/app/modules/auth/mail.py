"""Self-controlled SMTP delivery. Payloads are encrypted until sent or expired."""

import asyncio
from datetime import timedelta
from email.message import EmailMessage
import json
import smtplib
import ssl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.identity import now, decrypt
from app.modules.auth.identity_models import IdentityMail


class SMTPDelivery:
    def send(self, payload: dict, message_id: str) -> None:
        message = EmailMessage()
        message["From"] = settings.SMTP_FROM
        message["To"] = payload["to"]
        message["Subject"] = payload["subject"]
        message["Message-ID"] = f"<{message_id}@azaeron.local>"
        message.set_content(payload["body"])
        with smtplib.SMTP(
            settings.SMTP_HOST, settings.SMTP_PORT, timeout=10
        ) as connection:
            if settings.SMTP_STARTTLS:
                connection.starttls(context=ssl.create_default_context())
            if settings.SMTP_USERNAME:
                connection.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
            connection.send_message(message)


async def deliver_pending(
    db: AsyncSession, delivery: SMTPDelivery | None = None
) -> dict[str, int]:
    counts = {"sent": 0, "failed": 0, "expired": 0}
    if not settings.EMAIL_ENABLED:
        return counts
    rows = (
        await db.scalars(
            select(IdentityMail)
            .where(
                IdentityMail.sent_at.is_(None),
                IdentityMail.encrypted_payload.is_not(None),
                IdentityMail.next_attempt_at <= now(),
            )
            .order_by(IdentityMail.created_at)
            .limit(25)
            .with_for_update(skip_locked=True)
        )
    ).all()
    sender = delivery or SMTPDelivery()
    for row in rows:
        if row.expires_at.replace(tzinfo=now().tzinfo) <= now():
            row.encrypted_payload = None
            row.last_error = "expired"
            counts["expired"] += 1
            continue
        row.attempts += 1
        try:
            payload = json.loads(decrypt(row.encrypted_payload or ""))
            await asyncio.to_thread(sender.send, payload, str(row.id))
            row.sent_at = now()
            row.encrypted_payload = None
            row.last_error = None
            counts["sent"] += 1
        except Exception:
            # Never persist SMTP exception strings, addresses or token-bearing bodies.
            row.last_error = "delivery_unavailable"
            row.next_attempt_at = now() + timedelta(seconds=min(600, 30 * row.attempts))
            counts["failed"] += 1
    await db.flush()
    return counts
