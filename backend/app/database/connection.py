from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase, Result, Transaction


@dataclass(slots=True)
class Neo4jSettings:
    uri: str
    username: str
    password: str
    database: str = "neo4j"

    @classmethod
    def from_env(cls) -> "Neo4jSettings":
        load_dotenv()
        return cls(
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            username=os.getenv("NEO4J_USERNAME", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", ""),
            database=os.getenv("NEO4J_DATABASE", "neo4j"),
        )


class Neo4jConnection:
    def __init__(self, settings: Neo4jSettings | None = None):
        self.settings = settings or Neo4jSettings.from_env()
        auth = None
        if self.settings.username or self.settings.password:
            auth = (self.settings.username, self.settings.password)
        self._driver: Driver = GraphDatabase.driver(self.settings.uri, auth=auth)

    @staticmethod
    def _run_query(
        tx: Transaction,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        result: Result = tx.run(query, parameters or {})
        return [record.data() for record in result]

    def verify(self) -> None:
        self._driver.verify_connectivity()

    def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        with self._driver.session(database=self.settings.database) as session:
            return session.execute_read(self._run_query, query, parameters or {})

    def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        with self._driver.session(database=self.settings.database) as session:
            return session.execute_write(self._run_query, query, parameters or {})

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "Neo4jConnection":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()
