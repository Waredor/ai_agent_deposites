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
from bs4 import BeautifulSoup


# CONSTANTS
GIGACHAT_TOKEN = "MDE5YTJiN2MtZjg4NC03MDJiLWE3NWMtNGRlZWE0NDU1ZDJlOmVhOGUzOTI1LTEwMWItNGNkOS1iMDE2LWNkZTNkMjBjNDI5MA=="
GIGACHAT_SCOPE = "GIGACHAT_API_PERS"
ROOT = os.path.dirname(__file__)
PROMPT_PATH = os.path.join(ROOT, "prompts", "prompt_financial_agent_ver2.txt")


# STATEDICT
class AgentState(TypedDict):
    messages: list
    last_response_finish_reason: str
    call_function: str


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

get_best_currency_rate_desc = Function(
    name="get_curr_rate",
    description="Находит лучший курс для обмена валюты в заданном городе. "
                "Для вызова требует город, название валюты и тип операции (покупка или продажа).",
    parameters=FunctionParameters(
        type="object",
        properties={
            "operation_type": {"type": "string", "description": "осуществляемая операция (sell или buy)"},
            "exchange_value": {"type": "string", "description": "валюта, которую нужно получить после обмена: RUB, USD, EUR, CNY"},
            "city": {"type": "string", "description": "город в России, где осуществляется обмен валюты "
                                                      "(Москва, Санкт-Петербург, Казань, Уфа, Челябинск, "
                                                      "Новосибирск, Екатеринбург, Сочи, Владивосток, Хабаровск и т.д."}
        },
        required=["operation_type", "exchange_value", "city"]
    )
)

def check_asv(bank_name: str, amount: int, currency: str = "RUB") -> str:
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


def get_currency_rate(operation_type: str, exchange_value: str, city: str) -> str:
    banki_ru_base_url = 'https://www.banki.ru/products/currency/cash/'

    city_dict = {
        "абакан": "abakan/",
        "екатеринбург": "ekaterinburg/",
        "краснодар": "krasnodar/",
        "москва": "moskva/",
        "новосибирск": "novosibirsk/",
        "санкт-петербург": "sankt-peterburg/",
        "хабаровск": "habarovsk/",
    }

    wallet_dict = {
        "usd": "currencyId=840",
        "eur": "currencyId=978"
    }


    city = city_dict.get(city.lower(), None)
    wallet = wallet_dict.get(exchange_value.lower(), None)

    if city is None:
        return f"ОШИБКА! Не могу найти курсы валют для вашего города: {city}."

    if wallet is None:
        return f"ОШИБКА! Не могу найти курсы вашей валюты {wallet}"

    full_url = banki_ru_base_url + city + "?" + wallet + "&buttonId=1"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    response = requests.get(full_url, headers=headers)
    if response.status_code == 200:
        html_page = response.text
        soup = BeautifulSoup(html_page, 'html.parser')

        bank_blocks = soup.find_all('div', attrs={'data-test': 'flexbox-grid',
                                                  'class': 'FlexboxGrid__sc-akw86o-0 bIGLzR resultItemstyled__StyledWrapperResult-sc-qb3d7j-1 lkrmgI'})

        buy_dict = {}
        sell_dict = {}

        for block in bank_blocks:
            bank_name_element = block.find('div', attrs={'data-test': 'currenct--result-item--name'})
            if not bank_name_element:
                continue

            bank_name = bank_name_element.text.strip()

            buy_element = block.find('div', attrs={'data-test': 'currency--result-item---rate-buy'})
            if buy_element:
                buy_rate_element = buy_element.find('div',
                                                    attrs={'data-test': 'text', 'class': 'Text__sc-vycpdy-0 fqodgq'})
                if buy_rate_element:
                    buy_text = buy_rate_element.text.strip()
                    buy_value = float(buy_text.replace(' ₽', '').replace(',', '.'))
                    buy_dict[bank_name] = buy_value

            sell_element = block.find('div', attrs={'data-test': 'currency--result-item---rate-sell'})
            if sell_element:
                sell_rate_element = sell_element.find('div',
                                                      attrs={'data-test': 'text', 'class': 'Text__sc-vycpdy-0 fqodgq'})
                if sell_rate_element:
                    sell_text = sell_rate_element.text.strip()
                    sell_value = float(sell_text.replace(' ₽', '').replace(',', '.'))
                    sell_dict[bank_name] = sell_value

        sorted_buy = sorted(buy_dict.items(), key=lambda x: x[1], reverse=True)
        sorted_sell = sorted(sell_dict.items(), key=lambda x: x[1])

        if operation_type.lower() == "sell":
            if sorted_buy:
                best_buy_bank, best_buy_rate = sorted_buy[0]
                return f"Лучший курс продажи валюты банку: {best_buy_bank} - {best_buy_rate}"
            else:
                return "ОШИБКА! Не найдено ни одного курса покупки"

        elif operation_type.lower() == "buy":
            if sorted_sell:
                best_sell_bank, best_sell_rate = sorted_sell[0]
                return f"Лучший курс покупки валюты у банка: {best_sell_bank} - {best_sell_rate}"
            else:
                return "Не найдено ни одного курса продажи"

        else:
            return f"ОШИБКА! Не могу найти курсы валют для твоей операции {operation_type}"

    else:
        return f"ОШИБКА! Не могу проверить курсы валют из-за отсутсвия доступа к сайту. Попробуйте позже."


# NODES
def call_agent(state: AgentState) -> Dict[str, Any]:
    context = state["messages"]

    dialog = Chat(
        messages=context,
        functions=[get_best_currency_rate_desc],
        temperature=0.3,
        max_tokens=1000
    )

    response = client.chat(dialog).choices[0]
    message = response.message
    context.append(message)

    return {"messages": context}


def tool_node(state: AgentState) -> Dict[str, Any]:
    context = state["messages"]
    last_message = context[-1]
    name = last_message.function_call.name
    arguments = last_message.function_call.arguments

    if name == "get_curr_rate":
        function_result = get_currency_rate(**arguments)

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