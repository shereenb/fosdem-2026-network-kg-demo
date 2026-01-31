# Copyright AGNTCY Contributors (https://github.com/agntcy)
# SPDX-License-Identifier: Apache-2.0
#
# Modified ExchangeGraph with DIAGNOSTICS node for infrastructure visibility
# This extends the original graph.py with network knowledge graph integration.

import logging
import uuid
from pydantic import BaseModel, Field

from langchain_core.prompts import PromptTemplate
from langchain_core.messages import AIMessage, SystemMessage

from langgraph.graph.state import CompiledStateGraph
from langgraph.graph import MessagesState
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from ioa_observe.sdk import Observe
from ioa_observe.sdk.decorators import agent, tool, graph
from ioa_observe.sdk.tracing import session_start


from common.llm import get_llm
from graph.tools import (
    get_farm_yield_inventory,
    get_all_farms_yield_inventory,
    create_order,
    get_order_details,
    tools_or_next
)
# NEW: Import network diagnostic tools
from graph.network_tools import (
    diagnose_infrastructure,
    analyze_network_blast_radius,
    trace_network_path,
    get_network_health,
    NETWORK_TOOLS,
)

logger = logging.getLogger("lungo.supervisor.graph")


class NodeStates:
    SUPERVISOR = "exchange_supervisor"

    INVENTORY = "inventory_broker"
    INVENTORY_TOOLS = "inventory_tools"

    ORDERS = "orders_broker"
    ORDERS_TOOLS = "orders_tools"

    # NEW: Diagnostics node for infrastructure issues
    DIAGNOSTICS = "diagnostics_broker"
    DIAGNOSTICS_TOOLS = "diagnostics_tools"

    REFLECTION = "reflection"
    GENERAL_INFO = "general"


class GraphState(MessagesState):
    """
    Represents the state of our graph, passed between nodes.
    """
    next_node: str


@agent(name="exchange_agent")
class ExchangeGraph:
    def __init__(self):
        self.graph = self.build_graph()

    @graph(name="exchange_graph")
    def build_graph(self) -> CompiledStateGraph:
        """
        Constructs and compiles a LangGraph instance.

        Agent Flow:

        supervisor_agent
            - converse with user and coordinate app flow
            - NEW: routes to diagnostics for infrastructure issues

        inventory_agent
            - get inventory for a specific farm or broadcast to all farms

        orders_agent
            - initiate orders with a specific farm and retrieve order status

        diagnostics_agent (NEW)
            - diagnose infrastructure issues
            - analyze network blast radius
            - trace network paths

        reflection_agent
            - determine if the user's request has been satisfied or if further action is needed

        Returns:
        CompiledGraph: A fully compiled LangGraph instance ready for execution.
        """

        self.supervisor_llm = None
        self.reflection_llm = None
        self.inventory_llm = None
        self.orders_llm = None
        self.diagnostics_llm = None  # NEW

        workflow = StateGraph(GraphState)

        # --- 1. Define Node States ---

        workflow.add_node(NodeStates.SUPERVISOR, self._supervisor_node)
        workflow.add_node(NodeStates.INVENTORY, self._inventory_node)
        workflow.add_node(NodeStates.INVENTORY_TOOLS, ToolNode([get_farm_yield_inventory, get_all_farms_yield_inventory]))
        workflow.add_node(NodeStates.ORDERS, self._orders_node)
        workflow.add_node(NodeStates.ORDERS_TOOLS, ToolNode([create_order, get_order_details]))
        # NEW: Add diagnostics nodes
        workflow.add_node(NodeStates.DIAGNOSTICS, self._diagnostics_node)
        workflow.add_node(NodeStates.DIAGNOSTICS_TOOLS, ToolNode(NETWORK_TOOLS))
        workflow.add_node(NodeStates.REFLECTION, self._reflection_node)
        workflow.add_node(NodeStates.GENERAL_INFO, self._general_response_node)

        # --- 2. Define the Agentic Workflow ---

        workflow.set_entry_point(NodeStates.SUPERVISOR)

        # Add conditional edges from the supervisor (MODIFIED to include DIAGNOSTICS)
        workflow.add_conditional_edges(
            NodeStates.SUPERVISOR,
            lambda state: state["next_node"],
            {
                NodeStates.INVENTORY: NodeStates.INVENTORY,
                NodeStates.ORDERS: NodeStates.ORDERS,
                NodeStates.DIAGNOSTICS: NodeStates.DIAGNOSTICS,  # NEW
                NodeStates.GENERAL_INFO: NodeStates.GENERAL_INFO,
            },
        )

        workflow.add_conditional_edges(NodeStates.INVENTORY, tools_or_next(NodeStates.INVENTORY_TOOLS, NodeStates.REFLECTION))
        workflow.add_edge(NodeStates.INVENTORY_TOOLS, NodeStates.INVENTORY)

        workflow.add_conditional_edges(NodeStates.ORDERS, tools_or_next(NodeStates.ORDERS_TOOLS, NodeStates.REFLECTION))
        workflow.add_edge(NodeStates.ORDERS_TOOLS, NodeStates.ORDERS)

        # NEW: Add diagnostics edges
        workflow.add_conditional_edges(NodeStates.DIAGNOSTICS, tools_or_next(NodeStates.DIAGNOSTICS_TOOLS, NodeStates.REFLECTION))
        workflow.add_edge(NodeStates.DIAGNOSTICS_TOOLS, NodeStates.DIAGNOSTICS)

        workflow.add_edge(NodeStates.GENERAL_INFO, END)

        return workflow.compile()

    async def _supervisor_node(self, state: GraphState) -> dict:
        """
        Determines the intent of the user's message and routes to the appropriate node.
        MODIFIED: Now includes 'diagnostics' intent detection.
        """
        if not self.supervisor_llm:
            self.supervisor_llm = get_llm()

        user_message = state["messages"]

        # MODIFIED: Updated prompt to include diagnostics routing
        prompt = PromptTemplate(
            template="""You are a global coffee exchange agent connecting users to coffee farms in Brazil, Colombia, and Vietnam.
            You also have access to network diagnostics for troubleshooting infrastructure issues.

            Based on the user's message, determine the intent:

            Respond with 'inventory' if the message is about checking yield, stock, product availability, regions of origin, or specific coffee item details.

            Respond with 'orders' if the message is about checking order status, placing an order, or modifying an existing order.

            Respond with 'diagnostics' if the message is about:
            - Infrastructure issues, network problems, or connectivity
            - Service errors, timeouts, or failures
            - Checking system health or network status
            - Understanding why something isn't working
            - Maintenance planning or blast radius analysis
            - "Approach 1", "approach 3", "raw data", or comparing approaches
            - Anything mentioning "network", "links", "devices", or "topology"

            User message: {user_message}
            """,
            input_variables=["user_message"]
        )

        chain = prompt | self.supervisor_llm
        response = chain.invoke({"user_message": user_message})
        intent = response.content.strip().lower()

        logger.info(f"Supervisor decided: {intent}")

        if "inventory" in intent:
            return {"next_node": NodeStates.INVENTORY, "messages": user_message}
        elif "orders" in intent:
            return {"next_node": NodeStates.ORDERS, "messages": user_message}
        elif "diagnostics" in intent:  # NEW
            return {"next_node": NodeStates.DIAGNOSTICS, "messages": user_message}
        else:
            return {"next_node": NodeStates.GENERAL_INFO, "messages": user_message}

    async def _reflection_node(self, state: GraphState) -> dict:
        """
        Reflect on the conversation to determine if the user's query has been satisfied
        or if further action is needed.
        """
        if not self.reflection_llm:
            class ShouldContinue(BaseModel):
                should_continue: bool = Field(description="Whether to continue processing the request.")
                reason: str = Field(description="Reason for decision whether to continue the request.")

            # create a structured output LLM for reflection
            self.reflection_llm = get_llm().with_structured_output(ShouldContinue, strict=True)

        sys_msg_reflection = SystemMessage(
            content="""Decide whether the user query has been satisifed or if we need to continue.
                Do not continue if the last message is a question or requires user input.
                """,
                pretty_repr=True,
            )

        response = await self.reflection_llm.ainvoke(
          [sys_msg_reflection] + state["messages"]
        )
        logging.info(f"Reflection agent response: {response}")

        is_duplicate_message = (
          len(state["messages"]) > 2 and state["messages"][-1].content == state["messages"][-3].content
        )

        should_continue = response.should_continue and not is_duplicate_message
        next_node = NodeStates.SUPERVISOR if should_continue else END
        logging.info(f"Next node: {next_node}")

        return {
          "next_node": next_node,
          "messages": [SystemMessage(content=response.reason)],
        }

    async def _inventory_node(self, state: GraphState) -> dict:
        """
        Handles inventory-related queries using an LLM to formulate responses.
        """
        if not self.inventory_llm:
            self.inventory_llm = get_llm().bind_tools(
                [get_farm_yield_inventory, get_all_farms_yield_inventory],
                strict=True
            )

        # get latest HumanMessage
        user_msg = next(
            (m for m in reversed(state["messages"]) if m.type == "human"), None
        )
        # get latest ToolMessage
        tool_msg = next(
            (m for m in reversed(state["messages"]) if m.type == "tool"), None
        )

        if tool_msg:
            context = f"Tool responded: {tool_msg.content}"
        else:
            context = "Tool has not yet responded"

        prompt = PromptTemplate(
            template="""You are an inventory broker for a global coffee exchange company.
            Your task is to provide accurate and concise information about coffee yields and inventory based on user queries.

            If the user asks about how much coffee we have, what the yield is or general coffee inventory, use the provided tools.
            If no farm was specified, use the get_all_farms_yield_inventory tool to get the total yield across all farms.
            If the user asks about a specific farm, use the get_farm_yield_inventory tool to get the yield for that farm.

            If the user asks where we have coffee available, get the yield from all farms and respond with the total yield across all farms.

            User question: {user_message}

            {tool_context}
            If the tool has answered, summarize it to the user. Otherwise ask again.
            """,
            input_variables=["user_message", "tool_context"]
        )

        chain = prompt | self.inventory_llm

        llm_response = chain.invoke({
            "user_message": user_msg,
            "tool_context": context,
        })

        return {
            "messages": [llm_response]
        }

    async def _orders_node(self, state: GraphState) -> dict:
        if not self.orders_llm:
            self.orders_llm = get_llm().bind_tools([create_order, get_order_details])

        prompt = PromptTemplate(
            template="""You are an orders broker for a global coffee exchange company.
            Your task is to handle user requests related to placing and checking orders with coffee farms.

            If the issue is related to identity verification, respond with a short reply:
            'The badge of this <current_farm> farm agent has not been found or could not be verified, and hence the order request failed.'
            Do not ask further questions in this case.

            If the user asks about placing an order, use the provided tools to create an order.
            If the user asks about checking the status of an order, use the provided tools to retrieve order details.
            If an order has been created, do not create a new order for the same request.
            If further information is needed, ask the user for clarification.

            User question: {user_message}
            """,
            input_variables=["user_message"]
        )

        chain = prompt | self.orders_llm

        llm_response = chain.invoke({
            "user_message": state["messages"],
        })
        if llm_response.tool_calls:
            logger.info(f"Tool calls detected from orders_node: {llm_response.tool_calls}")
            logger.debug(f"Messages: {state['messages']}")
        return {
            "messages": [llm_response]
        }

    # NEW: Diagnostics node for infrastructure troubleshooting
    async def _diagnostics_node(self, state: GraphState) -> dict:
        """
        Handles infrastructure diagnostics queries using the network knowledge graph.
        """
        if not self.diagnostics_llm:
            self.diagnostics_llm = get_llm().bind_tools(NETWORK_TOOLS)

        # get latest HumanMessage
        user_msg = next(
            (m for m in reversed(state["messages"]) if m.type == "human"), None
        )
        # get latest ToolMessage
        tool_msg = next(
            (m for m in reversed(state["messages"]) if m.type == "tool"), None
        )

        if tool_msg:
            context = f"Network diagnostics tool responded: {tool_msg.content}"
        else:
            context = "Network diagnostics tool has not yet responded"

        prompt = PromptTemplate(
            template="""You are a network diagnostics assistant.

            {tool_context}

            User question: {user_message}

            INSTRUCTIONS:
            - If the tool has already responded above, DO NOT call any tools.

            - For APPROACH 1 responses (contains "[APPROACH 1"):
              Return the ENTIRE raw JSON data exactly as provided. Do not summarize it.
              Include the [MCP returned...] line at the end.

            - For APPROACH 3 responses (contains "[MCP returned"):
              Summarize in 1-2 sentences, then include the [MCP returned...] line exactly as provided.

            - If no tool has responded yet, call ONE of these tools:
              APPROACH 3 (default): get_network_health, diagnose_infrastructure, analyze_network_blast_radius, trace_network_path
              APPROACH 1 (if user asks for "approach 1" or "raw data"): get_network_health_raw
            """,
            input_variables=["user_message", "tool_context"]
        )

        chain = prompt | self.diagnostics_llm

        llm_response = chain.invoke({
            "user_message": user_msg,
            "tool_context": context,
        })

        if llm_response.tool_calls:
            logger.info(f"Tool calls detected from diagnostics_node: {llm_response.tool_calls}")

        # Log LLM token usage if available (but don't add to response)
        if hasattr(llm_response, 'usage_metadata') and llm_response.usage_metadata:
            usage = llm_response.usage_metadata
            llm_input = usage.get('input_tokens', 0)
            llm_output = usage.get('output_tokens', 0)
            logger.info(f"LLM token usage: {llm_input} in, {llm_output} out, {llm_input + llm_output} total")
        elif hasattr(llm_response, 'response_metadata') and llm_response.response_metadata:
            meta = llm_response.response_metadata
            if 'token_usage' in meta:
                usage = meta['token_usage']
                logger.info(f"LLM token usage: {usage}")

        return {
            "messages": [llm_response]
        }

    def _general_response_node(self, state: GraphState) -> dict:
        return {
            "next_node": END,
            "messages": [AIMessage(content="I'm not sure how to handle that. Could you please clarify?")],
        }

    async def serve(self, prompt: str):
        """
        Processes the input prompt and returns a response from the graph.
        Args:
            prompt (str): The input prompt to be processed by the graph.
        Returns:
            str: The response generated by the graph based on the input prompt.
        """
        try:
            logger.debug(f"Received prompt: {prompt}")
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError("Prompt must be a non-empty string.")
            result = await self.graph.ainvoke({
                "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
                ],
            }, {"configurable": {"thread_id": uuid.uuid4()}})

            messages = result.get("messages", [])
            if not messages:
                raise RuntimeError("No messages found in the graph response.")

            # Find the last AIMessage with non-empty content
            for message in reversed(messages):
                if isinstance(message, AIMessage) and message.content.strip():
                    logger.debug(f"Valid AIMessage found: {message.content.strip()}")
                    return message.content.strip()

            raise RuntimeError("No valid AIMessage found in the graph response.")
        except ValueError as ve:
            logger.error(f"ValueError in serve method: {ve}")
            raise ValueError(str(ve))
        except Exception as e:
            logger.error(f"Error in serve method: {e}")
            raise Exception(str(e))
