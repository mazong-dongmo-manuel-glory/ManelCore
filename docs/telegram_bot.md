# Intégration Telegram Bot

ManelCore inclut un bot Telegram interactif permettant de superviser les agents IA en déplacement.

## Commandes disponibles

- `/start` : Initialise la connexion avec le bot et enregistre le `chat_id`.
- `/status` : Affiche l'état actuel de l'agent Explorer (actif/inactif).
- `/opportunites` : Liste les 5 dernières opportunités trouvées avec leur score de pertinence.
- `/run` : Lance manuellement un cycle de recherche d'opportunités.
- `/aide` : Affiche la liste des commandes et les instructions d'utilisation.

## Notifications Interactives

Lorsqu'une nouvelle opportunité pertinente est détectée, le bot envoie une notification riche contenant :
- Le titre et l'organisation.
- Le score de pertinence.
- Un résumé généré par l'IA.
- Un lien direct vers l'offre.

### Actions rapides
Chaque notification est accompagnée de boutons interactifs :
- **✅ Valider** : Marque l'opportunité comme validée dans la base de données.
- **❌ Rejeter** : Ignore l'opportunité.

## Configuration
Le bot nécessite les variables d'environnement suivantes :
- `TELEGRAM_BOT_TOKEN` : Obtenu via @BotFather.
- `TELEGRAM_CHAT_ID` : (Optionnel) ID du chat pour les notifications automatiques.
