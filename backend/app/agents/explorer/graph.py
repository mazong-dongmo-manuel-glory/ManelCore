from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END

from .nodes import generate_queries, human_review, load_profile, rank_and_analyze, search_indeed, search_linkedin, search_seao
from .state import ExplorerState


# Global checkpointer to persist state between API calls
_checkpointer = MemorySaver()


def create_explorer_graph():
    workflow = StateGraph(ExplorerState)

    workflow.add_node("load_profile", load_profile)
    workflow.add_node("generate_queries", generate_queries)
    workflow.add_node("search_seao", search_seao)
    workflow.add_node("search_linkedin", search_linkedin)
    workflow.add_node("search_indeed", search_indeed)
    workflow.add_node("rank_and_analyze", rank_and_analyze)
    workflow.add_node("human_review", human_review)

    # Sequential init, then parallel fan-out across all sources
    workflow.set_entry_point("load_profile")
    workflow.add_edge("load_profile", "generate_queries")
    workflow.add_edge("generate_queries", "search_seao")
    workflow.add_edge("generate_queries", "search_linkedin")
    workflow.add_edge("generate_queries", "search_indeed")

    # Fan-in: all three searches merge into rank_and_analyze
    workflow.add_edge("search_seao", "rank_and_analyze")
    workflow.add_edge("search_linkedin", "rank_and_analyze")
    workflow.add_edge("search_indeed", "rank_and_analyze")
    
    workflow.add_edge("rank_and_analyze", "human_review")
    workflow.add_edge("human_review", END)

    return workflow.compile(checkpointer=_checkpointer, interrupt_before=["human_review"])
