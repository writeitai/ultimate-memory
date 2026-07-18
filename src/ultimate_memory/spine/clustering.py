"""Clustering & reversibility (D21, registries §6): gather, decide, undo.

Pairwise cascade guesses never chain (no transitive closure): the gather
stage collects a candidate blob through blocking links, and the decide stage
splits it with hierarchical agglomerative clustering (centroid linkage on
profile-embedding cosine distance) cut at a threshold — each piece below the
cut is one entity, a blob is never automatically one entity. New mentions
re-decide their 1-hop NEIGHBORHOOD jointly, so the grouping is independent of
arrival order. Every merge is a redirect with a pre-merge snapshot; un-merge
replays it. Blast radius routes big merges to review instead of auto (D24);
the black-hole guard tightens the bar on runaway blobs.
"""

from uuid import UUID
from uuid import uuid4

from sqlalchemy import bindparam
from sqlalchemy import JSON
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.engine import Engine

from ultimate_memory.model import ClusterConfig
from ultimate_memory.model import MergeProposal
from ultimate_memory.model import NeighborhoodReport
from ultimate_memory.model import UnmergeError
from ultimate_memory.ports.p1_index import EntityIndexPort
from ultimate_memory.spine.entity_registry import normalized_lemma


class EntityClusterer:
    """Neighborhood re-decision, reversible merges, and the guards (D21)."""

    def __init__(
        self, *, engine: Engine, entity_index: EntityIndexPort, config: ClusterConfig
    ) -> None:
        """Bind the clusterer to the registry, the profile index, and config."""
        self._engine = engine
        self._entity_index = entity_index
        self._config = config

    def recluster_neighborhood(
        self, *, deployment_id: UUID, surface: str
    ) -> NeighborhoodReport:
        """Jointly re-decide the surface's 1-hop neighborhood (nDR).

        Gather: active entities whose aliases block-reach the surface's lemma
        (trigram + phonetic — the same reach as resolution blocking). Decide:
        HAC over profile vectors with the distance cut; each multi-entity
        piece becomes a reversible merge (or a review item above the
        blast-radius cap). Joint re-decision makes the outcome independent of
        the order documents arrived in (registries §6).
        """
        lemma = normalized_lemma(surface=surface)
        with self._engine.begin() as connection:
            connection.execute(_LOCK_NEIGHBORHOOD, {"key": f"{deployment_id}:cluster"})
            members = self._gather(
                connection=connection, deployment_id=deployment_id, lemma=lemma
            )
            if len(members) < 2:
                return NeighborhoodReport(members=len(members))
            # re-deciding the pocket JOINTLY may move a previously-merged
            # member to a different group (the R. Klein case): first split
            # every merged member whose piece disagrees with its current
            # root, then apply the piece merges (registries §6).
            cut = self._config.distance_cut
            tightened = False
            if len(members) > self._config.blob_cap:
                # black-hole guard: raise the matching bar and re-split
                # rather than swallow the monster (registries §6)
                cut = cut / 2.0
                tightened = True
            vectors = self._entity_index.entity_vectors(
                deployment_id=str(deployment_id),
                entity_ids=tuple(str(m["entity_id"]) for m in members),
            )
            pieces = _hac_pieces(members=members, vectors=vectors, distance_cut=cut)
            for piece in pieces:
                self._split_disagreeing_members(
                    connection=connection, deployment_id=deployment_id, piece=piece
                )
            merged: list[UUID] = []
            queued = 0
            for proposal in self._proposals(
                connection=connection, deployment_id=deployment_id, pieces=pieces
            ):
                if proposal.blast_radius > self._config.blast_radius_cap:
                    self._queue_for_review(
                        connection=connection,
                        deployment_id=deployment_id,
                        proposal=proposal,
                        trigger_lemma=lemma,
                    )
                    queued += 1
                    continue
                merged.extend(
                    self._merge(
                        connection=connection,
                        deployment_id=deployment_id,
                        proposal=proposal,
                        trigger_lemma=lemma,
                    )
                )
            return NeighborhoodReport(
                members=len(members),
                merged=tuple(merged),
                queued_for_review=queued,
                black_hole_tightened=tightened,
            )

    def unmerge(self, *, deployment_id: UUID, merge_id: UUID) -> UUID:
        """Reverse one merge by replaying its snapshot (D21).

        The absorbed entity becomes active again (redirect removed); a
        reversal event is appended and linked from the original — nothing is
        overwritten, the full history survives. Returns the reversal id.
        """
        with self._engine.begin() as connection:
            event = (
                connection.execute(
                    _SELECT_MERGE_LOCKED,
                    {"deployment_id": deployment_id, "merge_id": merge_id},
                )
                .mappings()
                .one_or_none()
            )
            if event is None:
                raise UnmergeError(f"merge event {merge_id} does not exist")
            if event["reversed_by"] is not None:
                raise UnmergeError(f"merge event {merge_id} is already reversed")
            full_event = {**event, "merge_id": merge_id}
            reversal_id = self._reverse_event(
                connection=connection, deployment_id=deployment_id, event=full_event
            )
        return reversal_id

    def _reverse_event(
        self, *, connection: Connection, deployment_id: UUID, event: dict[str, object]
    ) -> UUID:
        """Reverse one live merge: restore, replay the snapshot, link.

        Snapshot replay (Codex review): any mention that belonged to the
        absorbed entity pre-merge but whose live decision now points
        elsewhere gets a superseding decision restoring it — the membership
        picture returns to the snapshot, not just the redirect.
        """
        absorbed_id = event["absorbed_id"]
        connection.execute(
            _RESTORE_ABSORBED,
            {"deployment_id": deployment_id, "entity_id": absorbed_id},
        )
        snapshot = event["pre_merge_membership_snapshot"]
        mentions = (
            snapshot.get("mentions_by_entity", {}).get(str(absorbed_id), [])
            if isinstance(snapshot, dict)
            else []
        )
        for mention_id in mentions:
            self._restore_mention_decision(
                connection=connection,
                deployment_id=deployment_id,
                mention_id=UUID(str(mention_id)),
                entity_id=UUID(str(absorbed_id)),
            )
        reversal_id = uuid4()
        connection.execute(
            _INSERT_MERGE_EVENT,
            {
                "merge_id": reversal_id,
                "deployment_id": deployment_id,
                "survivor_id": absorbed_id,
                "absorbed_id": event["survivor_id"],
                "trigger_lemmas": [],
                "evidence": {"unmerge_of": str(event["merge_id"])},
                "blast_radius": event["blast_radius"],
                "snapshot": snapshot,
                "decided_by": "human",
            },
        )
        marked = connection.execute(
            _MARK_REVERSED, {"merge_id": event["merge_id"], "reversal_id": reversal_id}
        ).rowcount
        if marked != 1:
            raise UnmergeError(
                f"merge event {event['merge_id']} was reversed concurrently"
            )
        return reversal_id

    def _restore_mention_decision(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        mention_id: UUID,
        entity_id: UUID,
    ) -> None:
        """Re-point one mention to its pre-merge entity, superseding (D17)."""
        live = (
            connection.execute(
                _LIVE_DECISION_FOR_MENTION,
                {"deployment_id": deployment_id, "mention_id": mention_id},
            )
            .mappings()
            .one_or_none()
        )
        if live is None or live["entity_id"] == entity_id:
            return
        restored_id = uuid4()
        connection.execute(
            _INSERT_RESTORE_DECISION,
            {
                "decision_id": restored_id,
                "deployment_id": deployment_id,
                "mention_id": mention_id,
                "entity_id": entity_id,
                "resolver_version": str(live["resolver_version"]),
            },
        )
        connection.execute(
            _SUPERSEDE_DECISION,
            {"decision_id": live["decision_id"], "superseded_by": restored_id},
        )

    def _gather(
        self, *, connection: Connection, deployment_id: UUID, lemma: str
    ) -> list[dict[str, object]]:
        """The 1-hop neighborhood, REDIRECTS INCLUDED (Codex review).

        Absorbed entities stay reachable through their aliases and appear as
        members with their own vectors plus their current survivor root — so
        a later arrival can trigger the joint re-decision that moves them.
        Hub-triggered 2-hop extension is a documented follow-up.
        """
        return [
            dict(row)
            for row in connection.execute(
                _GATHER_NEIGHBORHOOD, {"deployment_id": deployment_id, "lemma": lemma}
            ).mappings()
        ]

    def _split_disagreeing_members(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        piece: tuple[dict[str, object], ...],
    ) -> None:
        """Unmerge every merged member whose piece disagrees with its root.

        The joint decision is authoritative for the pocket: a member absorbed
        into an entity OUTSIDE its piece (or alone in a singleton piece) is
        split back out by reversing its live merge event — then the piece
        merges (if any) re-attach it where the joint decision says.
        """
        piece_ids = {str(member["entity_id"]) for member in piece}
        for member in piece:
            root = member.get("current_root")
            if root is None or str(root) == str(member["entity_id"]):
                continue  # active, or its own root
            if str(root) in piece_ids and len(piece) > 1:
                continue  # its survivor is in the same piece: agreement
            event = (
                connection.execute(
                    _LIVE_MERGE_OF,
                    {
                        "deployment_id": deployment_id,
                        "absorbed_id": member["entity_id"],
                    },
                )
                .mappings()
                .one_or_none()
            )
            if event is not None:
                self._reverse_event(
                    connection=connection,
                    deployment_id=deployment_id,
                    event=dict(event),
                )

    def _proposals(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        pieces: tuple[tuple[dict[str, object], ...], ...],
    ) -> tuple[MergeProposal, ...]:
        """Turn multi-entity pieces into proposals with live blast radii."""
        proposals: list[MergeProposal] = []
        for piece in pieces:
            if len(piece) < 2:
                continue
            ordered = sorted(
                piece, key=lambda m: (m["first_seen"], str(m["entity_id"]))
            )
            ids = [UUID(str(member["entity_id"])) for member in ordered]
            blast = connection.execute(
                _BLAST_RADIUS, {"deployment_id": deployment_id, "entity_ids": ids}
            ).scalar_one()
            proposals.append(
                MergeProposal(
                    survivor_id=ids[0],
                    absorbed_ids=tuple(ids[1:]),
                    blast_radius=blast,
                    mean_distance=0.0,
                )
            )
        return tuple(proposals)

    def _merge(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        proposal: MergeProposal,
        trigger_lemma: str,
    ) -> list[UUID]:
        """Redirect each absorbed entity into the survivor, snapshot first."""
        events: list[UUID] = []
        for absorbed_id in proposal.absorbed_ids:
            snapshot = _membership_snapshot(
                connection=connection,
                deployment_id=deployment_id,
                entity_ids=(proposal.survivor_id, absorbed_id),
            )
            redirected = connection.execute(
                _REDIRECT_ABSORBED,
                {
                    "deployment_id": deployment_id,
                    "entity_id": absorbed_id,
                    "survivor_id": proposal.survivor_id,
                },
            ).rowcount
            if redirected != 1:
                continue  # already merged here (piece agreement): no new event
            merge_id = uuid4()
            connection.execute(
                _INSERT_MERGE_EVENT,
                {
                    "merge_id": merge_id,
                    "deployment_id": deployment_id,
                    "survivor_id": proposal.survivor_id,
                    "absorbed_id": absorbed_id,
                    "trigger_lemmas": [trigger_lemma],
                    "evidence": {"mean_distance": proposal.mean_distance},
                    "blast_radius": proposal.blast_radius,
                    "snapshot": snapshot,
                    "decided_by": "auto",
                },
            )
            events.append(merge_id)
        return events

    def _queue_for_review(
        self,
        *,
        connection: Connection,
        deployment_id: UUID,
        proposal: MergeProposal,
        trigger_lemma: str,
    ) -> None:
        """Hub merges never auto (registries §6/D24): rank by expected impact."""
        confidence = 0.5  # cluster-level confidence; refined with WP-2.6 cards
        connection.execute(
            _INSERT_REVIEW,
            {
                "review_id": uuid4(),
                "deployment_id": deployment_id,
                "candidate": {
                    "survivor_id": str(proposal.survivor_id),
                    "absorbed_ids": [str(a) for a in proposal.absorbed_ids],
                    "trigger_lemma": trigger_lemma,
                },
                "blast_radius": proposal.blast_radius,
                "confidence": confidence,
                "expected_impact": proposal.blast_radius * (1.0 - confidence),
            },
        )


def _hac_pieces(
    *,
    members: list[dict[str, object]],
    vectors: dict[str, tuple[float, ...]],
    distance_cut: float,
) -> tuple[tuple[dict[str, object], ...], ...]:
    """Agglomerative clustering, centroid linkage, cut at `distance_cut`.

    Members without a profile vector stay singletons — a missing profile is
    never merge evidence (the paranoid direction). Deterministic: ties break
    on entity id, so the same member set always yields the same pieces.
    """
    clusters: list[tuple[list[dict[str, object]], tuple[float, ...] | None]] = []
    for member in sorted(members, key=lambda m: str(m["entity_id"])):
        vector = vectors.get(str(member["entity_id"]))
        clusters.append(([member], vector))
    while True:
        best: tuple[int, int, float] | None = None
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                left, right = clusters[i][1], clusters[j][1]
                if left is None or right is None:
                    continue
                distance = 1.0 - _cosine(left, right)
                if distance <= distance_cut and (best is None or distance < best[2]):
                    best = (i, j, distance)
        if best is None:
            break
        i, j, _ = best
        merged_members = clusters[i][0] + clusters[j][0]
        merged_centroid = _centroid(
            [c for c in (clusters[i][1], clusters[j][1]) if c is not None]
        )
        clusters = [cluster for k, cluster in enumerate(clusters) if k not in (i, j)]
        clusters.append((merged_members, merged_centroid))
    return tuple(tuple(cluster[0]) for cluster in clusters)


def _membership_snapshot(
    *, connection: Connection, deployment_id: UUID, entity_ids: tuple[UUID, ...]
) -> dict[str, object]:
    """The before picture: which mentions belong to which entity (D21)."""
    rows = connection.execute(
        _SNAPSHOT_MEMBERSHIP,
        {"deployment_id": deployment_id, "entity_ids": list(entity_ids)},
    ).all()
    snapshot: dict[str, list[str]] = {str(e): [] for e in entity_ids}
    for entity_id, mention_id in rows:
        snapshot[str(entity_id)].append(str(mention_id))
    return {"mentions_by_entity": snapshot}


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Cosine similarity of two same-dimension vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _centroid(vectors: list[tuple[float, ...]]) -> tuple[float, ...]:
    """The mean vector (centroid linkage)."""
    return tuple(sum(axis) / len(vectors) for axis in zip(*vectors, strict=True))


_LOCK_NEIGHBORHOOD = text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))")

_GATHER_NEIGHBORHOOD = text(
    """
    WITH RECURSIVE reached AS (
        SELECT DISTINCT entities.entity_id, entities.canonical_name,
               entities.created_at, entities.status, entities.merged_into
        FROM aliases
        JOIN entities ON entities.deployment_id = aliases.deployment_id
                     AND entities.entity_id = aliases.entity_id
        WHERE aliases.deployment_id = :deployment_id
          AND entities.status IN ('active', 'merged')
          AND (similarity(aliases.normalized_lemma, :lemma) >= 0.3
               OR daitch_mokotoff(aliases.normalized_lemma)
                  && daitch_mokotoff(:lemma))
    ),
    rooted AS (
        SELECT entity_id, canonical_name, created_at, status, merged_into,
               entity_id AS current_root
        FROM reached WHERE status = 'active'
        UNION ALL
        SELECT r.entity_id, r.canonical_name, r.created_at, r.status,
               r.merged_into, e.entity_id
        FROM (
            SELECT reached.*, reached.merged_into AS walk FROM reached
            WHERE status = 'merged'
        ) r
        JOIN entities e ON e.entity_id = r.walk AND e.status = 'active'
    )
    SELECT DISTINCT entity_id, canonical_name,
           created_at AS first_seen, current_root
    FROM rooted
    """
)

_BLAST_RADIUS = text(
    """
    SELECT coalesce(sum(mention_count + graph_degree), 0)::int
    FROM entities
    WHERE deployment_id = :deployment_id
      AND entity_id = ANY(:entity_ids)
    """
)

_SNAPSHOT_MEMBERSHIP = text(
    """
    SELECT entity_id, mention_id FROM resolution_decisions
    WHERE deployment_id = :deployment_id
      AND entity_id = ANY(:entity_ids)
      AND superseded_by IS NULL
    ORDER BY decided_at
    """
)

_INSERT_MERGE_EVENT = text(
    """
    INSERT INTO merge_events (
        merge_id, deployment_id, survivor_id, absorbed_id, trigger_lemmas,
        evidence, blast_radius, pre_merge_membership_snapshot, decided_by
    ) VALUES (
        :merge_id, :deployment_id, :survivor_id, :absorbed_id, :trigger_lemmas,
        :evidence, :blast_radius, :snapshot, :decided_by
    )
    """
).bindparams(bindparam("evidence", type_=JSON), bindparam("snapshot", type_=JSON))

_REDIRECT_ABSORBED = text(
    """
    UPDATE entities
    SET status = 'merged', merged_into = :survivor_id, updated_at = now()
    WHERE deployment_id = :deployment_id AND entity_id = :entity_id
      AND status = 'active'
    """
)

_RESTORE_ABSORBED = text(
    """
    UPDATE entities
    SET status = 'active', merged_into = NULL, updated_at = now()
    WHERE deployment_id = :deployment_id AND entity_id = :entity_id
      AND status = 'merged'
    """
)

_SELECT_MERGE = text(
    """
    SELECT survivor_id, absorbed_id, blast_radius,
           pre_merge_membership_snapshot, reversed_by
    FROM merge_events
    WHERE deployment_id = :deployment_id AND merge_id = :merge_id
    """
)

_MARK_REVERSED = text(
    "UPDATE merge_events SET reversed_by = :reversal_id WHERE merge_id = :merge_id"
)

_INSERT_REVIEW = text(
    """
    INSERT INTO review_queue (
        review_id, deployment_id, item_kind, candidate, blast_radius,
        confidence, expected_impact
    ) VALUES (
        :review_id, :deployment_id, 'merge_cluster', :candidate, :blast_radius,
        :confidence, :expected_impact
    )
    """
).bindparams(bindparam("candidate", type_=JSON))

_SELECT_MERGE_LOCKED = text(
    """
    SELECT survivor_id, absorbed_id, blast_radius,
           pre_merge_membership_snapshot, reversed_by
    FROM merge_events
    WHERE deployment_id = :deployment_id AND merge_id = :merge_id
    FOR UPDATE
    """
)

_LIVE_MERGE_OF = text(
    """
    SELECT merge_id, survivor_id, absorbed_id, blast_radius,
           pre_merge_membership_snapshot
    FROM merge_events
    WHERE deployment_id = :deployment_id
      AND absorbed_id = :absorbed_id
      AND reversed_by IS NULL
    ORDER BY decided_at DESC
    LIMIT 1
    FOR UPDATE
    """
)

_LIVE_DECISION_FOR_MENTION = text(
    """
    SELECT decision_id, entity_id, resolver_version
    FROM resolution_decisions
    WHERE deployment_id = :deployment_id
      AND mention_id = :mention_id
      AND superseded_by IS NULL
    ORDER BY decided_at DESC
    LIMIT 1
    """
)

_INSERT_RESTORE_DECISION = text(
    """
    INSERT INTO resolution_decisions (
        decision_id, deployment_id, mention_id, entity_id, method,
        confidence, is_new_entity, features, resolver_version, decided_by
    ) VALUES (
        :decision_id, :deployment_id, :mention_id, :entity_id, 'human',
        1.0, false, '{"unmerge_replay": true}', :resolver_version, 'human'
    )
    """
)

_SUPERSEDE_DECISION = text(
    """
    UPDATE resolution_decisions SET superseded_by = :superseded_by
    WHERE decision_id = :decision_id
    """
)
