# Bot VIE — Alertes Discord automatiques

Scrape les offres VIE de Business France toutes les 30 minutes et envoie les nouvelles offres dans Discord via webhook.

## Déploiement Railway (gratuit)

### Étape 1 — Créer un compte Railway
1. Va sur [railway.app](https://railway.app)
2. Clique **Login** → connecte-toi avec GitHub

### Étape 2 — Pousser les fichiers sur GitHub
Dans ton terminal (dans le dossier `vie-alert-bot/`) :

```bash
git init
git add .
git commit -m "bot VIE initial"
git branch -M main
git remote add origin https://github.com/TON_USERNAME/vie-alert-bot.git
git push -u origin main
```

> Si tu n'as pas encore de repo GitHub : va sur github.com → New repository → copie l'URL.

### Étape 3 — Créer le projet Railway
1. Sur Railway : **New Project** → **Deploy from GitHub repo**
2. Sélectionne ton repo `vie-alert-bot`
3. Railway détecte automatiquement le `Procfile` et le `runtime.txt`
4. Clique **Deploy**

### Étape 4 — Vérifier le déploiement
1. Va dans l'onglet **Deployments** → clique sur le dernier déploiement
2. Onglet **Logs** → tu dois voir :
   ```
   [2026-04-27 13:00:00] INFO     __main__ — Bot VIE démarré — vérification toutes les 30 min
   ```
3. Le message de démarrage apparaît aussi dans ton salon Discord

### Étape 5 (optionnel) — Variables d'environnement
Le webhook est déjà dans `config.py`.  
Si tu veux le changer sans modifier le code : Railway → Variables → ajoute `DISCORD_WEBHOOK_URL`.  
Dans ce cas, modifie `config.py` pour lire la variable :
```python
import os
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "ton_webhook_par_defaut")
```

---

## Lancer en local

```bash
# Installer les dépendances
pip install -r requirements.txt

# Démarrer le bot
python main.py
```

---

## Structure des fichiers

| Fichier | Rôle |
|---|---|
| `config.py` | URL webhook, intervalle, filtres |
| `scraper.py` | Scraping API + fallback HTML |
| `discord_notif.py` | Envoi des embeds Discord |
| `main.py` | Boucle principale |
| `seen_offers.json` | IDs déjà envoyés (persistance) |
| `bot.log` | Logs rotatifs (5 Mo max) |

---

## Dépannage

**Le bot tourne mais n'envoie rien**
→ L'API Business France peut nécessiter une authentification.  
→ Lance `python login.py` (nécessite `playwright`) pour te connecter une fois et générer `token_cache.json`.  
→ Le bot utilisera ce token automatiquement.

**Erreur `No module named 'bs4'`**
→ `pip install -r requirements.txt`

**Le webhook ne fonctionne pas**
→ Vérifie que l'URL dans `config.py` est correcte (pas expirée, pas supprimée sur Discord).
