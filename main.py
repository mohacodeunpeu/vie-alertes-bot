"""
Bot VIE — point d'entrée.

Boucle infinie : scrape → détecte les nouvelles offres → envoie sur Discord → attente.
Ne s'arrête jamais sauf SIGINT/SIGTERM.
"""

import json
import logging
import logging.handlers
import sys
import time
from datetime import datetime
from pathlib import Path

import config
import discord_notif
import scraper


# ── Logging ──────────────────────────────────────────────────────────────────────

def setup_logging() -> None:
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handlers = [
        # Console
        logging.StreamHandler(sys.stdout),
        # Fichier rotatif : 5 Mo max, 3 sauvegardes
        logging.handlers.RotatingFileHandler(
            config.LOG_FILE,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        ),
    ]
    for h in handlers:
        h.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in handlers:
        root.addHandler(h)


logger = logging.getLogger(__name__)


# ── Persistance seen_offers.json ─────────────────────────────────────────────────

def load_seen() -> set[str]:
    path = Path(config.SEEN_FILE)
    if not path.exists():
        path.write_text("[]", encoding="utf-8")
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except Exception as e:
        logger.warning(f"Impossible de lire {config.SEEN_FILE}: {e}")
        return set()


def save_seen(ids: set[str]) -> None:
    try:
        Path(config.SEEN_FILE).write_text(
            json.dumps(sorted(ids), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error(f"Impossible de sauvegarder {config.SEEN_FILE}: {e}")


# ── Boucle principale ────────────────────────────────────────────────────────────

def run() -> None:
    setup_logging()

    logger.info("=" * 60)
    logger.info("Bot VIE démarré — vérification toutes les 30 min")
    logger.info("=" * 60)

    discord_notif.send_startup()

    seen_ids = load_seen()
    logger.info(f"IDs déjà connus: {len(seen_ids)}")

    cycle = 0

    while True:
        cycle += 1
        start = datetime.now()
        logger.info(f"── Cycle #{cycle} @ {start.strftime('%H:%M:%S')} ──")

        try:
            offers = scraper.fetch_offers()
            new_offers = [o for o in offers if o.id not in seen_ids]

            logger.info(
                f"Cycle #{cycle}: {len(offers)} offres total, "
                f"{len(new_offers)} nouvelles"
            )

            sent = 0
            for offer in new_offers:
                if discord_notif.send_offer(offer):
                    seen_ids.add(offer.id)
                    sent += 1
                    save_seen(seen_ids)
                # Pause anti-rate-limit entre deux messages
                time.sleep(1.5)

            duration = (datetime.now() - start).seconds
            logger.info(
                f"Cycle #{cycle} terminé en {duration}s — "
                f"{sent} offre(s) envoyée(s)"
            )

        except KeyboardInterrupt:
            logger.info("Arrêt demandé (Ctrl+C)")
            break

        except Exception as exc:
            logger.error(
                f"Erreur inattendue cycle #{cycle}: {exc}",
                exc_info=True,
            )
            # On ne crashe jamais — on attend et on reprend

        logger.info(
            f"Prochain cycle dans {config.INTERVAL_SECONDS // 60} min…"
        )
        try:
            time.sleep(config.INTERVAL_SECONDS)
        except KeyboardInterrupt:
            logger.info("Arrêt demandé (Ctrl+C)")
            break

    logger.info("Bot arrêté proprement.")


if __name__ == "__main__":
    run()
