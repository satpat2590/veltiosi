"""Backlink analysis and graph building."""

import logging
from collections import defaultdict
from typing import Dict, List, Set, Tuple

import networkx as nx

from ..models import NoteRecord
from ..utils.markdown import extract_wikilinks

logger = logging.getLogger(__name__)


class BacklinkAnalyzer:
    """Analyzer for backlinks and graph relationships."""

    def __init__(self):
        """Initialize backlink analyzer."""
        self.graph = nx.DiGraph()
        self.backlink_map: Dict[str, Set[str]] = defaultdict(set)  # note_title -> set of backlinks
        self.forward_link_map: Dict[str, Set[str]] = defaultdict(
            set
        )  # note_title -> set of forward links

        logger.info("Backlink analyzer initialized")

    def build_graph(self, notes: List[NoteRecord]) -> None:
        """Build graph from notes."""
        logger.info(f"Building graph from {len(notes)} notes")

        # Clear existing graph
        self.graph.clear()
        self.backlink_map.clear()
        self.forward_link_map.clear()

        # Add nodes
        for note in notes:
            self.graph.add_node(note.title, **note.model_dump())

        # Add edges (forward links)
        for note in notes:
            forward_links = set(note.wikilinks_out)
            self.forward_link_map[note.title] = forward_links

            for link in forward_links:
                if link in self.graph:
                    self.graph.add_edge(note.title, link)

                    # Add to backlink map
                    self.backlink_map[link].add(note.title)

        logger.info(
            f"Graph built: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges"
        )

    def calculate_backlinks(self, notes: List[NoteRecord]) -> List[NoteRecord]:
        """Calculate backlinks for each note and update records."""
        # Build graph if not already built
        if not self.graph.nodes():
            self.build_graph(notes)

        # Update notes with backlinks
        updated_notes = []
        for note in notes:
            backlinks = list(self.backlink_map.get(note.title, set()))
            note.wikilinks_in = backlinks
            updated_notes.append(note)

        logger.info(f"Calculated backlinks for {len(updated_notes)} notes")
        return updated_notes

    def get_backlink_statistics(self) -> Dict[str, any]:
        """Get statistics about backlinks."""
        if not self.graph.nodes():
            return {}

        # Calculate various metrics
        in_degrees = dict(self.graph.in_degree())
        out_degrees = dict(self.graph.out_degree())

        # Find notes with most backlinks
        top_backlinked = sorted(in_degrees.items(), key=lambda x: x[1], reverse=True)[:10]

        # Find notes with most forward links
        top_linking = sorted(out_degrees.items(), key=lambda x: x[1], reverse=True)[:10]

        # Find orphan notes (no backlinks)
        orphans = [node for node, degree in in_degrees.items() if degree == 0]

        # Find sink notes (no forward links)
        sinks = [node for node, degree in out_degrees.items() if degree == 0]

        # Calculate connectivity
        try:
            avg_clustering = nx.average_clustering(self.graph.to_undirected())
        except:
            avg_clustering = 0.0

        # Check if graph is weakly connected
        is_connected = nx.is_weakly_connected(self.graph)

        # Find weakly connected components
        components = list(nx.weakly_connected_components(self.graph))

        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "avg_in_degree": sum(in_degrees.values()) / len(in_degrees) if in_degrees else 0,
            "avg_out_degree": sum(out_degrees.values()) / len(out_degrees) if out_degrees else 0,
            "top_backlinked_notes": top_backlinked,
            "top_linking_notes": top_linking,
            "orphan_notes": orphans,
            "sink_notes": sinks,
            "avg_clustering_coefficient": avg_clustering,
            "is_weakly_connected": is_connected,
            "weakly_connected_components": len(components),
            "largest_component_size": max(len(c) for c in components) if components else 0,
        }

    def find_orphans(self) -> List[str]:
        """Find orphan notes (no backlinks)."""
        if not self.graph.nodes():
            return []

        in_degrees = dict(self.graph.in_degree())
        return [node for node, degree in in_degrees.items() if degree == 0]

    def find_sinks(self) -> List[str]:
        """Find sink notes (no forward links)."""
        if not self.graph.nodes():
            return []

        out_degrees = dict(self.graph.out_degree())
        return [node for node, degree in out_degrees.items() if degree == 0]

    def find_weak_links(self, threshold: int = 1) -> List[Tuple[str, str]]:
        """Find weak links (edges that are the only connection between components)."""
        if not self.graph.edges():
            return []

        # Convert to undirected graph for bridge detection
        undirected_graph = self.graph.to_undirected()

        # Find bridges (edges whose removal increases number of connected components)
        bridges = list(nx.bridges(undirected_graph))

        # Filter by threshold (in-degree + out-degree)
        weak_links = []
        for u, v in bridges:
            # Get total connections for both nodes
            u_degree = self.graph.degree(u)
            v_degree = self.graph.degree(v)

            if u_degree <= threshold or v_degree <= threshold:
                weak_links.append((u, v))

        return weak_links

    def find_central_notes(self, top_n: int = 10) -> List[Tuple[str, float]]:
        """Find central notes using PageRank."""
        if not self.graph.nodes():
            return []

        try:
            pagerank = nx.pagerank(self.graph)
            sorted_pagerank = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)[:top_n]

            return sorted_pagerank
        except Exception as e:
            logger.error(f"Failed to calculate PageRank: {e}")
            return []

    def find_communities(self) -> Dict[str, List[str]]:
        """Find communities in the graph using Louvain method."""
        if not self.graph.nodes():
            return {}

        try:
            # Convert to undirected graph for community detection
            undirected_graph = self.graph.to_undirected()

            # Use greedy modularity communities (simpler than Louvain)
            communities = nx.community.greedy_modularity_communities(undirected_graph)

            # Map communities
            community_map = {}
            for i, community in enumerate(communities):
                community_name = f"community_{i + 1}"
                community_map[community_name] = list(community)

            return community_map
        except Exception as e:
            logger.error(f"Failed to find communities: {e}")
            return {}

    def get_note_neighborhood(self, note_title: str, radius: int = 2) -> Dict[str, any]:
        """Get neighborhood of a note."""
        if note_title not in self.graph:
            return {"error": f"Note '{note_title}' not found in graph"}

        # Get ego graph (subgraph centered on note)
        ego_graph = nx.ego_graph(self.graph, note_title, radius=radius, undirected=True)

        # Get statistics for neighborhood
        nodes = list(ego_graph.nodes())
        edges = list(ego_graph.edges())

        # Get backlinks and forward links for the note
        backlinks = list(self.backlink_map.get(note_title, set()))
        forward_links = list(self.forward_link_map.get(note_title, set()))

        # Calculate local clustering coefficient
        try:
            clustering_coeff = nx.clustering(self.graph.to_undirected(), note_title)
        except:
            clustering_coeff = 0.0

        return {
            "note": note_title,
            "neighborhood_radius": radius,
            "nodes_in_neighborhood": len(nodes),
            "edges_in_neighborhood": len(edges),
            "backlinks": backlinks,
            "forward_links": forward_links,
            "clustering_coefficient": clustering_coeff,
            "neighborhood_nodes": nodes,
            "neighborhood_edges": edges,
        }

    def find_shortest_path(
        self, source_note: str, target_note: str, max_path_length: int = 10
    ) -> List[str]:
        """Find shortest path between two notes."""
        if source_note not in self.graph or target_note not in self.graph:
            return []

        try:
            path = nx.shortest_path(self.graph, source=source_note, target=target_note)

            if len(path) > max_path_length:
                logger.warning(f"Path length {len(path)} exceeds max {max_path_length}")
                return []

            return path
        except nx.NetworkXNoPath:
            return []
        except Exception as e:
            logger.error(f"Failed to find shortest path: {e}")
            return []

    def analyze_connectivity_patterns(self) -> Dict[str, any]:
        """Analyze connectivity patterns in the graph."""
        if not self.graph.nodes():
            return {}

        stats = self.get_backlink_statistics()

        # Additional analysis
        degree_centrality = nx.degree_centrality(self.graph)
        betweenness_centrality = nx.betweenness_centrality(self.graph)

        # Find hubs (high degree centrality)
        hubs = sorted(degree_centrality.items(), key=lambda x: x[1], reverse=True)[:10]

        # Find brokers (high betweenness centrality)
        brokers = sorted(betweenness_centrality.items(), key=lambda x: x[1], reverse=True)[:10]

        # Analyze reciprocity (bidirectional links)
        reciprocal_edges = 0
        total_edges = self.graph.number_of_edges()

        for u, v in self.graph.edges():
            if self.graph.has_edge(v, u):
                reciprocal_edges += 1

        reciprocity = reciprocal_edges / total_edges if total_edges > 0 else 0

        return {
            **stats,
            "hubs": hubs,
            "brokers": brokers,
            "reciprocity": reciprocity,
            "reciprocal_edges": reciprocal_edges,
        }

    def export_graph(self, format: str = "gexf") -> str:
        """Export graph to various formats."""
        if not self.graph.nodes():
            return ""

        try:
            if format == "gexf":
                import io

                buffer = io.BytesIO()
                nx.write_gexf(self.graph, buffer)
                return buffer.getvalue().decode("utf-8")
            elif format == "graphml":
                import io

                buffer = io.BytesIO()
                nx.write_graphml(self.graph, buffer)
                return buffer.getvalue().decode("utf-8")
            elif format == "json":
                import json

                return json.dumps(nx.node_link_data(self.graph), indent=2)
            else:
                logger.error(f"Unsupported export format: {format}")
                return ""
        except Exception as e:
            logger.error(f"Failed to export graph: {e}")
            return ""
