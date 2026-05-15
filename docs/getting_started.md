# Guide d'Installation et Démarrage

## Prérequis

- **Python** 3.11+ (le projet utilise 3.14)
- **Flutter** SDK stable
- **Neo4j Desktop** — créer une instance locale, mot de passe : `password`
- **LM Studio** — charger le modèle `google/gemma-4-e4b` sur le port `1234`

---

## 1. Installation du backend

```bash
cd /Users/mazong/Documents/ManelCore

# Créer le venv (une seule fois)
python3 -m venv .venv

# Installer les dépendances
.venv/bin/pip install -r backend/requirements.txt
```

> **Note** : le venv est à la **racine du projet** (`ManelCore/.venv`),  
> pas dans `backend/`. Le hook `.zshrc` l'active automatiquement.

---

## 2. Lancer le backend

```bash
cd /Users/mazong/Documents/ManelCore/backend
python main.py
```

Le hook `.zshrc` active automatiquement le bon venv dès que tu entres dans le répertoire.  
L'API est disponible sur **http://localhost:8000**.

Pour lancer manuellement sans le hook :

```bash
PYTHONPATH=/Users/mazong/Documents/ManelCore/backend \
  /Users/mazong/Documents/ManelCore/.venv/bin/python main.py
```

---

## 3. Lancer le frontend Flutter

```bash
cd /Users/mazong/Documents/ManelCore/manelcore
flutter run -d macos
```

---

## 4. Variables d'environnement (`backend/.env`)

```env
# LLM — LM Studio local
MODEL=google/gemma-4-e4b
MODEL_BASE_URL=http://localhost:1234/v1
API_KEY=lm-studio

# Neo4j local
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password

# Email
MAILER_EMAIL=manuel.mazong@manelcanada.ca
MAILER_PASSWORD=...
MAILER_IMAP_SERVER=mail.manelcanada.ca

# Telegram (optionnel)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

---

## 5. Démarrage rapide

1. Ouvrir **Neo4j Desktop** → démarrer l'instance
2. Ouvrir **LM Studio** → charger `google/gemma-4-e4b` sur le port 1234
3. Ouvrir un terminal dans `ManelCore/backend` → `python main.py`
4. Ouvrir un autre terminal dans `ManelCore/manelcore` → `flutter run -d macos`
5. Dans l'app : aller dans **Configuration** → renseigner le profil entreprise
6. Aller dans **Recherche** → **Cycle de test** pour vérifier que tout fonctionne

---

## Dépannage

| Erreur | Cause | Solution |
|---|---|---|
| `ModuleNotFoundError: uvicorn` | Python système utilisé au lieu du venv | Recharger `.zshrc` : `source ~/.zshrc` |
| `Neo4j connection error` | Neo4j Desktop non démarré | Démarrer l'instance dans Neo4j Desktop |
| `LLM not connected` | LM Studio fermé ou mauvais port | Ouvrir LM Studio, vérifier port 1234 |
| `Port 8000 already in use` | Backend déjà en cours | `pkill -f uvicorn` puis relancer |
