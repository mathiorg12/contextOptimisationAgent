from typing import TypedDict
from langgraph.graph import StateGraph

class State(TypedDict):
    messages: list

workflow = StateGraph(State)
