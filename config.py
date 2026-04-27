# ── Webhook Discord ────────────────────────────────────────────────────────────
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1498280864705155202/ECenTEgA7Ixc8Mx4fuCxQWB6ULMus48RFkgCX7yi-s98xIVawcjpZ8KAThmTtC5VmQtV"

# ── Timing ──────────────────────────────────────────────────────────────────────
INTERVAL_SECONDS = 1800  # 30 minutes entre chaque cycle

# ── Fichiers locaux ─────────────────────────────────────────────────────────────
SEEN_FILE = "seen_offers.json"
LOG_FILE  = "bot.log"

# ── URLs ────────────────────────────────────────────────────────────────────────
BASE_URL    = "https://mon-vie-via.businessfrance.fr"
API_URL     = "https://mon-vie-via.businessfrance.fr/api/offres/recherche"
HTML_URL    = "https://mon-vie-via.businessfrance.fr/offres/recherche"

# ── Paramètres API ──────────────────────────────────────────────────────────────
PARAMS = {
    "missionsTypesIds": "VIE",
    "page": 0,
    "size": 100,
}

# ── Filtres optionnels (laisser [] ou 0 pour tout récupérer) ────────────────────
COUNTRIES_FILTER: list = []   # ex: ["ALLEMAGNE", "ROYAUME-UNI"]
MIN_SALARY:       float = 0   # ex: 1500 → ignore les offres sous 1500 €/mois
MAX_DURATION:     int   = 0   # ex: 12 → ignore les offres > 12 mois
