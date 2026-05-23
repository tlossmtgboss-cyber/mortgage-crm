"""
Knowledge Graph Tools for Aria AI agents.

Allows agents to query entity relationships, find connections between
leads/loans/users/partners, and retrieve structured context for prompts.
"""

import logging
from typing import Optional

from agents.tools.base import (
    mortgage_tool,
    ToolResult,
    get_db,
    get_tenant_context,
)

logger = logging.getLogger(__name__)


@mortgage_tool(
    name="graph_get_entity_context",
    description="Get all relationships and context for a CRM entity (lead, loan, user, referral_partner). Returns the entity's properties and grouped relationships — perfect for understanding who's connected to what.",
    agent_roles=["pipeline_analyst", "lead_nurturer", "sales", "manager", "compliance_checker", "team_coach", "receptionist"],
    risk_level="low",
    examples=[
        "What do we know about this lead's connections?",
        "Who's involved with this loan?",
        "Show me the network around this referral partner",
    ],
)
def graph_get_entity_context(
    entity_type: str,
    entity_id: str,
) -> ToolResult:
    """Get full relationship context for an entity."""
    org_id = get_tenant_context()
    if not org_id:
        return ToolResult.error("No tenant context")

    valid_types = {"lead", "loan", "user", "referral_partner", "borrower", "mum_client", "contact", "branch"}
    if entity_type not in valid_types:
        return ToolResult.error(f"Invalid entity type. Must be one of: {', '.join(sorted(valid_types))}")

    with get_db() as db:
        from services.knowledge_graph import KnowledgeGraphService
        svc = KnowledgeGraphService(db, org_id)
        ctx = svc.get_entity_context(entity_type, entity_id)
        if not ctx:
            return ToolResult.no_data(f"No graph data for {entity_type} #{entity_id}")
        return ToolResult.success(ctx)


@mortgage_tool(
    name="graph_find_connections",
    description="Find the path between two entities in the knowledge graph. Useful for discovering how a lead is connected to a referral partner, or how two loans share team members.",
    agent_roles=["pipeline_analyst", "lead_nurturer", "sales", "manager", "team_coach"],
    risk_level="low",
    examples=[
        "How is this lead connected to that referral partner?",
        "Find the relationship between these two entities",
        "What's the connection path?",
    ],
)
def graph_find_connections(
    start_entity_type: str,
    start_entity_id: str,
    end_entity_type: str,
    end_entity_id: str,
    max_depth: int = 4,
) -> ToolResult:
    """Find connection paths between two entities."""
    org_id = get_tenant_context()
    if not org_id:
        return ToolResult.error("No tenant context")

    with get_db() as db:
        from services.knowledge_graph import KnowledgeGraphService
        svc = KnowledgeGraphService(db, org_id)

        start_node = svc.get_node(start_entity_type, start_entity_id)
        end_node = svc.get_node(end_entity_type, end_entity_id)

        if not start_node:
            return ToolResult.no_data(f"Start entity not found: {start_entity_type} #{start_entity_id}")
        if not end_node:
            return ToolResult.no_data(f"End entity not found: {end_entity_type} #{end_entity_id}")

        paths = svc.find_paths(start_node.id, end_node.id, max_depth=min(max_depth, 5))
        if not paths:
            return ToolResult.no_data("No connection found between these entities")

        return ToolResult.success({
            "start": {"type": start_entity_type, "id": start_entity_id, "label": start_node.label},
            "end": {"type": end_entity_type, "id": end_entity_id, "label": end_node.label},
            "paths": paths,
            "path_count": len(paths),
        })


@mortgage_tool(
    name="graph_get_neighbors",
    description="Get immediate neighbors of an entity in the knowledge graph — who owns this lead, what loans does this LO have, which partners referred these leads.",
    agent_roles=["pipeline_analyst", "lead_nurturer", "sales", "manager", "team_coach", "receptionist"],
    risk_level="low",
    examples=[
        "What leads does this LO own?",
        "Who referred this lead?",
        "What loans is this partner involved with?",
    ],
)
def graph_get_neighbors(
    entity_type: str,
    entity_id: str,
    relationship_type: Optional[str] = None,
    direction: str = "both",
    limit: int = 25,
) -> ToolResult:
    """Get neighbors of an entity, optionally filtered by relationship type."""
    org_id = get_tenant_context()
    if not org_id:
        return ToolResult.error("No tenant context")

    if direction not in ("in", "out", "both"):
        return ToolResult.error("direction must be 'in', 'out', or 'both'")

    with get_db() as db:
        from services.knowledge_graph import KnowledgeGraphService
        svc = KnowledgeGraphService(db, org_id)

        node = svc.get_node(entity_type, entity_id)
        if not node:
            return ToolResult.no_data(f"Entity not found: {entity_type} #{entity_id}")

        rel_types = [relationship_type] if relationship_type else None
        neighbors = svc.get_neighbors(node.id, relationship_types=rel_types, direction=direction, limit=limit)

        return ToolResult.success({
            "entity": {"type": entity_type, "id": entity_id, "label": node.label},
            "neighbors": neighbors,
            "count": len(neighbors),
        })


@mortgage_tool(
    name="graph_search",
    description="Search the knowledge graph by name/label. Find leads, loans, users, or partners matching a text query.",
    agent_roles=["pipeline_analyst", "lead_nurturer", "sales", "manager", "team_coach", "receptionist", "scheduler"],
    risk_level="low",
    examples=[
        "Find everyone named Smith in the graph",
        "Search for loans related to Main Street",
        "Who do we have named Johnson?",
    ],
)
def graph_search(
    query: str,
    node_type: Optional[str] = None,
    limit: int = 20,
) -> ToolResult:
    """Search nodes by label text."""
    org_id = get_tenant_context()
    if not org_id:
        return ToolResult.error("No tenant context")

    if not query or len(query.strip()) < 2:
        return ToolResult.error("Search query must be at least 2 characters")

    with get_db() as db:
        from services.knowledge_graph import KnowledgeGraphService
        svc = KnowledgeGraphService(db, org_id)
        nodes = svc.search_nodes(query.strip(), node_type=node_type, limit=limit)

        if not nodes:
            return ToolResult.no_data(f"No results for '{query}'")

        results = []
        for n in nodes:
            results.append({
                "id": n.id,
                "type": n.node_type,
                "entity_id": n.entity_id,
                "label": n.label,
                "properties": n.properties or {},
            })

        return ToolResult.success({
            "query": query,
            "results": results,
            "count": len(results),
        })


@mortgage_tool(
    name="graph_get_stats",
    description="Get knowledge graph statistics — total nodes, edges, and breakdowns by type. Useful for understanding the data landscape.",
    agent_roles=["pipeline_analyst", "manager", "team_coach"],
    risk_level="low",
    examples=[
        "How big is the knowledge graph?",
        "How many entities are connected?",
        "What's in the relationship graph?",
    ],
)
def graph_get_stats() -> ToolResult:
    """Get graph statistics for the current organization."""
    org_id = get_tenant_context()
    if not org_id:
        return ToolResult.error("No tenant context")

    with get_db() as db:
        from services.knowledge_graph import KnowledgeGraphService
        svc = KnowledgeGraphService(db, org_id)
        stats = svc.get_stats()
        return ToolResult.success(stats)


@mortgage_tool(
    name="graph_get_referral_network",
    description="Get the referral network for a user — all referral partners, their leads, and closed loans. Shows the strength of each relationship.",
    agent_roles=["pipeline_analyst", "lead_nurturer", "sales", "manager", "team_coach"],
    risk_level="low",
    examples=[
        "Show me this LO's referral network",
        "Who are my strongest referral partners?",
        "Map out the referral relationships",
    ],
)
def graph_get_referral_network(
    user_id: str,
) -> ToolResult:
    """Get the referral network for a loan officer."""
    org_id = get_tenant_context()
    if not org_id:
        return ToolResult.error("No tenant context")

    with get_db() as db:
        from services.knowledge_graph import KnowledgeGraphService
        svc = KnowledgeGraphService(db, org_id)

        user_node = svc.get_node("user", user_id)
        if not user_node:
            return ToolResult.no_data(f"User #{user_id} not found in graph")

        partners = svc.get_neighbors(user_node.id, relationship_types=["works_with"], direction="out")
        leads = svc.get_neighbors(user_node.id, relationship_types=["owns_lead"], direction="out")
        loans = svc.get_neighbors(user_node.id, relationship_types=["officers_loan"], direction="out")

        referred_leads = []
        for p in partners:
            partner_node_id = p["node"]["id"]
            referred = svc.get_neighbors(partner_node_id, relationship_types=["referred"], direction="out")
            referred_leads.extend(referred)

        return ToolResult.success({
            "user": {"id": user_id, "label": user_node.label},
            "referral_partners": [{
                "label": p["node"]["label"],
                "entity_id": p["node"]["entity_id"],
                "weight": p["weight"],
                "properties": p["node"].get("properties", {}),
            } for p in partners],
            "total_leads": len(leads),
            "total_loans": len(loans),
            "referred_leads": len(referred_leads),
            "partner_count": len(partners),
        })
