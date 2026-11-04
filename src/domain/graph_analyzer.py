"""Skill intelligence graph analyzer for job market analysis.

This module provides graph-based analysis of skill co-occurrence patterns
from job applications to identify learning priorities and skill relationships.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True, slots=True)
class SkillMetrics:
    """Metrics for a skill in the job market graph.

    Attributes:
        name: Canonical skill name (e.g., "React", "PostgreSQL").
        demand: Number of job postings requiring this skill.
        centrality_degree: Normalized degree centrality (0.0-1.0).
        centrality_betweenness: Normalized betweenness centrality (0.0-1.0).
        community_id: Community identifier from Louvain clustering.
        mastery_level: User's self-assessed mastery (0.0-1.0).
        priority_score: Computed priority = demand * (1 - mastery).
    """

    name: str
    demand: int
    centrality_degree: float
    centrality_betweenness: float
    community_id: int
    mastery_level: float
    priority_score: float


@dataclass(frozen=True, slots=True)
class AssociationRule:
    """Association rule mined from skill co-occurrence (FP-Growth style).

    Attributes:
        antecedent: Frozen set of prerequisite skills.
        consequent: Frozen set of implied skills.
        support: Fraction of applications containing both antecedent and consequent.
        confidence: P(consequent | antecedent).
        lift: confidence / P(consequent), > 1 indicates positive correlation.
    """

    antecedent: frozenset[str]
    consequent: frozenset[str]
    support: float
    confidence: float
    lift: float


class GraphAnalyzer:
    """Analyzes skill co-occurrence graphs from job applications.

    Builds a NetworkX graph where nodes are skills weighted by demand,
    edges represent co-occurrence frequency (threshold >= 2).
    Provides community detection, centrality metrics, and association rule mining.

    Example:
        >>> analyzer = GraphAnalyzer()
        >>> analyzer.build_from_applications(applications)
        >>> metrics = analyzer.get_skill_metrics(mastery_levels)
        >>> matrix = analyzer.get_learning_priority_matrix(top_k=20)
    """

    MIN_CO_OCCURRENCE: int = 2
    MIN_SUPPORT: float = 0.05
    MIN_CONFIDENCE: float = 0.7

    def __init__(self) -> None:
        """Initialize analyzer with empty state."""
        self._graph: object | None = None
        self._skill_to_index: dict[str, int] = {}
        self._index_to_skill: list[str] = []
        self._communities: dict[str, int] = {}
        self._association_rules: list[AssociationRule] = []
        self._total_applications: int = 0

    def build_from_applications(
        self,
        applications: Iterable[Iterable[str]],
    ) -> GraphAnalyzer:
        """Build co-occurrence graph from job application skill sets.

        Args:
            applications: Iterable of iterables, each containing skill names
                for a single job posting (only matched skills).

        Returns:
            Self for method chaining.
        """
        self._skill_to_index.clear()
        self._index_to_skill.clear()
        self._communities.clear()
        self._association_rules.clear()

        skill_demand: dict[str, int] = {}
        co_occurrence: dict[tuple[str, str], int] = {}

        app_list = list(applications)
        self._total_applications = len(app_list)

        for app_skills in app_list:
            unique_skills = set(app_skills)
            for skill in unique_skills:
                skill_demand[skill] = skill_demand.get(skill, 0) + 1

            for skill_a, skill_b in combinations(sorted(unique_skills), 2):
                key = (skill_a, skill_b)
                co_occurrence[key] = co_occurrence.get(key, 0) + 1

        for idx, skill in enumerate(sorted(skill_demand.keys())):
            self._skill_to_index[skill] = idx
            self._index_to_skill.append(skill)

        self._build_networkx_graph(skill_demand, co_occurrence)
        self._detect_communities()
        self._mine_associations(app_list, skill_demand)

        return self

    def _build_networkx_graph(
        self,
        skill_demand: dict[str, int],
        co_occurrence: dict[tuple[str, str], int],
    ) -> None:
        """Create NetworkX graph with demand as node weight, co-occurrence as edge weight.

        Args:
            skill_demand: Mapping of skill -> number of job postings.
            co_occurrence: Mapping of (skill_a, skill_b) -> co-occurrence count.
        """
        try:
            import networkx as nx
        except ImportError:
            self._graph = None
            return

        graph = nx.Graph()

        for skill, demand in skill_demand.items():
            graph.add_node(skill, demand=demand, index=self._skill_to_index[skill])

        for (skill_a, skill_b), count in co_occurrence.items():
            if count >= self.MIN_CO_OCCURRENCE:
                graph.add_edge(skill_a, skill_b, weight=count, co_occurrence=count)

        self._graph = graph

    def _detect_communities(self) -> None:
        """Detect skill communities using Louvain algorithm (python-louvain).

        Falls back to connected components if python-louvain is unavailable.
        Stores community_id per skill in self._communities.
        """
        if self._graph is None:
            for skill in self._index_to_skill:
                self._communities[skill] = hash(skill) % 1000
            return

        try:
            import community as community_louvain
        except ImportError:
            import networkx as nx

            for comp_id, component in enumerate(nx.connected_components(self._graph)):
                for skill in component:
                    self._communities[skill] = comp_id
            return

        partition = community_louvain.best_partition(self._graph)
        self._communities = partition

    def _mine_associations(
        self,
        applications: list[Iterable[str]],
        skill_demand: dict[str, int],
    ) -> None:
        """Mine association rules using simplified FP-Growth approach.

        Args:
            applications: List of skill sets per application.
            skill_demand: Demand count per skill.
        """
        if self._total_applications == 0:
            return

        app_skillsets = [frozenset(app) for app in applications]

        min_support_count = self.MIN_SUPPORT * self._total_applications
        frequent_1 = {
            skill for skill, count in skill_demand.items()
            if count >= min_support_count
        }

        if len(frequent_1) < 2:
            return

        frequent_2: dict[frozenset[str], int] = {}
        for app_set in app_skillsets:
            freq_in_app = app_set & frequent_1
            for pair in combinations(sorted(freq_in_app), 2):
                key = frozenset(pair)
                frequent_2[key] = frequent_2.get(key, 0) + 1

        frequent_2 = {
            pair: count for pair, count in frequent_2.items()
            if count >= min_support_count
        }

        if not frequent_2:
            return

        rules: list[AssociationRule] = []
        for pair, pair_count in frequent_2.items():
            skill_a, skill_b = tuple(pair)
            count_a = skill_demand[skill_a]
            count_b = skill_demand[skill_b]

            conf_ab = pair_count / count_a if count_a > 0 else 0.0
            lift_ab = conf_ab / (count_b / self._total_applications) if count_b > 0 else 0.0
            if conf_ab >= self.MIN_CONFIDENCE:
                rules.append(AssociationRule(
                    antecedent=frozenset([skill_a]),
                    consequent=frozenset([skill_b]),
                    support=pair_count / self._total_applications,
                    confidence=conf_ab,
                    lift=lift_ab,
                ))

            conf_ba = pair_count / count_b if count_b > 0 else 0.0
            lift_ba = conf_ba / (count_a / self._total_applications) if count_a > 0 else 0.0
            if conf_ba >= self.MIN_CONFIDENCE:
                rules.append(AssociationRule(
                    antecedent=frozenset([skill_b]),
                    consequent=frozenset([skill_a]),
                    support=pair_count / self._total_applications,
                    confidence=conf_ba,
                    lift=lift_ba,
                ))

        rules.sort(key=lambda r: (r.lift, r.confidence), reverse=True)
        self._association_rules = rules

    def get_skill_metrics(self, mastery_levels: dict[str, float]) -> list[SkillMetrics]:
        """Compute skill metrics including centrality and priority scores.

        Args:
            mastery_levels: Mapping of skill -> user mastery level (0.0-1.0).
                Missing skills default to 0.0.

        Returns:
            List of SkillMetrics sorted by priority_score descending.
        """
        if self._graph is None:
            return self._get_basic_metrics(mastery_levels)

        import networkx as nx

        graph = self._graph

        degree_centrality = nx.degree_centrality(graph)
        betweenness_centrality = nx.betweenness_centrality(graph, weight="weight")

        metrics = []
        for skill in self._index_to_skill:
            demand = graph.nodes[skill].get("demand", 0)
            degree = degree_centrality.get(skill, 0.0)
            betweenness = betweenness_centrality.get(skill, 0.0)
            community = self._communities.get(skill, -1)
            mastery = mastery_levels.get(skill, 0.0)
            priority = demand * (1.0 - mastery)

            metrics.append(SkillMetrics(
                name=skill,
                demand=demand,
                centrality_degree=degree,
                centrality_betweenness=betweenness,
                community_id=community,
                mastery_level=mastery,
                priority_score=priority,
            ))

        metrics.sort(key=lambda m: m.priority_score, reverse=True)
        return metrics

    def _get_basic_metrics(self, mastery_levels: dict[str, float]) -> list[SkillMetrics]:
        """Fallback metrics when NetworkX is unavailable."""
        metrics = []
        for skill in self._index_to_skill:
            demand = 0
            if self._graph is not None:
                try:
                    demand = self._graph.nodes[skill].get("demand", 0)
                except (AttributeError, KeyError):
                    pass

            mastery = mastery_levels.get(skill, 0.0)
            metrics.append(SkillMetrics(
                name=skill,
                demand=demand,
                centrality_degree=0.0,
                centrality_betweenness=0.0,
                community_id=self._communities.get(skill, -1),
                mastery_level=mastery,
                priority_score=demand * (1.0 - mastery),
            ))

        metrics.sort(key=lambda m: m.priority_score, reverse=True)
        return metrics

    def get_learning_priority_matrix(self, top_k: int = 20) -> list[dict]:
        """Generate learning priority matrix for UI display.

        Args:
            top_k: Number of top skills to return.

        Returns:
            List of dicts with keys: skill, demand, degree_centrality,
            betweenness_centrality, community, mastery, priority.
        """
        mastery_levels: dict[str, float] = {}
        metrics = self.get_skill_metrics(mastery_levels)

        matrix = []
        for metric in metrics[:top_k]:
            matrix.append({
                "skill": metric.name,
                "demand": metric.demand,
                "degree_centrality": round(metric.centrality_degree, 4),
                "betweenness_centrality": round(metric.centrality_betweenness, 4),
                "community": metric.community_id,
                "mastery": round(metric.mastery_level, 2),
                "priority": round(metric.priority_score, 2),
            })

        return matrix

    def get_association_rules(self, top_k: int | None = None) -> list[AssociationRule]:
        """Get mined association rules.

        Args:
            top_k: Optional limit on number of rules to return.

        Returns:
            List of AssociationRule sorted by lift descending.
        """
        rules = self._association_rules
        if top_k is not None:
            rules = rules[:top_k]
        return rules

    def get_community_skills(self, community_id: int) -> list[str]:
        """Get all skills belonging to a specific community.

        Args:
            community_id: Community identifier.

        Returns:
            List of skill names in that community.
        """
        return [
            skill for skill, cid in self._communities.items()
            if cid == community_id
        ]

    @property
    def skill_count(self) -> int:
        """Total number of unique skills in the graph."""
        return len(self._index_to_skill)

    @property
    def application_count(self) -> int:
        """Total number of applications processed."""
        return self._total_applications

    def has_graph(self) -> bool:
        """Check if NetworkX graph was successfully built."""
        return self._graph is not None