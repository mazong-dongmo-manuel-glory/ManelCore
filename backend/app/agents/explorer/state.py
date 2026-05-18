from typing import Annotated, List, TypedDict
from langchain_core.messages import BaseMessage
import operator


class ExplorerState(TypedDict, total=False):
    company_profile: str
    sectors: List[str]
    search_queries: List[str]
    search_prompt_hint: str
    found_opportunities: Annotated[List[dict], operator.add]
    ranked_opportunities: List[dict]
    messages: Annotated[List[BaseMessage], operator.add]
    current_source: Annotated[List[str], operator.add]
    approved_opportunities: List[dict]
    review_comment: str
    errors: Annotated[List[str], operator.add]
    context: dict
