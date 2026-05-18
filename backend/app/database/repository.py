from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any
from uuid import uuid4

from .connection import Neo4jConnection
from .models import (
    AgentAction,
    Besoin,
    Candidature,
    Contact,
    Conversation,
    Document,
    Entreprise,
    GraphNodePayload,
    Message,
    Opportunite,
    ProfilEntreprise,
    Secteur,
)
from .queries import (
    build_delete_node_query,
    build_delete_relationship_query,
    build_find_nodes_query,
    build_get_node_query,
    build_get_related_nodes_query,
    build_merge_node_query,
    build_merge_relationship_query,
)

NodeInput = Mapping[str, Any] | GraphNodePayload


def _serialize_neo4j(value: Any) -> Any:
    """Recursively convert Neo4j temporal/spatial types to JSON-safe primitives."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {k: _serialize_neo4j(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_neo4j(v) for v in value]
    # Neo4j DateTime / Date / Time all have isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    # Fallback for any other neo4j type
    try:
        return str(value)
    except Exception:
        return None


class GraphRepository:
    def __init__(self, connection: Neo4jConnection):
        self.connection = connection

    def _normalize_payload(self, payload: NodeInput) -> dict[str, Any]:
        if isinstance(payload, GraphNodePayload):
            properties = payload.to_properties()
        elif is_dataclass(payload):
            properties = asdict(payload)
        else:
            properties = dict(payload)
        return {key: value for key, value in properties.items() if value is not None}

    def upsert_node(self, label: str, payload: NodeInput) -> dict[str, Any]:
        properties = self._normalize_payload(payload)
        node_id = properties.get("id") or str(uuid4())
        created_at = properties.pop("created_at", None)
        updated_at = properties.pop("updated_at", None)
        properties["id"] = node_id

        query = build_merge_node_query(label)
        result = self.connection.execute_write(
            query,
            {
                "id": node_id,
                "properties": properties,
                "created_at": created_at,
                "updated_at": updated_at,
            },
        )
        return _serialize_neo4j(result[0]["node"]) if result else {}

    def get_node(self, label: str, node_id: str) -> dict[str, Any] | None:
        query = build_get_node_query(label)
        result = self.connection.execute_read(query, {"id": node_id})
        return _serialize_neo4j(result[0]["node"]) if result else None

    def find_nodes(
        self,
        label: str,
        filters: Mapping[str, Any] | None = None,
        *,
        sort_by: str | None = None,
        descending: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query, parameters = build_find_nodes_query(label, filters, sort_by, descending)
        parameters["limit"] = limit
        result = self.connection.execute_read(query, parameters)
        return [_serialize_neo4j(row["node"]) for row in result]

    def delete_node(self, label: str, node_id: str) -> int:
        query = build_delete_node_query(label)
        result = self.connection.execute_write(query, {"id": node_id})
        return int(result[0]["deleted_count"]) if result else 0

    def delete_all_data(self) -> int:
        result = self.connection.execute_write(
            """
            MATCH (n)
            WITH collect(n) AS nodes, count(n) AS deleted_count
            FOREACH (node IN nodes | DETACH DELETE node)
            RETURN deleted_count
            """
        )
        return int(result[0]["deleted_count"]) if result else 0

    def create_relationship(
        self,
        source_label: str,
        source_id: str,
        relationship_type: str,
        target_label: str,
        target_id: str,
        properties: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = build_merge_relationship_query(source_label, relationship_type, target_label)
        result = self.connection.execute_write(
            query,
            {
                "source_id": source_id,
                "target_id": target_id,
                "properties": dict(properties or {}),
            },
        )
        return _serialize_neo4j(result[0]) if result else {}

    def get_related_nodes(
        self,
        source_label: str,
        source_id: str,
        relationship_type: str,
        target_label: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query = build_get_related_nodes_query(source_label, relationship_type, target_label)
        result = self.connection.execute_read(
            query,
            {"source_id": source_id, "limit": limit},
        )
        return [_serialize_neo4j(row) for row in result]

    def delete_relationship(
        self,
        source_label: str,
        source_id: str,
        relationship_type: str,
        target_label: str,
        target_id: str,
    ) -> int:
        query = build_delete_relationship_query(source_label, relationship_type, target_label)
        result = self.connection.execute_write(
            query,
            {"source_id": source_id, "target_id": target_id},
        )
        return int(result[0]["deleted_count"]) if result else 0

    def upsert_entreprise(self, payload: Entreprise | Mapping[str, Any]) -> dict[str, Any]:
        return self.upsert_node("Entreprise", payload)

    def upsert_contact(self, payload: Contact | Mapping[str, Any]) -> dict[str, Any]:
        return self.upsert_node("Contact", payload)

    def upsert_opportunite(self, payload: Opportunite | Mapping[str, Any]) -> dict[str, Any]:
        return self.upsert_node("Opportunite", payload)

    def upsert_secteur(self, payload: Secteur | Mapping[str, Any]) -> dict[str, Any]:
        return self.upsert_node("Secteur", payload)

    def upsert_message(self, payload: Message | Mapping[str, Any]) -> dict[str, Any]:
        return self.upsert_node("Message", payload)

    def upsert_conversation(self, payload: Conversation | Mapping[str, Any]) -> dict[str, Any]:
        return self.upsert_node("Conversation", payload)

    def upsert_document(self, payload: Document | Mapping[str, Any]) -> dict[str, Any]:
        return self.upsert_node("Document", payload)

    def upsert_candidature(self, payload: Candidature | Mapping[str, Any]) -> dict[str, Any]:
        return self.upsert_node("Candidature", payload)

    def upsert_agent_action(self, payload: AgentAction | Mapping[str, Any]) -> dict[str, Any]:
        return self.upsert_node("AgentAction", payload)

    def upsert_besoin(self, payload: Besoin | Mapping[str, Any]) -> dict[str, Any]:
        return self.upsert_node("Besoin", payload)

    def upsert_profil_entreprise(
        self,
        payload: ProfilEntreprise | Mapping[str, Any],
    ) -> dict[str, Any]:
        return self.upsert_node("ProfilEntreprise", payload)
