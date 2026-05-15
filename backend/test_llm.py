import asyncio
from langchain_openai import ChatOpenAI
import os

os.environ["MODEL"] = "google/gemma-4-e4b"
os.environ["MODEL_BASE_URL"] = "http://localhost:1234/v1"
os.environ["API_KEY"] = "lm-studio"

llm = ChatOpenAI(
    model=os.getenv("MODEL"),
    base_url=os.getenv("MODEL_BASE_URL"),
    api_key=os.getenv("API_KEY"),
    max_tokens=2000,
)

prompt = """
Tu es un expert en développement des affaires au Québec, spécialisé dans l'analyse de pertinence (Product-Market Fit).

### CONTEXTE DE L'ENTREPRISE MANELCORE
Entreprise: ManelCore
Description: Solutions informatiques et IA.

### MISSION
Analyse chaque opportunité ci-dessous. Tu DOIS vérifier si elle correspond aux secteurs d'activité cités et si ManelCore a les capacités d'y répondre via ses services.

Pour chaque opportunité, génère un objet JSON contenant:
- "score_pertinence": float de 0.0 à 1.0. (0.9+ = match parfait, <0.4 = hors sujet).
- "contact_email": email du contact si trouvé, sinon null.
- "contact_nom": nom de la personne ressource si trouvé, sinon null.
- "draft_email": Si contact_email est présent et score > 0.7, rédige un email d'introduction ultra-professionnel de la part du dirigeant de ManelCore, sinon null.
- "resume": analyse critique structurée de 4-6 phrases.

### OPPORTUNITÉS À ANALYSER
[
  {
    "titre": "Développement d'une application mobile",
    "organisation": "Ville de Québec",
    "resume": "Nous cherchons un partenaire pour développer notre application.",
    "url": "http://example.com"
  }
]

### FORMAT DE RÉPONSE
Retourne UNIQUEMENT un JSON array complet trié par score_pertinence décroissant.
IMPORTANT: Conserve tous les champs originaux et ajoute seulement 'score_pertinence', 'contact_email', 'contact_nom', 'draft_email' et 'resume'.
"""

async def main():
    print("Calling LLM...")
    res = await llm.ainvoke(prompt)
    print("Response:")
    print(res.content)

asyncio.run(main())
