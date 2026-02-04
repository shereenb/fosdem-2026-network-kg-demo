# Network Knowledge Graph for Lungo

**FOSDEM 2026**: Beyond MCP Servers: Why Network Automation Agents Need Knowledge Graphs

Adds network infrastructure knowledge graph capabilities to lungo, demonstrating why graph-based queries outperform text-based approaches for network automation.

## The Problem

coffeeAGNTCY lungo handles business logic great, but has no infrastructure visibility. When the database times out, the Auction Supervisor can't diagnose why.

## The Solution

Model network topology as a knowledge graph. Query with Cypher. Expose via MCP.

## Quick Start

### 1. Setup Neo4j Aura (recommended)

1. Go to https://console.neo4j.io
2. Create a free AuraDB instance
3. Copy the connection URI and password
4. Create `.env`:
   ```
   NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=your-aura-password
   OPENAI_API_KEY=sk-...
   ```

### 2. Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Load Graph Data

```bash
python setup_network_graph.py
```

### 4. Run the Demo

```bash
./demo_launcher.sh
```

Choose:
- **A**: Terminal demo (Attempt 1 vs Attempt 3)
- **B**: Web UI at localhost:8001
- **C**: Check setup / verify Neo4j connection

## Demo Options

### Option A: Terminal Demo (`demo_option_a.py`)

Standalone terminal demo showing the presentation narrative:
- **Attempt 1**: Raw data via MCP (~2,400 tokens)
- **Attempt 2**: KAG/GraphRAG (covered in slides)
- **Attempt 3**: Graph-backed MCP (~1,100 tokens)

```bash
python demo_option_a.py
```

### Option B: Web UI (`network_kg_api.py`)

Standalone web UI at http://localhost:8001/diagnostics

```bash
python network_kg_api.py
```

Features:
- Diagnose service issues
- Analyze blast radius of link failures
- Trace upstream paths

### Option C: Full coffeeAGNTCY Integration (`option_c/`)

**True integration** into the coffeeAGNTCY lungo UI at localhost:3000.

This modifies lungo to:
- Add `network_kg_service.py` as an MCP server
- Add DIAGNOSTICS node to the Auction Supervisor LangGraph
- Show Network KG in the UI visualization

```bash
cd option_c
./install.sh
```

Then start lungo with:
```bash
cd /path/to/lungo
docker-compose -f docker-compose.yaml -f docker-compose.network-kg.yaml up -d
```
