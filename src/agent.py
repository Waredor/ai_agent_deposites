import os
import json
import requests

from pydantic import BaseModel
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
from fastapi import FastAPI


# CONSTANTS
GIGACHAT_TOKEN = "MDE5YTJiN2MtZjg4NC03MDJiLWE3NWMtNGRlZWE0NDU1ZDJlOmVhOGUzOTI1LTEwMWItNGNkOS1iMDE2LWNkZTNkMjBjNDI5MA=="
GIGACHAT_SCOPE = "GIGACHAT_API_PERS"
ROOT = os.path.dirname(__file__)
PROMPT_PATH = os.path.join(ROOT, "prompts", "prompt_financial_agent_ver2.txt")


# STATEDICT
class AgentState(TypedDict):
    messages: list[dict]
    last_response_finish_reason: str
    call_function: str
    function_arguments: dict


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
def llm_call(dialog, functions=None, structure=None, model='GigaChat', temperature=0.3):
    client = GigaChat(
        credentials=GIGACHAT_TOKEN,
        scope=GIGACHAT_SCOPE,
        model=model,
        verify_ssl_certs=False
    )
    roles_dict = {
        "system": MessagesRole.SYSTEM,
        "user": MessagesRole.USER,
        "assistant": MessagesRole.ASSISTANT,
        "function": MessagesRole.FUNCTION
    }

    gigachat_messages = []
    for message in dialog:
        msg_kwargs = {
            "role": roles_dict[message["role"]],
            "content": message["content"]
        }

        if message["role"] == "assistant" and "function_call" in message:
            msg_kwargs["function_call"] = message["function_call"]

        gigachat_messages.append(Messages(**msg_kwargs))

    if structure:
        structure = structure.model_json_schema()
        answer_function = Function(
            name="llm_answer",
            description="""Используй эту функцию для формирования ответа пользователю""",
            parameters=FunctionParameters(
                type=structure["type"],
                properties=structure["properties"],
                required=structure["required"]
            )
        )
        chat = Chat(
            messages=gigachat_messages,
            temperature=temperature,
            max_tokens=1024,
            functions=[answer_function],
            function_call="auto"
        )
        response = client.chat(chat).choices[0]

        assert response.finish_reason == "function_call", \
            "Вызов GigaChat со структурой не вернул объект функции, "\
            "попробуйте еще раз или перепишите промпт"

        response = response.message.function_call.arguments

    else:
        chat_params = {
            "messages": gigachat_messages,
            "temperature": temperature,
            "max_tokens": 1024
        }

        if functions:
            chat_params["functions"] = functions

        chat = Chat(**chat_params)
        response = client.chat(chat).choices[0]

    return response


def call_agent(state: AgentState) -> Dict[str, Any]:
    context = state["messages"]

    response = llm_call(context, functions=[get_best_currency_rate_desc])
    message = response.message
    finish_reason = response.finish_reason

    assistant_msg = {"role": "assistant", "content": message.content}

    if finish_reason == "function_call" and hasattr(message, 'function_call') and message.function_call:
        function_name = message.function_call.name
        function_arguments = message.function_call.arguments

        assistant_msg["function_call"] = {
            "name": function_name,
            "arguments": function_arguments
        }
    else:
        function_name = ""
        function_arguments = ""

    context.append(assistant_msg)

    return {
        "messages": context,
        "last_response_finish_reason": finish_reason,
        "call_function": function_name,
        "function_arguments": function_arguments
    }


def tool_node(state: AgentState) -> Dict[str, Any]:
    context = state["messages"]
    name = state["call_function"]
    arguments = state["function_arguments"]

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {}

    if name == "get_curr_rate":
        function_result = get_currency_rate(**arguments)
    else:
        function_result = f"Неизвестная функция: {name}"

    context.append({
        "role": "function",
        "name": name,
        "content": json.dumps({"result": function_result}, ensure_ascii=False)
    })

    return {
        "messages": context,
        "call_function": "",
        "function_arguments": {}
    }


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

# FASTAPI
class InPayload(BaseModel):
    user_input: str

class OutPayload(BaseModel):
    assistant_message: str

app = FastAPI()

with open(PROMPT_PATH, mode="r", encoding="utf-8") as f:
    system_message = f.read()

app_state = {
    "messages": [{"role": "system", "content": system_message}]
}


@app.post('/invoke', response_model=OutPayload)
async def invoke(payload: InPayload):
    global app_state

    user_message = payload.user_input
    app_state["messages"].append({
        "role": "user",
        "content": user_message
    })

    app_state = agent.invoke(app_state)
    last_message = app_state["messages"][-1]

    return OutPayload(assistant_message=last_message["content"])