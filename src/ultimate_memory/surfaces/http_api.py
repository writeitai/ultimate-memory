"""The HTTP API surface (WP-1.6/WP-5.4): primitives and recipes over FastAPI.

A thin, typed veneer: every endpoint delegates to one QueryEngine primitive or
runs one recipe through the shared `RecipeSurface`, and returns the D49
envelope verbatim. The recipe endpoints render from the registry — `/recipes`
IS the registry's active rows — so the CLI and MCP surfaces stay in lockstep
by construction (they render the same surface).

The API is the one place authorization is enforced for query-engine reads
(retrieval §9): a deployment that passes an `AuthPerimeterPort` gets every
endpoint gated on a valid perimeter credential for THIS deployment — a single
trust domain, never per-request tenancy. With no port, the perimeter is
infrastructure's job and the app is open (the self-host default). The surface
itself never touches adapters.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import Body
from fastapi import Depends
from fastapi import FastAPI
from fastapi import Header
from fastapi import HTTPException
from pydantic import SecretBytes

from ultimate_memory.model import AuthenticatedContext
from ultimate_memory.model import Envelope
from ultimate_memory.model import PerimeterCredential
from ultimate_memory.ports.auth import AuthPerimeterPort
from ultimate_memory.surfaces.query_engine import QueryEngine
from ultimate_memory.surfaces.recipe_surface import MissingArgumentError
from ultimate_memory.surfaces.recipe_surface import RecipeSurface
from ultimate_memory.surfaces.recipe_surface import ToolDescriptor
from ultimate_memory.surfaces.recipe_surface import UnknownRecipeError


def build_api(
    *,
    engine: QueryEngine,
    deployment_id: UUID,
    surface: RecipeSurface | None = None,
    auth: AuthPerimeterPort | None = None,
) -> FastAPI:
    """Build one deployment's query API over a composed engine.

    `surface` adds the registry-rendered recipe endpoints (`/recipes` and
    `/recipe/{name}`); `auth` gates every endpoint on a perimeter credential
    for this deployment. Both are optional — the primitives alone, open, are
    the Phase-1 shape.
    """
    dependencies = (
        [Depends(_perimeter(auth=auth, deployment_id=deployment_id))]
        if auth is not None
        else []
    )
    app = FastAPI(
        title="ultimate-memory query API",
        docs_url=None,
        redoc_url=None,
        dependencies=dependencies,
    )

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

    if surface is not None:
        _mount_recipes(app=app, surface=surface)

    return app


def _mount_recipes(*, app: FastAPI, surface: RecipeSurface) -> None:
    """Add the registry-rendered recipe endpoints to the app (D50)."""

    @app.get("/recipes", response_model=list[ToolDescriptor])
    def list_recipes() -> list[ToolDescriptor]:
        """The recipe tool list — this deployment's active registry rows."""
        return list(surface.descriptors())

    @app.post("/recipe/{name}", response_model=Envelope)
    def run_recipe(
        name: str, arguments: Annotated[dict[str, object], Body(default_factory=dict)]
    ) -> Envelope:
        """Run one recipe by name over JSON arguments (the D50 executor)."""
        try:
            return surface.run(name=name, arguments=arguments)
        except UnknownRecipeError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except MissingArgumentError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error


def _perimeter(*, auth: AuthPerimeterPort, deployment_id: UUID):  # noqa: ANN202
    """A FastAPI dependency that authenticates the perimeter credential.

    The `Authorization: <scheme> <value>` header is handed to the configured
    port; a failure, a missing header, or a credential for another deployment
    is a 401/403 before any read runs. This is the single enforcement point
    (retrieval §9) — inside, it is one trust domain.
    """

    def dependency(
        authorization: str | None = Header(default=None),
    ) -> AuthenticatedContext:
        if not authorization:
            raise HTTPException(
                status_code=401, detail="a perimeter credential is required"
            )
        scheme, _, value = authorization.partition(" ")
        try:
            context = auth.authenticate(
                credential=PerimeterCredential(
                    scheme=scheme, value=SecretBytes(value.encode("utf-8"))
                )
            )
        except Exception as error:  # any auth failure is an opaque 401
            raise HTTPException(
                status_code=401, detail="perimeter authentication failed"
            ) from error
        if context.deployment_id != deployment_id:
            raise HTTPException(
                status_code=403, detail="credential is for another deployment"
            )
        return context

    return dependency
