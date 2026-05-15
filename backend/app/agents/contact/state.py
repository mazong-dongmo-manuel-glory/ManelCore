from typing import Annotated, List, TypedDict
from langchain_core.messages import BaseMessage
import operator


class ContactState(TypedDict):
    opportunity_id: str
    contact_info: dict           # {"email": ..., "nom": ..., "organisation": ..., "poste": ...}
    opportunity_details: dict    # Full opportunity data loaded from Neo4j
    company_context: dict        # Entreprise + ProfilEntreprise loaded from Neo4j
    conversation_history: List[dict]
    draft_email: str
    status: str                  # drafting | awaiting_approval | approved | sent | error
    approved: bool
    error: str
    messages: Annotated[List[BaseMessage], operator.add]
