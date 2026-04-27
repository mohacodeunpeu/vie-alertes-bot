import time
import logging
import requests
from datetime import datetime, timezone
from scraper import Offer
import config

logger = logging.getLogger(__name__)

EMBED_COLOR = 3447003  # bleu Discord


def _format_date(raw: str) -> str:
    """Convert ISO date to DD/MM/YYYY, return as-is if unparseable."""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:19], fmt).strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            continue
    return raw or "—"


def _format_salary(amount: float) -> str:
    if not amount:
        return "Non précisé"
    return f"{amount:,.0f} €/mois".replace(",", " ")


def _build_embed(offer: Offer) -> dict:
    specs_str = ", ".join(offer.specializations) if offer.specializations else "—"

    fields = [
        {"name": "🏢 Entreprise", "value": offer.company, "inline": True},
        {"name": "📅 Durée", "value": f"{offer.duration_months} mois" if offer.duration_months else "—", "inline": True},
        {"name": "💰 Indemnité", "value": _format_salary(offer.salary), "inline": True},
        {"name": "🏙️ Ville", "value": offer.city, "inline": True},
        {"name": "🌍 Pays", "value": offer.country, "inline": True},
        {"name": "🚀 Début", "value": _format_date(offer.start_date), "inline": True},
        {"name": "🏁 Fin candidature", "value": _format_date(offer.end_date), "inline": True},
    ]
    if offer.specializations:
        fields.append({"name": "📂 Domaine", "value": specs_str, "inline": False})

    return {
        "title": f"💼 {offer.title} (H/F)",
        "url": offer.url,
        "color": EMBED_COLOR,
        "description": f"🔗 [Voir l'offre sur Business France]({offer.url})",
        "fields": fields,
        "footer": {"text": "🇫🇷 Alerte VIE • Business France"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def send_offer(offer: Offer, retries: int = 3) -> bool:
    """Send one offer as a Discord embed. Returns True on success."""
    payload = {"embeds": [_build_embed(offer)]}

    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                config.DISCORD_WEBHOOK_URL,
                json=payload,
                timeout=10,
            )
            if resp.status_code in (200, 204):
                logger.info(f"Sent offer {offer.id} — {offer.title[:50]}")
                return True
            # 429 = rate limit
            if resp.status_code == 429:
                retry_after = resp.json().get("retry_after", 5)
                logger.warning(f"Discord rate limit — waiting {retry_after}s")
                time.sleep(float(retry_after))
                continue
            logger.warning(
                f"Discord returned {resp.status_code} for offer {offer.id} "
                f"(attempt {attempt}/{retries}): {resp.text[:200]}"
            )
        except requests.RequestException as e:
            logger.warning(f"Webhook request error (attempt {attempt}/{retries}): {e}")

        if attempt < retries:
            backoff = 2 ** attempt
            logger.info(f"Retrying in {backoff}s…")
            time.sleep(backoff)

    logger.error(f"Failed to send offer {offer.id} after {retries} attempts")
    return False


def send_startup_message() -> None:
    """Post a startup notice to the channel."""
    payload = {
        "embeds": [{
            "title": "🟢 Bot VIE démarré",
            "description": (
                f"Scraping toutes les **{config.INTERVAL_SECONDS // 60} minutes**.\n"
                f"Taille de page : **{config.PAGE_SIZE}** offres."
            ),
            "color": 5763719,  # vert
            "footer": {"text": "🇫🇷 Alerte VIE • Business France"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }
    try:
        requests.post(config.DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except requests.RequestException as e:
        logger.warning(f"Could not send startup message: {e}")
