"""
Notification Sender
--------------------
Abstracts Discord and Slack webhook delivery so each monitoring script
can send to either or both platforms without duplicating logic.

Discord uses rich embeds with color sidebars.
Slack uses Block Kit with attachment color sidebars.

Usage
-----
from notifier import Notifier

notifier = Notifier(
    discord_webhook="https://discord.com/api/webhooks/...",  # or None
    slack_webhook="https://hooks.slack.com/services/...",    # or None
)

notifier.send_embed(embed, image_bytes=png_bytes)
notifier.send_raw(discord_payload=..., slack_payload=...)
"""

import requests
import json
from datetime import datetime, timezone


# ─────────────────────────────────────────
#  TIER → SLACK COLOR
# ─────────────────────────────────────────
# Slack attachment colors are hex strings
SLACK_COLORS = {
    "critical": "#FF0000",
    "warning":  "#FF6600",
    "watch":    "#FFCC00",
    "advisory": "#0099FF",
    "status":   "#00CC44",
    "shutdown": "#888888",
    "md":       "#FFAA00",
}

DISCORD_COLORS = {
    "critical": 0xFF0000,
    "warning":  0xFF6600,
    "watch":    0xFFCC00,
    "advisory": 0x0099FF,
    "status":   0x00CC44,
    "shutdown": 0x888888,
    "md":       0xFFAA00,
}


# ─────────────────────────────────────────
#  NOTIFIER CLASS
# ─────────────────────────────────────────

class Notifier:
    """
    Sends notifications to Discord, Slack, or both.

    Parameters
    ----------
    discord_webhook : str or None
        Discord webhook URL. Set to None to disable Discord.
    slack_webhook : str or None
        Slack incoming webhook URL. Set to None to disable Slack.
    username : str
        Display name shown on Discord messages.
    """

    def __init__(
        self,
        discord_webhook: str | None = None,
        slack_webhook:   str | None = None,
        username:        str        = "NWS Alert Monitor",
    ):
        self.discord_webhook = discord_webhook if discord_webhook and discord_webhook != "YOUR_DISCORD_WEBHOOK_URL_HERE" else None
        self.slack_webhook   = slack_webhook   if slack_webhook   and slack_webhook   != "YOUR_SLACK_WEBHOOK_URL_HERE"   else None
        self.username        = username

    @property
    def enabled(self) -> bool:
        return bool(self.discord_webhook or self.slack_webhook)

    # ── Discord ───────────────────────────

    def _post_discord(self, payload: dict, image_bytes: bytes | None = None) -> bool:
        if not self.discord_webhook:
            return True
        try:
            if image_bytes:
                import io
                files   = {"file": ("map.png", io.BytesIO(image_bytes), "image/png")}
                # Discord multipart: payload_json + file
                resp = requests.post(
                    self.discord_webhook,
                    data={"payload_json": json.dumps(payload)},
                    files=files,
                    timeout=15,
                )
            else:
                resp = requests.post(
                    self.discord_webhook,
                    json=payload,
                    timeout=15,
                )
            resp.raise_for_status()
            return True
        except Exception as e:
            print(f"  ✗ Discord error: {e}")
            return False

    # ── Slack ─────────────────────────────

    def _post_slack(self, payload: dict, image_bytes: bytes | None = None) -> bool:
        if not self.slack_webhook:
            return True
        try:
            resp = requests.post(
                self.slack_webhook,
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            # Slack returns "ok" as plain text on success
            return True
        except Exception as e:
            print(f"  ✗ Slack error: {e}")
            return False

    # ── Embed → Slack Block Kit conversion ─

    @staticmethod
    def _embed_to_slack(embed: dict, image_bytes: bytes | None = None) -> dict:
        """
        Convert a Discord-style embed dict to a Slack Block Kit payload.

        Discord embed structure:
            title, description, color (int), fields (list), timestamp, footer

        Slack attachment structure:
            color (hex), pretext, title, text, fields, footer, ts
        """
        title       = embed.get("title", "")
        description = embed.get("description", "")
        color_int   = embed.get("color", 0x888888)
        fields      = embed.get("fields", [])
        footer_text = embed.get("footer", {}).get("text", "")
        timestamp   = embed.get("timestamp", "")
        url         = embed.get("url", "")

        # Convert int color to hex string
        color_hex = f"#{color_int:06X}"

        # Build Slack fields
        slack_fields = []
        for field in fields:
            slack_fields.append({
                "title": field.get("name", ""),
                "value": field.get("value", ""),
                "short": field.get("inline", False),
            })

        # Parse timestamp
        ts = None
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                ts = int(dt.timestamp())
            except Exception:
                pass

        attachment = {
            "color":      color_hex,
            "title":      title,
            "text":       description,
            "fields":     slack_fields,
            "footer":     footer_text,
            "ts":         ts,
            "mrkdwn_in":  ["text", "fields"],
        }

        # Note: Slack incoming webhooks don't support direct image byte upload.
        # If image_bytes is provided, it must be hosted somewhere accessible.
        # For now we note this limitation — a future enhancement would upload
        # to a temporary image host or S3 and attach the URL.
        if image_bytes:
            attachment["footer"] = (footer_text + "  •  Map attached" if footer_text else "Map attached")

        return {"attachments": [attachment]}

    # ── Public send methods ───────────────

    def send_embed(
        self,
        embed:       dict,
        image_bytes: bytes | None = None,
    ) -> bool:
        """
        Send a notification using a Discord-style embed dict.
        Automatically converts to Slack Block Kit for Slack delivery.
        Optionally attaches a PNG map image to Discord.

        Returns True if all enabled platforms succeeded.
        """
        ok = True

        # Discord
        if self.discord_webhook:
            discord_payload = {
                "username": self.username,
                "embeds":   [embed],
            }
            ok = self._post_discord(discord_payload, image_bytes) and ok

        # Slack
        if self.slack_webhook:
            slack_payload = self._embed_to_slack(embed, image_bytes)
            ok = self._post_slack(slack_payload, image_bytes) and ok

        return ok

    def send_status(
        self,
        title:       str,
        description: str,
        tier:        str = "status",
        footer:      str = "",
    ) -> bool:
        """
        Send a simple status embed (startup, shutdown, summary).
        """
        embed = {
            "title":       title,
            "description": description,
            "color":       DISCORD_COLORS.get(tier, 0x888888),
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "footer":      {"text": footer},
        }
        return self.send_embed(embed)
