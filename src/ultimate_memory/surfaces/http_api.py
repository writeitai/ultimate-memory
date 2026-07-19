"""The HTTP API surface (WP-1.6): the query engine's primitives over FastAPI.

A thin, typed veneer: every endpoint delegates to one QueryEngine primitive
and returns the D49 envelope verbatim. The app is built per composed engine
(profiles own composition); the surface itself never touches adapters.
"""

from datetime import datetime
from uuid import UUID

from fastapi import FastAPI

from ultimate_memory.model import Envelope
from ultimate_memory.surfaces.query_engine import QueryEngine


def build_api(*, engine: QueryEngine, deployment_id: UUID) -> FastAPI:
    """Build one deployment's query API over a composed engine."""
    app = FastAPI(title="ultimate-memory query API", docs_url=None, redoc_url=None)

    @app.get("/resolve", response_model=Envelope)
    def resolve(name: str, entity_type: str | None = None) -> Envelope:
        """Resolve a name to ranked current entities (T0; S1/S39)."""
        return engine.resolve(
            deployment_id=deployment_id, name=name, entity_type=entity_type
        )

    @app.get("/lookup/relations", response_model=Envelope)
    def lookup_relations(
        subject_entity_id: UUID | None = None,
        predicate: str | None = None,
        object_entity_id: UUID | None = None,
        valid_at: datetime | None = None,
    ) -> Envelope:
        """Relations matching an (s, p, o) pattern — current, or as-of (S9)."""
        return engine.lookup_relations(
            deployment_id=deployment_id,
            subject_entity_id=subject_entity_id,
            predicate=predicate,
            object_entity_id=object_entity_id,
            valid_at=valid_at,
        )

    @app.get("/transcript/relation/{relation_id}", response_model=Envelope)
    def transcript_relation(relation_id: UUID) -> Envelope:
        """The S8 audit query: why the system believes what it believes."""
        return engine.transcript_relation(
            deployment_id=deployment_id, relation_id=relation_id
        )

    @app.get("/lookup/observations", response_model=Envelope)
    def lookup_observations(
        entity_id: UUID, property_query: str | None = None, k: int = 10
    ) -> Envelope:
        """Live observations on one entity, semantic over statements (S2)."""
        return engine.lookup_observations(
            deployment_id=deployment_id,
            entity_id=entity_id,
            property_query=property_query,
            k=k,
        )

    @app.get("/search/claims", response_model=Envelope)
    def search_claims(query: str, k: int = 10) -> Envelope:
        """Semantic claim search — evidence grain, never current-fact truth."""
        return engine.search_claims(deployment_id=deployment_id, query=query, k=k)

    @app.get("/hydrate/relation/{relation_id}", response_model=Envelope)
    def hydrate_relation(relation_id: UUID) -> Envelope:
        """The S5 chain: relation → evidence claims → source documents."""
        return engine.hydrate_relation(
            deployment_id=deployment_id, relation_id=relation_id
        )

    return app
