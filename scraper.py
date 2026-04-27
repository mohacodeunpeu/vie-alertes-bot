"""
Scraper Business France — offres VIE.

Stratégie en cascade :
  1. Appel API JSON (avec Bearer token si token_cache.json existe)
  2. Extraction de l'état Nuxt embarqué dans le HTML (window.__NUXT__ / __NUXT_DATA__)
  3. Scraping BeautifulSoup des cartes visibles sur la page
"""

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

# ── Constantes ──────────────────────────────────────────────────────────────────

_SESSION_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "Referer":         "https://mon-vie-via.businessfrance.fr/",
    "Origin":          "https://mon-vie-via.businessfrance.fr",
}

TOKEN_CACHE = Path("token_cache.json")


# ── Dataclass Offre ─────────────────────────────────────────────────────────────

@dataclass
class Offer:
    id:          str
    titre:       str
    entreprise:  str
    duree:       int    # mois
    ville:       str
    pays:        str
    salaire:     float
    date_debut:  str    # JJ/MM/AAAA
    date_fin:    str    # JJ/MM/AAAA

    @property
    def url(self) -> str:
        return f"{config.BASE_URL}/offres/{self.id}"


# ── Helpers parsing ─────────────────────────────────────────────────────────────

def _parse_date(raw) -> str:
    if not raw:
        return "—"
    s = str(raw)
    if "T" in s:
        s = s.split("T")[0]
    if "/" in s:
        return s
    parts = s.split("-")
    if len(parts) == 3:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return s or "—"


def _parse_salary(raw) -> float:
    if not raw:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, dict):
        for key in ("montant", "value", "amount", "total", "net"):
            if raw.get(key):
                return float(raw[key])
        return 0.0
    try:
        cleaned = re.sub(r"[^\d.,]", "", str(raw)).replace(",", ".")
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def _parse_raw(raw: dict) -> Optional[Offer]:
    """Convertit un dict brut (API ou HTML) en Offer. Retourne None si invalide."""
    try:
        offer_id = str(
            raw.get("id") or raw.get("offreId") or raw.get("offerId") or
            raw.get("reference") or raw.get("ref") or ""
        ).strip()
        if not offer_id:
            return None

        titre = str(
            raw.get("intitule") or raw.get("title") or raw.get("libelle") or
            raw.get("poste") or raw.get("titreFrancais") or raw.get("name") or
            "Poste non précisé"
        ).strip()

        # Entreprise
        ent = raw.get("entreprise") or raw.get("company") or raw.get("societe") or {}
        if isinstance(ent, dict):
            entreprise = str(
                ent.get("raisonSociale") or ent.get("nom") or
                ent.get("name") or ent.get("libelle") or
                raw.get("entrepriseLibelle") or raw.get("nomEntreprise") or
                "Entreprise inconnue"
            )
        else:
            entreprise = str(ent or raw.get("entrepriseLibelle") or
                             raw.get("nomEntreprise") or "Entreprise inconnue")

        # Localisation
        loc = raw.get("localisation") or raw.get("lieu") or raw.get("location") or {}
        if isinstance(loc, dict):
            ville = str(loc.get("ville") or loc.get("city") or loc.get("commune") or
                        raw.get("ville") or "—")
            pays  = str(loc.get("pays") or loc.get("country") or
                        loc.get("libellePays") or raw.get("pays") or "—")
        else:
            ville = str(raw.get("ville") or raw.get("city") or "—")
            pays  = str(raw.get("pays") or raw.get("country") or
                        raw.get("libellePays") or "—")

        # Durée
        duree = int(
            raw.get("duree") or raw.get("dureeMission") or
            raw.get("duration") or raw.get("nbMois") or 0
        )

        # Salaire
        salaire = _parse_salary(
            raw.get("salaire") or raw.get("remunerationMensuelle") or
            raw.get("remuneration") or raw.get("salary") or
            raw.get("indemnite") or 0
        )

        # Dates
        date_debut = _parse_date(
            raw.get("dateDebut") or raw.get("startDate") or
            raw.get("dateDebutMission") or raw.get("debut") or
            raw.get("datePublication")
        )
        date_fin = _parse_date(
            raw.get("dateFin") or raw.get("endDate") or
            raw.get("dateFinCandidature") or raw.get("fin") or
            raw.get("dateLimite") or raw.get("dateExpiration")
        )

        offer = Offer(
            id=offer_id,
            titre=titre,
            entreprise=entreprise,
            duree=duree,
            ville=ville,
            pays=pays,
            salaire=salaire,
            date_debut=date_debut,
            date_fin=date_fin,
        )

        # Filtres config
        if config.COUNTRIES_FILTER:
            if pays.upper() not in [c.upper() for c in config.COUNTRIES_FILTER]:
                return None
        if config.MIN_SALARY and salaire and salaire < config.MIN_SALARY:
            return None
        if config.MAX_DURATION and duree and duree > config.MAX_DURATION:
            return None

        return offer

    except Exception as e:
        logger.debug(f"Parsing échoué pour id={raw.get('id', '?')}: {e}")
        return None


# ── Session HTTP ────────────────────────────────────────────────────────────────

def _build_session() -> requests.Session:
    """Crée une session HTTP avec les bons headers + Bearer token si dispo."""
    session = requests.Session()
    session.headers.update(_SESSION_HEADERS)

    # Token optionnel (généré par login.py si disponible)
    if TOKEN_CACHE.exists():
        try:
            cache = json.loads(TOKEN_CACHE.read_text(encoding="utf-8"))
            token = cache.get("access_token", "")
            if token and str(token).startswith("ey"):
                session.headers["Authorization"] = f"Bearer {token}"
                logger.info("Token Bearer chargé depuis token_cache.json")
        except Exception as e:
            logger.debug(f"token_cache.json illisible: {e}")

    return session


def _get(session: requests.Session, url: str,
         params: dict = None, retries: int = 3) -> Optional[requests.Response]:
    """GET avec retry et backoff exponentiel."""
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, params=params, timeout=15)
            logger.debug(f"GET {url} → HTTP {resp.status_code}")
            return resp
        except requests.Timeout:
            logger.warning(f"Timeout {url} (tentative {attempt}/{retries})")
        except requests.ConnectionError as e:
            logger.warning(f"Connexion refusée {url}: {e} (tentative {attempt}/{retries})")
        except requests.RequestException as e:
            logger.error(f"Erreur HTTP {url}: {e}")
            break

        if attempt < retries:
            wait = 2 ** attempt
            logger.info(f"Retry dans {wait}s…")
            time.sleep(wait)

    return None


# ── Stratégie 1 : API JSON ───────────────────────────────────────────────────────

def _fetch_api(session: requests.Session) -> list[Offer]:
    logger.info(f"[API] {config.API_URL} (size={config.PARAMS['size']})")
    resp = _get(session, config.API_URL, params=config.PARAMS)
    if not resp:
        return []

    if resp.status_code == 401 or resp.status_code == 500:
        try:
            msg = resp.json().get("message", "")
        except Exception:
            msg = resp.text[:100]
        logger.warning(f"[API] HTTP {resp.status_code}: {msg} — passage au fallback HTML")
        return []

    if resp.status_code != 200:
        logger.warning(f"[API] HTTP {resp.status_code} inattendu")
        return []

    try:
        data = resp.json()
    except ValueError:
        logger.error("[API] Réponse non-JSON")
        return []

    # Normaliser les formats de réponse possibles
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = (
            data.get("content") or data.get("offres") or data.get("results") or
            data.get("data")    or data.get("items")  or data.get("list") or []
        )
        total = data.get("totalElements") or data.get("total") or len(items)
        logger.info(f"[API] {len(items)}/{total} offres reçues")
    else:
        logger.warning(f"[API] Format inattendu: {type(data)}")
        return []

    offers = [o for raw in items if (o := _parse_raw(raw)) is not None]
    logger.info(f"[API] {len(offers)} offres valides")
    return offers


# ── Stratégie 2 : état Nuxt embarqué dans le HTML ──────────────────────────────

def _extract_nuxt_items(html: str) -> list[dict]:
    """Cherche les données d'offres dans les blobs JSON embarqués par Nuxt/SSR."""

    # Nuxt 3 : <script id="__NUXT_DATA__" type="application/json">
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all("script", {"type": "application/json"}):
        try:
            data = json.loads(tag.string or "")
            if isinstance(data, list) and len(data) > 5:
                # Heuristique : chercher les sous-listes qui ressemblent à des offres
                for item in data:
                    if isinstance(item, dict) and (
                        item.get("id") or item.get("intitule") or item.get("title")
                    ):
                        return data
        except Exception:
            continue

    # Nuxt 2 : window.__NUXT__ = {...}  (objet direct)
    match = re.search(
        r'window\.__NUXT__\s*=\s*(\{.*?\})\s*;?\s*</script>',
        html, re.DOTALL
    )
    if match:
        try:
            root = json.loads(match.group(1))
            return _dig_for_offers(root)
        except Exception:
            pass

    # Chercher tout bloc JSON contenant des offres
    for blob in re.findall(r'\{[^{}]{200,}\}', html):
        try:
            data = json.loads(blob)
            found = _dig_for_offers(data)
            if found:
                return found
        except Exception:
            continue

    return []


def _dig_for_offers(node, depth: int = 0) -> list[dict]:
    """Parcours récursif d'un dict/liste pour trouver une liste d'offres."""
    if depth > 6:
        return []
    if isinstance(node, list):
        if len(node) > 0 and isinstance(node[0], dict):
            if any(
                node[0].get(k)
                for k in ("id", "offreId", "intitule", "title", "entreprise")
            ):
                return node
        for item in node:
            found = _dig_for_offers(item, depth + 1)
            if found:
                return found
    elif isinstance(node, dict):
        for key in ("content", "offres", "results", "data", "items", "list",
                    "offers", "missions"):
            val = node.get(key)
            if isinstance(val, list) and val:
                found = _dig_for_offers(val, depth + 1)
                if found:
                    return found
        for val in node.values():
            if isinstance(val, (dict, list)):
                found = _dig_for_offers(val, depth + 1)
                if found:
                    return found
    return []


def _fetch_html(session: requests.Session) -> list[Offer]:
    logger.info(f"[HTML] {config.HTML_URL}")
    resp = _get(session, config.HTML_URL)
    if not resp or resp.status_code != 200:
        logger.error("[HTML] Impossible de charger la page")
        return []

    html = resp.text

    # Tentative via données Nuxt embarquées
    items = _extract_nuxt_items(html)
    if items:
        logger.info(f"[HTML/Nuxt] {len(items)} items bruts trouvés")
        offers = [o for raw in items if isinstance(raw, dict) and (o := _parse_raw(raw)) is not None]
        if offers:
            logger.info(f"[HTML/Nuxt] {len(offers)} offres parsées")
            return offers

    # Tentative via JSON-LD
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
            items = (
                data if isinstance(data, list) else
                data.get("itemListElement") or data.get("offers") or []
            )
            offers = [o for raw in items if isinstance(raw, dict) and (o := _parse_raw(raw)) is not None]
            if offers:
                logger.info(f"[HTML/JSON-LD] {len(offers)} offres")
                return offers
        except Exception:
            continue

    # Tentative via sélecteurs CSS
    selectors = [
        "[data-id]", "[data-offre-id]", "[data-offer-id]",
        "article.offer", "div.offer-card", ".job-card", ".offre-card",
        ".offer-item", ".job-item", "li.offer",
        "[class*='offer']", "[class*='offre']", "[class*='job']",
    ]
    for sel in selectors:
        cards = soup.select(sel)
        if cards:
            logger.info(f"[HTML/CSS] {len(cards)} cartes avec sélecteur '{sel}'")
            offers = []
            for card in cards:
                raw = _parse_html_card(card)
                if raw:
                    o = _parse_raw(raw)
                    if o:
                        offers.append(o)
            if offers:
                return offers

    logger.warning(
        "[HTML] Aucune offre trouvée — le site est probablement rendu uniquement "
        "côté client (JavaScript). Exécutez login.py pour activer l'API authentifiée."
    )
    return []


def _parse_html_card(tag) -> Optional[dict]:
    """Extrait un dict minimal depuis une carte HTML d'offre."""
    try:
        raw: dict = {}

        # ID depuis attributs data-*
        for attr in ("data-id", "data-offre-id", "data-offer-id", "data-reference"):
            val = tag.get(attr, "").strip()
            if val and val.isdigit():
                raw["id"] = val
                break
        if not raw.get("id"):
            # Essai depuis l'attribut id= de la balise
            val = tag.get("id", "")
            digits = re.search(r"\d+", val)
            if digits:
                raw["id"] = digits.group()
        if not raw.get("id"):
            return None

        # Titre
        for sel in ("h1", "h2", "h3", ".title", ".offer-title",
                    "[class*='title']", "[class*='intitule']"):
            el = tag.select_one(sel)
            if el:
                raw["intitule"] = el.get_text(strip=True)
                break

        # Entreprise
        for sel in (".company", ".entreprise", ".firm",
                    "[class*='company']", "[class*='entreprise']"):
            el = tag.select_one(sel)
            if el:
                raw["entreprise"] = {"raisonSociale": el.get_text(strip=True)}
                break

        # Localisation
        for sel in (".location", ".localisation", ".pays",
                    "[class*='location']", "[class*='country']", "[class*='pays']"):
            el = tag.select_one(sel)
            if el:
                text = el.get_text(strip=True)
                parts = [p.strip() for p in text.split(",")]
                raw["localisation"] = {
                    "ville": parts[0] if len(parts) >= 2 else "—",
                    "pays":  parts[-1],
                }
                break

        # Durée
        for sel in (".duration", ".duree", "[class*='duration']", "[class*='duree']"):
            el = tag.select_one(sel)
            if el:
                m = re.search(r"(\d+)", el.get_text())
                if m:
                    raw["duree"] = int(m.group(1))
                break

        return raw if raw.get("intitule") else None

    except Exception as e:
        logger.debug(f"_parse_html_card échoué: {e}")
        return None


# ── Point d'entrée public ───────────────────────────────────────────────────────

def fetch_offers() -> list[Offer]:
    """
    Récupère toutes les offres VIE disponibles.
    Cascade : API → HTML Nuxt → HTML BeautifulSoup.
    """
    session = _build_session()

    # Charger les cookies du site (pré-requête sur la page principale)
    try:
        _get(session, config.BASE_URL)
    except Exception:
        pass

    # 1. API
    offers = _fetch_api(session)
    if offers:
        return offers

    # 2. HTML fallback
    return _fetch_html(session)
