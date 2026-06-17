"""
PRisk LangGraph Workflow
------------------------------
This file defines HOW agents connect to each other.
LangGraph reads this graph and figures out execution order automatically.

EXECUTION ORDER:
  1. context_builder_node       → builds initial state (runs before graph)
  2. [PARALLEL] change_node     → Agent 1
  3. [PARALLEL] blast_node      → Agent 2
  4. [PARALLEL] engineering_node → Agent 3
  5. [SEQUENTIAL] testing_node  → Agent 4 (needs 1, 2, 3 done)
  6. [SEQUENTIAL] confidence_node → Agent 5 (needs 4 done)

HOW LANGGRAPH PARALLELISM WORKS:
  When multiple nodes have the same dependencies, LangGraph runs them
  in parallel automatically. Here agents 1, 2, 3 all depend only on
  the initial state → they run simultaneously.

  Agent 4 depends on agents 1, 2, 3 → waits for all three to finish.
  Agent 5 depends on agent 4 → runs last.
"""

from langgraph.graph import StateGraph, END

from core.state import PRiskState
from agents.agent1_change_understanding import change_understanding_agent
from agents.agent2_blast_radius import blast_radius_agent
from agents.agent3_engineering_review import engineering_review_agent
from agents.agent4_testing_strategy import testing_strategy_agent
from agents.agent5_merge_confidence import merge_confidence_agent


def _start_parallel_agents(_: PRiskState) -> list[str]:
    return ["change_node", "blast_node", "engineering_node"]


def build_prisk_graph() -> StateGraph:
    """
    Constructs and compiles the LangGraph workflow.

    Returns a compiled graph that can be invoked with:
        result = graph.invoke(initial_state)
    """

    # Step 1: Create the graph, telling it what the state shape looks like
    graph = StateGraph(PRiskState)

    # Step 2: Register each agent as a named node
    # The first argument is the node name (string)
    # The second argument is the Python function to call
    graph.add_node("change_node", change_understanding_agent)
    graph.add_node("blast_node", blast_radius_agent)
    graph.add_node("engineering_node", engineering_review_agent)
    graph.add_node("testing_node", testing_strategy_agent)
    graph.add_node("confidence_node", merge_confidence_agent)
 
    # Step 3: Fan out to the first three agents in parallel, then join at testing.
    graph.set_conditional_entry_point(_start_parallel_agents, then="testing_node")

    # Step 4: Wire up the remaining edges.
    graph.add_edge("testing_node", "confidence_node")
    graph.add_edge("confidence_node", END)

    # Step 5: Compile (validates the graph structure)
    return graph.compile()


# Build the graph once at module load time (singleton pattern)
# FastAPI will reuse this compiled graph for every request
prisk_graph = build_prisk_graph()


def run_analysis(initial_state: PRiskState) -> PRiskState:
    """
    Convenience function called by the FastAPI route.

    Takes the initial state from context_builder,
    runs the full LangGraph pipeline,
    returns the final state with all agents' outputs populated.
    """
    final_state = prisk_graph.invoke(initial_state)
    return final_state
