from __future__ import annotations

from .connection import Neo4jConnection
from .models import Entreprise, Opportunite, Secteur
from .queries import build_schema_queries
from .repository import GraphRepository


class DatabaseSchemaManager:
    def __init__(self, connection: Neo4jConnection):
        self.connection = connection

    def initialize(self) -> None:
        for query in build_schema_queries():
            self.connection.execute_write(query)

    def seed_example_data(self) -> dict[str, dict]:
        repository = GraphRepository(self.connection)

        entreprise = repository.upsert_entreprise(
            Entreprise(
                nom="ABC Technologies",
                site_web="https://abc.ca",
                pays="Canada",
                ville="Montreal",
                score_confiance=0.87,
            )
        )
        secteur = repository.upsert_secteur(
            Secteur(nom="Technologie de l'information")
        )
        opportunite = repository.upsert_opportunite(
            Opportunite(
                titre="Developpement d'une application web",
                type="appel_offre",
                source="SEAO",
                statut="nouvelle",
                score_pertinence=0.92,
            )
        )

        repository.create_relationship(
            "Entreprise",
            entreprise["id"],
            "PUBLIE",
            "Opportunite",
            opportunite["id"],
        )
        repository.create_relationship(
            "Opportunite",
            opportunite["id"],
            "APPARTIENT_A",
            "Secteur",
            secteur["id"],
        )
        repository.create_relationship(
            "Entreprise",
            entreprise["id"],
            "TRAVAILLE_DANS",
            "Secteur",
            secteur["id"],
        )

        return {
            "entreprise": entreprise,
            "secteur": secteur,
            "opportunite": opportunite,
        }
