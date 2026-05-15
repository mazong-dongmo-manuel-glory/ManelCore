# Référence de l'API FastAPI

L'API de ManelCore est le cœur du système, facilitant la communication entre le frontend Flutter, la base de données Neo4j, et les agents IA.

## Endpoints principaux

### Santé et Système
- `GET /health` : Vérifie l'état de connexion à Neo4j et au serveur LLM.
- `GET /dashboard/stats` : Récupère les statistiques globales (opportunités, contacts, emails).

### Configuration
- `POST /config` : Met à jour le profil de l'entreprise et les secteurs cibles.
- `GET /config` : Récupère la configuration actuelle.

### Agent Explorer (Veille)
- `POST /agent/run` : Déclenche l'agent de recherche en arrière-plan.
- `GET /agent/stream` : Stream (SSE) les événements en temps réel de l'agent.
- `GET /agent/status` : Indique si l'agent est actuellement en cours d'exécution.

### Gestion des Opportunités
- `GET /opportunities` : Liste les opportunités avec filtres (limite, statut).
- `GET /opportunities/{id}` : Détails d'une opportunité spécifique.
- `PATCH /opportunities/{id}/status` : Met à jour le statut (ex: validé, rejeté).

### Gestion des Contacts et RH
- `GET /contacts` / `POST /contacts` : Gestion des contacts d'affaires.
- `GET /candidats` / `POST /candidats` : Gestion du pipeline de recrutement.

### Chat et Interaction
- `POST /chat/stream` : Interface de chat direct avec le LLM en streaming.
- `POST /contact/draft` : Génère un brouillon d'email pour une opportunité.
- `POST /contact/approve` : Valide et envoie un email de contact.

## Authentification et Sécurité
Le système utilise actuellement une configuration basée sur les variables d'environnement (`API_KEY`, `MODEL_BASE_URL`) pour communiquer avec les fournisseurs de modèles.
