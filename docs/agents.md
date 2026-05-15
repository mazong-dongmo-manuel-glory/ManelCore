# Agents IA (LangGraph)

ManelCore utilise **LangGraph** pour orchestrer des workflows d'IA complexes et persistants.

## Agent Explorer

L'agent Explorer est responsable de la veille stratégique. Son cycle de vie est le suivant :

1.  **load_profile** : Récupère le profil de l'entreprise et les secteurs cibles depuis Neo4j.
2.  **generate_queries** : Utilise le LLM pour transformer les secteurs en requêtes de recherche optimisées.
3.  **Nodes de Recherche** (Exécutés en parallèle ou séquence) :
    *   `search_seao` : Scrape le site SEAO pour les appels d'offres publics au Québec.
    *   `search_linkedin` : Recherche des opportunités d'affaires sur LinkedIn.
    *   `search_indeed` : Identifie des projets ou rôles pertinents sur Indeed.
4.  **rank_and_save** :
    *   Déduplique les résultats.
    *   Attribue un score de pertinence (0.0 à 1.0) basé sur le profil de l'entreprise.
    *   Génère un résumé explicatif pour chaque opportunité.
    *   Persiste les données dans Neo4j.

## Agent Contact

L'agent Contact gère l'engagement avec les prospects :
- Analyse l'opportunité sélectionnée.
- Rédige un email personnalisé en utilisant le profil de l'entreprise.
- Attend une validation humaine (via l'API ou Telegram) avant d'envoyer.

## Configuration des Modèles
Les agents utilisent deux types de configurations :
- **LLM Principal** : Pour le raisonnement et le classement.
- **Crawler HTTP** : Extraction légère des sources publiques; le navigateur est réservé aux cas manuels.
