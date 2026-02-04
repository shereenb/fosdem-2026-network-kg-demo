# FOSDEM 2026: Network Knowledge Graph Demo

**Beyond MCP Servers: Why Network Automation Agents Need Knowledge Graphs**

This demo shows two approaches to querying network infrastructure via MCP:

| | Approach 1 (The Problem) | Approach 3 (Solution) |
|--|-----------------|-------------------|
| **MCP returns** | 8,714 chars raw JSON | 172 chars precise answer |
| **Who reasons?** | LLM parses all data | Cypher computes the answer |
| **Result** | Expensive, slow | Efficient, deterministic |

## Files

```
├── mcp_servers/
│   └── network_kg_service.py      # MCP server with Neo4j/Cypher queries
├── exchange/graph/
│   ├── network_tools.py           # MCP client tools (LangChain)
│   └── graph_with_diagnostics.py  # LangGraph diagnostics node
├── scripts/
│   └── seed_neo4j.py              # Seeds Neo4j with network topology
├── docker/
│   └── Dockerfile.network-kg      # Dockerfile for MCP server
└── docker-compose.network-kg.yaml # Neo4j + MCP server
```

## Architecture

```
User Question
     ↓
LangGraph (graph_with_diagnostics.py)
     ↓
MCP Client (network_tools.py)
     ↓
MCP Server (network_kg_service.py)
     ↓
Neo4j + Cypher
     ↓
Precise Answer (172 chars) or Raw Dump (8,714 chars)
```

## Demo Queries

**Approach 3** (Cypher computes the answer):
- "Check the network health"
- "What's the network path for postgresql_orders?"
- "What's the blast radius if link-core-agg3 fails?"

**Approach 1** (Raw data dump for comparison):
- "Use approach 1 to check network health"

## Sample Output

**Approach 3:**
```
DEGRADED | 2 of 12 links down: link-core-agg3 (87%), link-agg3-dist3 (91%)
Critical services: lungo_auction_supervisor, postgresql_orders, slim_gateway

[MCP returned 172 chars — Cypher computed the precise answer]
```

**Approach 1:**
```json
{
  "devices": [...13 devices...],
  "links": [...12 links...],
  "services": [...7 services...],
  "connections": [...24 relationships...]
}

[MCP returned 8714 chars — LLM must parse all this raw data]
```

## Integration

These files integrate into [coffeeAGNTCY lungo](https://github.com/agntcy/agentic-apps). To run:

```bash
# From the lungo directory
docker-compose -f docker-compose.yaml -f docker-compose.network-kg.yaml up -d

# Seed Neo4j
python scripts/seed_neo4j.py

# Open UI at http://localhost:3000
```

## Key Insight

The knowledge graph does the reasoning, not the LLM:

```cypher
// Approach 3: Cypher returns the answer
MATCH (s:Service)-[:RUNS_ON]->(host)<-[:CONNECTS_TO*]-(upstream)
RETURN upstream.name
→ "postgresql_orders → db-server-1 → dist-switch-2 → core-router-1"
```

vs dumping all nodes/relationships and asking the LLM to figure it out.
