import os
import json
import requests

from gigachat import GigaChat
from gigachat.models import (
    Chat,
    Function,
    FunctionParameters,
    Messages,
    MessagesRole
)
from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Dict, Any


# CONSTANTS
GIGACHAT_TOKEN = "MDE5YTJiN2MtZjg4NC03MDJiLWE3NWMtNGRlZWE0NDU1ZDJlOmVhOGUzOTI1LTEwMWItNGNkOS1iMDE2LWNkZTNkMjBjNDI5MA=="
GIGACHAT_SCOPE = "GIGACHAT_API_PERS"
ROOT = os.path.dirname(__file__)
PROMPT_PATH = os.path.join(ROOT, "prompts", "prompt_financial_agent_ver2.txt")


# STATEDICT
class AgentState(TypedDict):
    messages: list
    last_response_finish_reason: str


# LLM
client = GigaChat(
    credentials=GIGACHAT_TOKEN,
    scope=GIGACHAT_SCOPE,
    model="GigaChat",
    verify_ssl_certs=False
)


# TOOLS
check_asv_desc = Function(
    name="check_asv",
    description="Проверяет лимит АСВ для вклада пользователя",
    parameters=FunctionParameters(
        type="object",
        properties={
            "bank_name": {"type": "string", "description": "название банка (Сбер, Тинькофф, ВТБ, Райффайзен и т.д.)"},
            "amount": {"type": "integer", "description": "сумма вклада (например, 5000, 2500000, 500000)"},
            "currency": {"type": "string", "description": "валюта: RUB, USD, EUR (по умолчанию RUB)"}
        },
        required=["bank_name", "amount", "currency"]
    )
)

def check_asv(bank_name: str, amount: int, currency: str = "RUB"):
    if not bank_name or not isinstance(bank_name, str):
        return "ОШИБКА: Не указано название банка. Пожалуйста, укажите банк."

    if not amount or not isinstance(amount, (int, float)):
        return "ОШИБКА: Не указана сумма вклада. Пожалуйста, укажите сумму."

    if amount <= 0:
        return "ОШИБКА: Сумма должна быть положительным числом."

    if currency != "RUB":
        return "АСВ не страхует валютные вклады!"

    if amount > 1400000:
        delta = amount - 1400000
        return (f"Превышен лимит АСВ! Лимит: 1400000 рублей, ваш вклад в банке {bank_name}:"
                f" {amount} рублей,"
                f"превышение: {delta} рублей.")

    return "Все хорошо, лимит не превышен."



# NODES
def call_agent(state: AgentState) -> Dict[str, Any]:
    context = state["messages"]

    dialog = Chat(
        messages=context,
        functions=[check_asv_desc],
        temperature=0.3,
        max_tokens=1000
    )

    response = client.chat(dialog).choices[0]
    message = response.message
    context.append(message)

    return {"messages": context, "last_response_finish_reason": response.finish_reason}


def tool_node(state: AgentState) -> Dict[str, Any]:
    context = state["messages"]
    last_message = context[-1]
    name = last_message.function_call.name
    arguments = last_message.function_call.arguments

    if name == "check_asv":
        function_result = check_asv(**arguments)

    context.append(
        Messages(
            role=MessagesRole.FUNCTION,
            content=json.dumps(
                {"result": function_result},
                ensure_ascii=False
            )
        )
    )

    return {"messages": context}


def should_continue(state: AgentState):
    finish_reason = state["last_response_finish_reason"]
    if finish_reason == "function_call":
        return "tool"

    return "__end__"


#GRAPH
workflow = StateGraph(AgentState)

workflow.add_node("agent", call_agent)
workflow.add_node("tool_node", tool_node)

workflow.add_edge(START, "agent")
workflow.add_edge("tool_node", "agent")
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "tool": "tool_node",
        "__end__": END
    }
)

agent = workflow.compile()


#MAINLOOP
def main():
    state = {
        "messages": []
    }

    with open(PROMPT_PATH, mode="r", encoding="utf-8") as f:
        system_message = f.read()

    state["messages"].append(
        Messages(
            role=MessagesRole.SYSTEM,
            content=system_message
        )
    )

    while True:
        user_message = input("Вы: ").strip()
        if user_message.lower() in ["пока", "до свидания!", "выход", "exit", "quit"]:
            print("Агент: До свидания!")
            break

        if not user_message:
            continue

        state["messages"].append(
            Messages(
                role=MessagesRole.USER,
                content=user_message
            )
        )

        try:
            final_state = agent.invoke(state)
            last_message = final_state["messages"][-1]

            state = final_state
            print(f"Агент: {last_message.content}\n")

        except Exception as e:
            print(f"Ошибка: {e}")
            print("Попробуйте еще раз.\n")


if __name__ == "__main__":
    main()