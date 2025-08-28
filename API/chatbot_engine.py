from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import InMemorySaver

from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama
from langchain_tavily import TavilySearch

import copy, os
from dotenv import load_dotenv

# ------------------ Setup ------------------

load_dotenv()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

class State(TypedDict):
    messages: Annotated[list, add_messages]

graph_builder = StateGraph(State)

system_prompt = """You are a helpful AI assistant.
- Use Tavily Search ONLY when the user asks about recent, factual, or web-based information.
"""

# LLM (Ollama local)
llm = ChatOllama(model="llama3.1:8b", temperature=0, system=system_prompt)

# Tools
tavily_tool = TavilySearch(
    tavily_api_key=TAVILY_API_KEY,
    max_results=3
)

tools = [tavily_tool]
llm_with_tools = llm.bind_tools(tools)

# ------------------ Nodes ------------------

def chatbot_node(state: State):
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}

graph_builder.add_node("chatbot", chatbot_node)

tool_node = ToolNode(tools=tools)
graph_builder.add_node("tools", tool_node)

graph_builder.add_edge(START, "chatbot")
graph_builder.add_conditional_edges("chatbot", tools_condition)
graph_builder.add_edge("tools", "chatbot")
graph_builder.add_edge("chatbot", END)

# ------------------ Memory & Graph ------------------

memory = InMemorySaver()
graph = graph_builder.compile(checkpointer=memory)

# ------------------ Public Functions ------------------

def run_message(thread_id: str, user_input: str) -> str:
    """
    Run one user message inside a thread (create or continue).
    Returns bot response as string.
    """
    config = {"configurable": {"thread_id": thread_id}}
    events = graph.stream(
        {"messages": [HumanMessage(content=user_input)]},
        config,
        stream_mode="values"
    )
    response = None
    for ev in events:
        if "messages" in ev:
            response = ev["messages"][-1].content
    return response

def branch_thread(old_thread: str, new_thread: str, replace_msg=None) -> str:
    """
    Branch an existing thread into a new one.
    Optionally replace one user message.
    Returns the latest bot response in new thread.
    """
    # get checkpoint of old thread
    cp = memory.get(config={"configurable": {"thread_id": old_thread}})
    messages = copy.deepcopy(cp["channel_values"]["messages"])

    # optional edit
    if replace_msg:
        for msg in messages:
            if msg.__class__.__name__ == "HumanMessage" and replace_msg["old"] in msg.content:
                msg.content = replace_msg["new"]

    # replay messages into new thread
    config_new = {"configurable": {"thread_id": new_thread}}
    events = graph.stream({"messages": messages}, config=config_new, stream_mode="values")

    response = None
    for ev in events:
        if "messages" in ev:
            response = ev["messages"][-1].content
    return response
