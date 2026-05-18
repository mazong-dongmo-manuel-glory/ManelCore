from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

DEFAULT_NODE_LABELS: tuple[str, ...] = (
    "Entreprise",
    "Contact",
    "Opportunite",
    "Secteur",
    "Message",
    "Conversation",
    "Document",
    "Candidature",
    "AgentAction",
    "Besoin",
    "ProfilEntreprise",
)

DEFAULT_INDEXES: dict[str, tuple[str, ...]] = {
    "Entreprise": ("nom", "site_web", "secteur_principal", "ville", "pays"),
    "Contact": ("email", "nom", "linkedin"),
    "Opportunite": ("titre", "type", "source", "statut", "date_limite", "seao_uuid", "score_pertinence"),
    "Secteur": ("nom",),
    "Message": ("canal", "direction", "intent", "classification", "from_email", "uid_imap", "compte_recepteur", "date_envoi"),
    "Conversation": ("canal", "statut"),
    "Document": ("type", "nom", "embedding_id"),
    "Candidature": ("statut", "date_soumission"),
    "AgentAction": ("type", "statut"),
    "Besoin": ("nom", "priorite"),
}


def validate_identifier(identifier: str, kind: str = "identifier") -> str:
    if not IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(f"{kind} invalide: {identifier}")
    return identifier


def build_filter_clause(
    alias: str,
    filters: Mapping[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    if not filters:
        return "", {}

    clauses: list[str] = []
    parameters: dict[str, Any] = {}

    for key, value in filters.items():
        safe_key = validate_identifier(key, "property name")
        parameter_name = f"{alias}_{safe_key}"
        clauses.append(f"{alias}.{safe_key} = ${parameter_name}")
        parameters[parameter_name] = value

    return "WHERE " + " AND ".join(clauses), parameters


def build_merge_node_query(label: str) -> str:
    safe_label = validate_identifier(label, "node label")
    return f"""
    MERGE (n:{safe_label} {{id: $id}})
    ON CREATE SET n.created_at = coalesce($created_at, datetime())
    SET n += $properties, n.updated_at = coalesce($updated_at, datetime())
    RETURN properties(n) AS node
    """.strip()


def build_get_node_query(label: str) -> str:
    safe_label = validate_identifier(label, "node label")
    return f"""
    MATCH (n:{safe_label} {{id: $id}})
    RETURN properties(n) AS node
    """.strip()


def build_find_nodes_query(
    label: str,
    filters: Mapping[str, Any] | None = None,
    sort_by: str | None = None,
    descending: bool = False,
) -> tuple[str, dict[str, Any]]:
    safe_label = validate_identifier(label, "node label")
    where_clause, parameters = build_filter_clause("n", filters)

    order_clause = ""
    if sort_by:
        safe_sort = validate_identifier(sort_by, "sort field")
        order_clause = f"ORDER BY n.{safe_sort} {'DESC' if descending else 'ASC'}"

    query = f"""
    MATCH (n:{safe_label})
    {where_clause}
    RETURN properties(n) AS node
    {order_clause}
    LIMIT $limit
    """.strip()
    return query, parameters


def build_delete_node_query(label: str) -> str:
    safe_label = validate_identifier(label, "node label")
    return f"""
    MATCH (n:{safe_label} {{id: $id}})
    WITH collect(n) AS nodes, count(n) AS deleted_count
    FOREACH (node IN nodes | DETACH DELETE node)
    RETURN deleted_count
    """.strip()


def build_merge_relationship_query(
    source_label: str,
    relationship_type: str,
    target_label: str,
) -> str:
    safe_source = validate_identifier(source_label, "source label")
    safe_relationship = validate_identifier(relationship_type, "relationship type")
    safe_target = validate_identifier(target_label, "target label")
    return f"""
    MATCH (source:{safe_source} {{id: $source_id}})
    MATCH (target:{safe_target} {{id: $target_id}})
    MERGE (source)-[r:{safe_relationship}]->(target)
    ON CREATE SET r.created_at = datetime()
    SET r += $properties, r.updated_at = datetime()
    RETURN properties(source) AS source, properties(r) AS relationship, properties(target) AS target
    """.strip()


def build_delete_relationship_query(
    source_label: str,
    relationship_type: str,
    target_label: str,
) -> str:
    safe_source = validate_identifier(source_label, "source label")
    safe_relationship = validate_identifier(relationship_type, "relationship type")
    safe_target = validate_identifier(target_label, "target label")
    return f"""
    MATCH (source:{safe_source} {{id: $source_id}})-[r:{safe_relationship}]->(target:{safe_target} {{id: $target_id}})
    WITH collect(r) AS relationships, count(r) AS deleted_count
    FOREACH (relationship IN relationships | DELETE relationship)
    RETURN deleted_count
    """.strip()


def build_get_related_nodes_query(
    source_label: str,
    relationship_type: str,
    target_label: str,
) -> str:
    safe_source = validate_identifier(source_label, "source label")
    safe_relationship = validate_identifier(relationship_type, "relationship type")
    safe_target = validate_identifier(target_label, "target label")
    return f"""
    MATCH (source:{safe_source} {{id: $source_id}})-[r:{safe_relationship}]->(target:{safe_target})
    RETURN properties(target) AS node, properties(r) AS relationship
    LIMIT $limit
    """.strip()


def build_unique_id_constraints(labels: Iterable[str]) -> list[str]:
    queries: list[str] = []
    for label in labels:
        safe_label = validate_identifier(label, "node label")
        queries.append(
            f"CREATE CONSTRAINT {safe_label.lower()}_id_unique IF NOT EXISTS "
            f"FOR (n:{safe_label}) REQUIRE n.id IS UNIQUE"
        )
    return queries


def build_property_indexes(indexes: Mapping[str, Iterable[str]]) -> list[str]:
    queries: list[str] = []
    for label, fields in indexes.items():
        safe_label = validate_identifier(label, "node label")
        for field in fields:
            safe_field = validate_identifier(field, "property name")
            queries.append(
                f"CREATE INDEX {safe_label.lower()}_{safe_field}_idx IF NOT EXISTS "
                f"FOR (n:{safe_label}) ON (n.{safe_field})"
            )
    return queries


def build_schema_queries() -> list[str]:
    return [
        *build_unique_id_constraints(DEFAULT_NODE_LABELS),
        *build_property_indexes(DEFAULT_INDEXES),
    ]
