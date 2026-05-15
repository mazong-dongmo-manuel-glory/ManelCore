from langgraph.graph import StateGraph, END

from .nodes import draft_response, fetch_history, send_email
from .state import ContactState


def create_contact_graph():
    workflow = StateGraph(ContactState)

    workflow.add_node("fetch_history", fetch_history)
    workflow.add_node("draft_response", draft_response)
    workflow.add_node("send_email", send_email)

    workflow.set_entry_point("fetch_history")
    workflow.add_edge("fetch_history", "draft_response")
    workflow.add_edge("draft_response", "send_email")
    workflow.add_edge("send_email", END)

    # interrupt_before=["send_email"] pauses execution after draft_response so the
    # API can serve the draft for human review; the caller resumes with approved=True.
    return workflow.compile(interrupt_before=["send_email"])
