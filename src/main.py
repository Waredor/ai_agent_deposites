import os
import requests

#from bs4 import BeautifulSoup
from typing import TypedDict, Literal, Annotated
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_gigachat import GigaChat
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


@tool
def check_asv(bank_name: str, amount: int, currency: str = 'RUB') -> str:
    """
    ПРОВЕРКА ЛИМИТА АСВ.

    ВНИМАНИЕ! Это ЕДИНСТВЕННЫЙ инструмент для проверки вкладов.
    ТРЕБУЕТСЯ ОБЯЗАТЕЛЬНО передать ВСЕ ТРИ параметра:

    Args:
        bank_name: СТРОКА - название банка (Сбер, Тинькофф, ВТБ, Райффайзен и т.д.)
        amount: ЧИСЛО - сумма вклада (например, 5000, 2500000, 500000)
        currency: СТРОКА - валюта: RUB, USD, EUR (по умолчанию RUB)

    ВОЗВРАЩАЕТ:
        Строку с результатом проверки.

    ПРИМЕРЫ ПРАВИЛЬНОГО ВЫЗОВА:
        check_asv(bank_name="Сбер", amount=2500000, currency="RUB")
        check_asv(bank_name="Райффайзенбанк", amount=5000, currency="USD")
        check_asv(bank_name="Тинькофф", amount=800000, currency="RUB")

    НЕПРАВИЛЬНЫЙ ВЫЗОВ (ТАК ДЕЛАТЬ НЕЛЬЗЯ):
        check_asv(bank_name="Сбер")  # ОШИБКА! Нет amount
        check_asv(amount=5000)  # ОШИБКА! Нет bank_name
    """
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


def call_agent(state: AgentState):
    """
    Этот узел вызывает LLM.
    Модель может:
    1. Просто ответить пользователю
    2. Решить, что нужно вызвать инструмент (тогда в ответе будет tool_calls)
    """
    print("\nУЗЕЛ: call_agent")
    print(f"Сообщений в истории: {len(state['messages'])}")

    # Создаем системное сообщение
    system_message = SystemMessage(content=SYSTEM_PROMPT)
    messages = state["messages"]

    has_system = any(isinstance(msg, SystemMessage) for msg in messages)

    if not has_system:
        full_messages = [system_message] + messages
        print("Добавлен системный промпт")
    else:
        full_messages = messages
        print("Системный промпт уже есть в истории")

    # Вызываем модель с полной историей
    response = model_with_tools.invoke(full_messages)

    if hasattr(response, "tool_calls") and response.tool_calls:
        print(f"Модель РЕШИЛА вызвать инструмент: {response.tool_calls[0]['name']}")
        print(f"Параметры: {response.tool_calls[0]['args']}")
    else:
        print(f"Модель ОТВЕЧАЕТ: {response.content[:50]}...")

    return {"messages": [response]}


def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    """
    Эта функция решает, что делать дальше:
    - Если модель вызвала инструменты → идем в tools
    - Если модель просто ответила → завершаем
    """
    print("\nМАРШРУТИЗАТОР")

    last_message = state["messages"][-1]

    # Проверяем, есть ли вызовы инструментов
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        print("Решение: вызвать инструменты (идем в tools)")
        return "tools"

    print("Решение: ответ готов (завершаем)")
    return "__end__"

root = os.path.dirname(__file__)
print(root)
prompt_path = os.path.join(root, "prompts", "prompt_financial_agent.txt")

with open(prompt_path, mode='r', encoding='utf-8') as f:
    SYSTEM_PROMPT = f.read()

tools = [check_asv]

llm = GigaChat(
    credentials="MDE5YTJiN2MtZjg4NC03MDJiLWE3NWMtNGRlZWE0NDU1ZDJlOmUxMWRkODZkLTI3NWYtNDVhMC1iMWQ0LTZmNzQ5OTYwMTAxYw==",
    model="Gigachat",
    scope="GIGACHAT_API_PERS",
    verify_ssl_certs=False,
    temperature=0.3
)

model_with_tools = llm.bind_tools(tools)
tool_node = ToolNode(tools)

workflow = StateGraph(AgentState)
workflow.add_node("agent", call_agent)
workflow.add_node("tools", tool_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "tools": "tools",
        "__end__": END
    }
)

workflow.add_edge("tools", "agent")
agent = workflow.compile()


def main():
    print("АГЕНТ АСВ")
    print("Спросите про вклад в банке")
    print("Например: 'У меня в сбере 2.5 млн рублей'")
    print("Или: '5000 долларов в райффайзене'")
    print("Для выхода напишите 'пока'\n")

    state = {
        "messages": []
    }

    while True:
        user_input = input("Вы: ").strip()

        if user_input.lower() in ['пока', 'выход', 'exit', 'quit']:
            print("Агент: До свидания!")
            break

        if not user_input:
            continue

        state["messages"].append(HumanMessage(content=user_input))
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
