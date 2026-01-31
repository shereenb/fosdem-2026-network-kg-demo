# Copyright AGNTCY Contributors (https://github.com/agntcy)
# SPDX-License-Identifier: Apache-2.0
#
# Network Diagnostic Tools - MCP Client
# Calls the Network KG MCP Server which returns PRECISE ANSWERS from Cypher.

import logging
from pydantic import BaseModel, Field
from langchain_core.tools import tool

from agntcy_app_sdk.factory import AgntcyFactory
from config.config import (
    DEFAULT_MESSAGE_TRANSPORT,
    TRANSPORT_SERVER_ENDPOINT,
)

logger = logging.getLogger("lungo.supervisor.network_tools")

factory = AgntcyFactory("lungo_exchange_network_client", enable_tracing=True)


async def call_mcp_tool(tool_name: str, arguments: dict) -> str:
    """Call MCP tool and return the precise answer from Cypher."""
    logger.info(f"MCP call: {tool_name}({arguments})")

    transport = factory.create_transport(DEFAULT_MESSAGE_TRANSPORT, endpoint=TRANSPORT_SERVER_ENDPOINT)
    client = factory.create_client("MCP", agent_topic="lungo_network_kg_service", transport=transport)

    try:
        async with client as c:
            result = await c.call_tool(name=tool_name, arguments=arguments)
            answer = result.content[0].text if result.content else "No response"
            logger.info(f"MCP response (~{len(answer)//4} tokens): {answer}")
            return answer
    except Exception as e:
        logger.error(f"MCP error: {e}")
        return f"Error: {str(e)}"


class ServiceArgs(BaseModel):
    service_name: str = Field(description="Service name (e.g., 'postgresql_orders')")
    issue_type: str = Field(description="Issue type: timeout, connectivity, performance")


class LinkArgs(BaseModel):
    link_id: str = Field(description="Link ID (e.g., 'link-core-agg3')")


class PathArgs(BaseModel):
    service_name: str = Field(description="Service name to trace")


@tool(args_schema=ServiceArgs)
async def diagnose_infrastructure(service_name: str, issue_type: str) -> str:
    """
    Diagnose infrastructure issues for a service.
    Returns precise answer from knowledge graph - not data for LLM to parse.
    """
    return await call_mcp_tool("diagnose_service", {"service_name": service_name, "issue_type": issue_type})


@tool(args_schema=LinkArgs)
async def analyze_network_blast_radius(link_id: str) -> str:
    """
    Analyze blast radius if a link fails.
    Cypher calculates exact impact - returns precise answer.
    """
    return await call_mcp_tool("analyze_blast_radius", {"link_id": link_id})


@tool(args_schema=PathArgs)
async def trace_network_path(service_name: str) -> str:
    """
    Trace network path from service to core.
    Cypher traverses the graph - returns exact path.
    """
    return await call_mcp_tool("get_upstream_path", {"service_name": service_name})


@tool
async def get_network_health() -> str:
    """
    APPROACH 3 (GOOD): Get network health status.
    Cypher aggregates data - returns precise status, not raw data.
    Use this for efficient queries.
    """
    return await call_mcp_tool("get_network_health", {})


@tool
async def get_network_health_raw() -> str:
    """
    APPROACH 1 (BAD): Get ALL raw network data.
    Returns everything for LLM to parse - inefficient, expensive, error-prone.
    Use this to demonstrate the bad approach.
    """
    return await call_mcp_tool("get_network_health_raw", {})


NETWORK_TOOLS = [
    diagnose_infrastructure,
    analyze_network_blast_radius,
    trace_network_path,
    get_network_health,
    get_network_health_raw,
]
