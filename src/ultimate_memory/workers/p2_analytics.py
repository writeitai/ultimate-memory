"""Graph analytics on the freshly built snapshot (p2 §7, D11 → D72).

PageRank (salience prior), k-core (hub-ness), weakly-connected components
(ER-health signal), and **Louvain community detection** all run natively in
the engine on the snapshot the rebuild just validated — Louvain included,
which D72 corrected after verifying it live on the deployed build (the
vendored survey behind D11 said it was absent, so the original plan carried
an external igraph pass; the simpler mechanism removes it).

Results are written **back to Postgres** and never reprojected into the
graph's node tables: analytics are graph-DERIVED, so loading them into the
projection would be circular (D6). Community *labels* — the K1 navigation
aid — are an optional batched micro-LLM call over each community's top
members by PageRank; without a provider the communities are unlabeled,
which costs navigation polish and nothing load-bearing.
"""

from typing import cast
from typing import Final
from uuid import NAMESPACE_URL
from uuid import UUID
from uuid import uuid5

import ladybug
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

from ultimate_memory.model import ModelRequest
from ultimate_memory.ports.model_provider import ModelProviderPort
from ultimate_memory.spine.projection import ProjectionCatalog

COMMUNITY_DETECTOR_VERSION: Final = "p2-communities-2026.07:louvain-native"
"""The analytics pass's component version (D12); the algorithm is part of
the identity because a detector swap changes every assignment."""

_PROJECTION: Final = "analytics_graph"
_LABEL_MEMBERS: Final = 8
"""How many top-PageRank members the labeling prompt sees per community."""

_LABEL_PROMPT: Final = (
    "These entities form one cluster in a knowledge graph. Give the cluster"
    " a short topic label (2-5 words) an agent could navigate by. Members,"
    " most central first:\n{members}"
)


class CommunityLabel(BaseModel):
    """The labeling call's structured output."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    label: str = Field(default="")


class AnalyticsSettings(BaseSettings):
    """The analytics pass's knobs (D70 port config; D22 numbers)."""

    model_config = SettingsConfigDict(env_prefix="UGM_P2_ANALYTICS_")

    label_model: str = Field(default="openai/gpt-5.6-luna")
    min_community_size_to_label: int = Field(default=3, ge=1)


class GraphAnalyticsWorker:
    """Compute snapshot analytics natively; write assignments to Postgres."""

    def __init__(
        self,
        *,
        catalog: ProjectionCatalog,
        model_provider: ModelProviderPort | None = None,
        settings: AnalyticsSettings | None = None,
    ) -> None:
        """Bind to the spine and (optionally) the labeling model seat."""
        self._catalog = catalog
        self._model_provider = model_provider
        self._settings = settings or AnalyticsSettings()

    def analyze(
        self, *, deployment_id: UUID, snapshot_id: UUID, connection: ladybug.Connection
    ) -> dict[str, int]:
        """Run every algorithm on the snapshot and write the results back."""
        connection.execute("INSTALL algo")
        connection.execute("LOAD algo")
        connection.execute(
            f"CALL PROJECT_GRAPH('{_PROJECTION}', ['Entity'], ['RELATES'])"
        )
        pagerank = _algorithm_scores(connection, algorithm="PAGE_RANK")
        k_core = _algorithm_scores(connection, algorithm="K_CORE_DECOMPOSITION")
        components = _algorithm_scores(
            connection, algorithm="WEAKLY_CONNECTED_COMPONENTS"
        )
        louvain = _algorithm_scores(connection, algorithm="LOUVAIN")
        degrees = _degrees(connection)
        names = _names(connection)

        members: dict[object, list[UUID]] = {}
        for entity_id, group in louvain.items():
            members.setdefault(group, []).append(entity_id)
        communities: list[dict[str, object]] = []
        community_ids: dict[object, UUID] = {}
        for group, group_members in sorted(
            members.items(), key=lambda item: str(item[0])
        ):
            # a stable id per (snapshot, group): re-running the pass on the
            # same snapshot rewrites its own rows instead of forking them
            community_id = uuid5(NAMESPACE_URL, f"ugm:community:{snapshot_id}:{group}")
            community_ids[group] = community_id
            communities.append(
                {
                    "community_id": community_id,
                    "label": self._label(
                        members=group_members, pagerank=pagerank, names=names
                    ),
                    "size": len(group_members),
                    "algorithm": "louvain",
                }
            )
        metrics = tuple(
            {
                "entity_id": entity_id,
                "community_id": community_ids.get(louvain.get(entity_id)),
                "pagerank": float(cast("float", pagerank.get(entity_id, 0.0))),
                "degree": int(cast("int", degrees.get(entity_id, 0))),
                "k_core": int(cast("int", k_core.get(entity_id, 0))),
                "component_id": uuid5(
                    NAMESPACE_URL,
                    f"ugm:component:{snapshot_id}:{components.get(entity_id)}",
                ),
            }
            for entity_id in names
        )
        self._catalog.record_graph_analytics(
            deployment_id=deployment_id,
            snapshot_id=snapshot_id,
            communities=tuple(communities),
            metrics=metrics,
        )
        return {"communities": len(communities), "entities": len(metrics)}

    def _label(
        self,
        *,
        members: list[UUID],
        pagerank: dict[UUID, object],
        names: dict[UUID, str],
    ) -> str | None:
        """A short navigation label from the community's most central members.

        Skipped for tiny communities and whenever no model seat is composed
        — labels are navigation aids (p2 §7); nothing load-bearing reads
        them, so their absence must never fail a rebuild.
        """
        if (
            self._model_provider is None
            or len(members) < self._settings.min_community_size_to_label
        ):
            return None
        central = sorted(
            members,
            key=lambda entity: float(cast("float", pagerank.get(entity, 0.0))),
            reverse=True,
        )[:_LABEL_MEMBERS]
        prompt = _LABEL_PROMPT.format(
            members="\n".join(f"- {names.get(entity, '')}" for entity in central)
        )
        try:
            response = self._model_provider.generate(
                request=ModelRequest(model=self._settings.label_model, prompt=prompt),
                response_type=CommunityLabel,
            )
        except Exception:  # noqa: BLE001 — a label never fails the analytics
            return None
        return response.label or None


def _algorithm_scores(
    connection: ladybug.Connection, *, algorithm: str
) -> dict[UUID, object]:
    """One algorithm's per-entity output, keyed by entity id."""
    result = connection.execute(f"CALL {algorithm}('{_PROJECTION}') RETURN *")
    assert isinstance(result, ladybug.QueryResult)
    scores: dict[UUID, object] = {}
    while result.has_next():
        row = cast("list[object]", result.get_next())
        node = cast("dict[str, object]", row[0])
        scores[cast("UUID", node["id"])] = row[1]
    return scores


def _degrees(connection: ladybug.Connection) -> dict[UUID, int]:
    """Relation degree per entity (undirected: the blast-radius input)."""
    result = connection.execute(
        "MATCH (e:Entity) OPTIONAL MATCH (e)-[r:RELATES]-() RETURN e.id, count(r)"
    )
    assert isinstance(result, ladybug.QueryResult)
    degrees: dict[UUID, int] = {}
    while result.has_next():
        row = cast("list[object]", result.get_next())
        degrees[cast("UUID", row[0])] = cast("int", row[1])
    return degrees


def _names(connection: ladybug.Connection) -> dict[UUID, str]:
    """Every emitted entity's canonical name (the labeling input)."""
    result = connection.execute("MATCH (e:Entity) RETURN e.id, e.name")
    assert isinstance(result, ladybug.QueryResult)
    names: dict[UUID, str] = {}
    while result.has_next():
        row = cast("list[object]", result.get_next())
        names[cast("UUID", row[0])] = cast("str", row[1])
    return names
