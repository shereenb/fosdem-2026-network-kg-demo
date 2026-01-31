# Copyright AGNTCY Contributors (https://github.com/agntcy)
# SPDX-License-Identifier: Apache-2.0
#
# Network Knowledge Graph MCP Server for Lungo
#
# KEY INSIGHT: Cypher queries return PRECISE ANSWERS, not data dumps.
# The knowledge graph does the reasoning, not the LLM.
#
# ATTEMPT 1 (BAD):  MCP returns all data → LLM parses → 50K tokens, hallucinations
# ATTEMPT 3 (GOOD): Cypher query returns exact answer → ~50 tokens, deterministic

import os
import asyncio
import logging

import tiktoken
from mcp.server.fastmcp import FastMCP
from neo4j import AsyncGraphDatabase

from agntcy_app_sdk.factory import AgntcyFactory
from config.config import (
    DEFAULT_MESSAGE_TRANSPORT,
    TRANSPORT_SERVER_ENDPOINT,
)

logger = logging.getLogger("lungo.mcp.network_kg")

# Initialize factory and transport
factory = AgntcyFactory("lungo_network_kg_server", enable_tracing=True)
transport = factory.create_transport(DEFAULT_MESSAGE_TRANSPORT, endpoint=TRANSPORT_SERVER_ENDPOINT)

# Neo4j connection
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

mcp = FastMCP()

# Token counter using tiktoken (cl100k_base encoding)
_tokenizer = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count actual tokens using tiktoken."""
    return len(_tokenizer.encode(text))


class NetworkGraphClient:
    """Async Neo4j client for network topology queries."""

    def __init__(self):
        self.driver = None

    async def connect(self):
        if not self.driver:
            self.driver = AsyncGraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
            )

    async def query(self, cypher: str, params: dict = None) -> list[dict]:
        await self.connect()
        async with self.driver.session() as session:
            result = await session.run(cypher, params or {})
            return [record.data() async for record in result]


graph_client = NetworkGraphClient()


# =============================================================================
# APPROACH 1 (BAD): Return ALL raw data - LLM must parse it
# =============================================================================

@mcp.tool()
async def get_network_health_raw() -> str:
    """
    APPROACH 1: Get ALL network data as raw JSON.
    This is the BAD approach - dumps everything for LLM to parse.
    """
    logger.info("APPROACH 1: Fetching ALL raw graph data (inefficient)")

    # Get ALL devices with ALL properties
    devices = await graph_client.query("""
        MATCH (d:Device)
        RETURN d.name as name, d.type as type, d.location as location,
               d.ip_address as ip, d.vendor as vendor, d.model as model,
               d.firmware as firmware, d.status as status
    """)

    # Get ALL links with ALL properties
    links = await graph_client.query("""
        MATCH (l:Link)
        RETURN l.id as id, l.status as status, l.utilization as utilization,
               l.bandwidth as bandwidth, l.latency as latency, l.type as type
    """)

    # Get ALL services with ALL properties
    services = await graph_client.query("""
        MATCH (s:Service)-[:RUNS_ON]->(d:Device)
        RETURN s.name as name, s.critical as critical, s.port as port,
               s.protocol as protocol, d.name as host
    """)

    # Get ALL relationships
    connections = await graph_client.query("""
        MATCH (a)-[r:CONNECTS_TO]->(b)
        RETURN a.name as from, type(r) as rel, b.name as to, b.id as to_id
    """)

    import json
    raw_data = {
        "devices": devices,
        "links": links,
        "services": services,
        "connections": connections,
        "instructions": "Please analyze this network data and determine: 1) Overall health status 2) Any degraded links 3) Critical services affected 4) Total device count"
    }

    raw_json = json.dumps(raw_data, indent=2)
    token_count = count_tokens(raw_json)

    logger.info(f"APPROACH 1: Returning {len(raw_json)} chars, {token_count} tokens of raw data")

    return f"""[APPROACH 1 - Raw Data Dump]

{raw_json}

[MCP returned {len(raw_json)} chars — LLM must parse all this raw data]"""


# =============================================================================
# APPROACH 3 (GOOD): Cypher returns PRECISE answers
# =============================================================================

@mcp.tool()
async def get_network_health() -> str:
    """
    Get network health status.
    Returns a precise answer, not a data dump.
    """
    logger.info("Cypher query: Getting network health")

    cypher = """
    MATCH (l:Link)
    WITH collect(l) as links
    WITH [l IN links WHERE l.status = 'degraded' | l.id + ' (' + toString(l.utilization) + '%)'] as degraded,
         size(links) as total_links
    MATCH (s:Service WHERE s.critical = true)
    WITH degraded, total_links, collect(s.name) as critical_services
    MATCH (d:Device)
    WITH degraded, total_links, critical_services, count(d) as device_count
    RETURN degraded, total_links, critical_services, device_count
    """

    results = await graph_client.query(cypher)
    r = results[0] if results else {}

    degraded = r.get('degraded', [])
    total_links = r.get('total_links', 0)
    critical = r.get('critical_services', [])
    devices = r.get('device_count', 0)

    # Return PRECISE answer - Cypher did the work, not LLM
    if degraded:
        answer = f"DEGRADED | {len(degraded)} of {total_links} links down: {', '.join(degraded)} | Critical services: {', '.join(critical)} | {devices} devices total"
    else:
        answer = f"HEALTHY | All {total_links} links operational | Critical services: {', '.join(critical)} | {devices} devices total"

    # Include proof in response for demo visibility
    proof = f"\n\n[MCP returned {len(answer)} chars — Cypher computed the precise answer]"
    logger.info(f"Precise answer ({len(answer)} chars, {count_tokens(answer)} tokens): {answer}")
    return answer + proof


@mcp.tool()
async def get_upstream_path(service_name: str) -> str:
    """
    Get the upstream network path from a service to core.
    Cypher traces the path - returns exact route, not data for LLM to parse.
    """
    logger.info(f"Cypher query: Tracing path for {service_name}")

    cypher = """
    MATCH (s:Service {name: $service_name})-[:RUNS_ON]->(host:Device)
    OPTIONAL MATCH path = (host)<-[:CONNECTS_TO*]-(upstream:Device)
    WITH s, host, upstream, length(path) as hops
    ORDER BY hops
    WITH s, host, collect(upstream.name) as path_names
    RETURN s.name as service, host.name as host, path_names
    """

    results = await graph_client.query(cypher, {"service_name": service_name})

    if not results or not results[0].get('service'):
        return f"Service '{service_name}' not found"

    r = results[0]
    host = r.get('host', 'unknown')
    path = [p for p in r.get('path_names', []) if p]

    # Return PRECISE path - Cypher traced it, not LLM
    if path:
        answer = f"{service_name} → {host} → {' → '.join(path)}"
    else:
        answer = f"{service_name} → {host} (no upstream path found)"

    # Include proof in response for demo visibility
    proof = f"\n\n[MCP returned {len(answer)} chars — Cypher computed the precise answer]"
    logger.info(f"Precise answer ({len(answer)} chars, {count_tokens(answer)} tokens): {answer}")
    return answer + proof


@mcp.tool()
async def analyze_blast_radius(link_id: str) -> str:
    """
    Analyze impact if a link fails.
    Cypher finds affected services - returns exact impact, not raw data.
    """
    logger.info(f"Cypher query: Blast radius for {link_id}")

    cypher = """
    MATCH (l:Link {id: $link_id})
    OPTIONAL MATCH (d:Device)-[:CONNECTS_TO]->(l)
    OPTIONAL MATCH (s:Service)-[:RUNS_ON]->(host:Device)-[:CONNECTS_TO*1..3]->(l)
    WITH l, collect(DISTINCT d.name) as devices,
         collect(DISTINCT CASE WHEN s.critical THEN s.name + ' [CRITICAL]' ELSE s.name END) as services
    RETURN l.id as link, l.status as status, l.utilization as util, devices, services
    """

    results = await graph_client.query(cypher, {"link_id": link_id})

    if not results or not results[0].get('link'):
        return f"Link '{link_id}' not found"

    r = results[0]
    status = r.get('status', 'unknown')
    util = r.get('util', 0)
    devices = [d for d in r.get('devices', []) if d]
    services = [s for s in r.get('services', []) if s]

    # Return PRECISE impact - Cypher calculated it
    critical_count = len([s for s in services if 'CRITICAL' in s])
    risk = "CRITICAL" if critical_count > 0 else "MODERATE" if services else "LOW"

    answer = f"{link_id} ({status}, {util}% util) | Risk: {risk} | Affects: {', '.join(devices) if devices else 'no devices'}"
    if services:
        answer += f" | Services impacted: {', '.join(services)}"

    # Include proof in response for demo visibility
    proof = f"\n\n[MCP returned {len(answer)} chars — Cypher computed the precise answer]"
    logger.info(f"Precise answer ({len(answer)} chars, {count_tokens(answer)} tokens): {answer}")
    return answer + proof


@mcp.tool()
async def diagnose_service(service_name: str, issue_type: str = "timeout") -> str:
    """
    Diagnose infrastructure issues for a service.
    Cypher checks the path for problems - returns diagnosis, not raw data.
    """
    logger.info(f"Cypher query: Diagnosing {issue_type} for {service_name}")

    cypher = """
    MATCH (s:Service {name: $service_name})-[:RUNS_ON]->(host:Device)
    OPTIONAL MATCH (host)<-[:CONNECTS_TO]-(link:Link)
    WITH s, host, collect({id: link.id, status: link.status, util: link.utilization}) as links
    WITH s, host, [l IN links WHERE l.status = 'degraded' OR l.util > 80 | l.id + ' (' + l.status + ', ' + toString(l.util) + '%)'] as problems
    RETURN s.name as service, s.critical as critical, host.name as host, host.location as location, problems
    """

    results = await graph_client.query(cypher, {"service_name": service_name})

    if not results or not results[0].get('service'):
        return f"Service '{service_name}' not found"

    r = results[0]
    host = r.get('host', 'unknown')
    location = r.get('location', 'unknown')
    critical = r.get('critical', False)
    problems = r.get('problems', [])

    # Return PRECISE diagnosis - Cypher found the issues
    crit_tag = " [CRITICAL]" if critical else ""
    if problems:
        answer = f"{service_name}{crit_tag} on {host} ({location}) | ISSUES FOUND: {', '.join(problems)} | Recommendation: Check network links"
    else:
        answer = f"{service_name}{crit_tag} on {host} ({location}) | No infrastructure issues | Recommendation: Check application logs"

    # Include proof in response for demo visibility
    proof = f"\n\n[MCP returned {len(answer)} chars — Cypher computed the precise answer]"
    logger.info(f"Precise answer ({len(answer)} chars, {count_tokens(answer)} tokens): {answer}")
    return answer + proof


async def main():
    """Start the MCP server via SLIM bridge."""
    logger.info("Starting Network KG MCP Server")
    logger.info("Mode: PRECISE ANSWERS from Cypher (not data dumps for LLM)")

    try:
        await graph_client.connect()
        logger.info("Connected to Neo4j")
    except Exception as e:
        logger.warning(f"Could not connect to Neo4j: {e}")

    bridge = factory.create_bridge(mcp, transport=transport, topic="lungo_network_kg_service")
    await bridge.start(blocking=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
