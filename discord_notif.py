"""
Envoi des notifications Discord via webhook.
"""

import logging
import time
from datetime import datetime, timezone

import requests

import config
from scraper import Offer

logger = logging.getLogger(__name__)

EMBED_COLOR  = 3447003   # Bleu Discord
COLOR_GREEN  = 5763719
COLOR_RED    = 15548997


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _fmt_date(raw: str) -> str:
    """Garantit le format JJ/MM/AAAA."""
    if not raw or raw == "—":
        return "—"
    s = str(raw).strip()
    if "/" in s:
        return s
    # ISO → JJ/MM/AAAA
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt).strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            continue
    return s


def _fmt_salary(amount: float) -> str:
    if not amount:
        return "Non précisé"
    return f"{int(amount):,} €/mois".replace(",", " ")


def _fmt_duration(months: int) -> str:
    if not months:
        return "—"
    if months == 1:
        return "1 mois"
    return f"{months} mois"


# ── Construction de l'embed ──────────────────────────────────────────────────────

def _build_embed(offer: Offer) -> dict:
    return {
        "title":       f"💼 {offer.titre}",
        "color":       EMBED_COLOR,
        "url":         offer.url,
        "description": f"🔗 [Voir l'offre sur Business France]({offer.url})",
        "fields": [
            {
                "name":   "🏢 Entreprise",
                "value":  offer.entreprise or "—",
                "inline": True,
            },
            {
                "name":   "📅 Durée",
                "value":  _fmt_duration(offer.duree),
                "inline": True,
            },
            {
                "name":   "🏙️ Ville",
                "value":  offer.ville or "—",
                "inline": True,
            },
            {
                "name":   "🌍 Pays",
                "value":  offer.pays or "—",
                "inline": True,
            },
            {
                "name":   "💰 Salaire",
                "value":  _fmt_salary(offer.salaire),
                "inline": True,
            },
            {
                "name":   "🚀 Début",
                "value":  _fmt_date(offer.date_debut),
                "inline": True,
            },
            {
                "name":   "🏁 Fin candidature",
                "value":  _fmt_date(offer.date_fin),
                "inline": True,
            },
        ],
        "footer":    {"text": "🇫🇷 Alerte VIE • Business France"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Envoi ────────────────────────────────────────────────────────────────────────

def _post_payload(payload: dict, retries: int = 3) -> bool:
    """POST un payload JSON sur le webhook. Retourne True si succès."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                config.DISCORD_WEBHOOK_URL,
                json=payload,
                timeout=10,
            )

            if resp.status_code in (200, 204):
                return True

            # Rate limit Discord
            if resp.status_code == 429:
                try:
                    retry_after = float(resp.json().get("retry_after", 5))
                except Exception:
                    retry_after = 5.0
                logger.warning(f"Rate limit Discord — attente {retry_after:.1f}s")
                time.sleep(retry_after)
                continue

            logger.warning(
                f"Discord HTTP {resp.status_code} "
                f"(tentative {attempt}/{retries}): {resp.text[:200]}"
            )

        except requests.RequestException as e:
            logger.warning(f"Erreur webhook (tentative {attempt}/{retries}): {e}")

        if attempt < retries:
            backoff = 2 ** attempt
            logger.info(f"Retry dans {backoff}s…")
            time.sleep(backoff)

    return False


def send_offer(offer: Offer) -> bool:
    """Envoie une offre VIE dans le canal Discord. Retourne True si succès."""
    ok = _post_payload({"embeds": [_build_embed(offer)]})
    if ok:
        logger.info(f"✅ Envoyé : [{offer.id}] {offer.titre[:55]}")
    else:
        logger.error(f"❌ Échec envoi : [{offer.id}] {offer.titre[:55]}")
    return ok


def send_startup() -> None:
    """Annonce le démarrage du bot dans le canal."""
    payload = {
        "embeds": [{
            "title":       "🟢 Bot VIE démarré",
            "description": (
                f"Surveillance des offres VIE active.\n"
                f"Vérification toutes les **{config.INTERVAL_SECONDS // 60} minutes**."
            ),
            "color":     COLOR_GREEN,
            "footer":    {"text": "🇫🇷 Alerte VIE • Business France"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }
    try:
        requests.post(config.DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        logger.info("Message de démarrage envoyé sur Discord")
    except Exception as e:
        logger.warning(f"Impossible d'envoyer le message de démarrage: {e}")


def send_error_alert(message: str) -> None:
    """Envoie une alerte d'erreur critique dans le canal (optionnel)."""
    payload = {
        "embeds": [{
            "title":       "🔴 Erreur bot VIE",
            "description": message[:2000],
            "color":       COLOR_RED,
            "footer":      {"text": "🇫🇷 Alerte VIE • Business France"},
            "timestamp":   datetime.now(timezone.utc).isoformat(),
        }]
    }
    try:
        requests.post(config.DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except Exception:
        pass
