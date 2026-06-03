import json
import os
from pathlib import Path
from typing import List, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq


ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(ENV_PATH)


def get_groq_api_key() -> str:
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise ValueError("GROQ_API_KEY is missing. Please add it to the .env file.")
    return groq_api_key


llm = ChatGroq(
    temperature=0,
    model_name="llama-3.1-8b-instant",
    groq_api_key=get_groq_api_key(),
)


class AgentState(TypedDict):
    goal: str
    tasks: List[str]
    results: List[str]
    critique: str
    approved: bool
    iterations: int


def planner(state: AgentState) -> AgentState:
    system = """You are a planning agent. Break the user's goal into
at most 5 concrete, actionable tasks. Respond ONLY with a
valid JSON array of strings. No preamble, no markdown."""

    messages = [
        SystemMessage(content=system),
        HumanMessage(content=f"Goal: {state['goal']}"),
    ]
    response = llm.invoke(messages).content.strip()

    try:
        clean = response.replace("```json", "").replace("```", "").strip()
        tasks = json.loads(clean)
    except json.JSONDecodeError:
        tasks = [response]

    print(f"\n[Planner] Generated {len(tasks)} tasks:")
    for i, task in enumerate(tasks):
        print(f"  {i + 1}. {task}")

    return {**state, "tasks": tasks}


initial_state: AgentState = {
    "goal": "Research and summarise the top 3 trends in agriculture for 2025",
    "tasks": [],
    "results": [],
    "critique": "",
    "approved": False,
    "iterations": 0,
}


if __name__ == "__main__":
    planner(initial_state)
