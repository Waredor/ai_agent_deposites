import os
import requests
from bs4 import BeautifulSoup

from langchain_gigachat import GigaChat
from langchain_core.tools import tool
from langchain.agents import create_agent


class SimpleMemory:
    """
    Класс памяти для ИИ-агента
    """

    def __init__(self):
        self.history = []

    def load_memory_variables(self):
        """Возвращает историю для промпта"""
        history_text = ""
        for msg in self.history:
            history_text += f"{msg}\n"

        return {"chat_history": history_text}

    def save_context(self, role: str, message: str):
        """Сохраняет сообщение в историю"""
        if role == "user":
            self.history.append({"role": "user", "content": message})

        else:
            self.history.append({"role": "assistant", "content": message})

    def clear(self):
        """Очищает историю"""
        self.history = []


@tool
def check_asv(bank_name: str = None, amount: int = None, currency: str = 'RUB') -> str:
    """
    ПРОВЕРКА ЛИМИТА АСВ. Требует банк и сумму!
    Если пользователь не указал валюту - по умолчанию используются рубли.
    Если пользователь указал доллары - currency = "USD",
    если евро - currency = "EUR",
    юани - currency = "CNY"

    Args:
        bank_name: название банка (Сбер, Тинькофф, ВТБ и т.д.)
        amount: сумма в цифрах
        currency: валюта (RUB, USD, EUR)
    Returns:
        Ответ в виде строки, содержащий:
        - Информацию по превышению лимита АСВ
        - Предупреждение, что вклад валютный (если валюта вклада не рубли)
    """
    if not bank_name or not amount:
        return "Не хватает данных: укажите банк и сумму"
    if currency != "RUB":
        return "АСВ не страхует валютные вклады!"
    if amount > 1400000:
        delta = amount - 1400000
        return (f"Превышен лимит АСВ! Лимит: 1400000 рублей, ваш вклад в банке {bank_name}:"
                f" {amount} рублей,"
                f"превышение: {delta} рублей.")
    return "Все хорошо, лимит не превышен."


@tool
def calculate_real_yield(bank_name: str = None, amount: int = None, rate: float = None, currency: str = 'RUB') -> str:
    """
    РАССЧЕТ РЕАЛЬНОЙ ДОХОДНОСТИ ВКЛАДА. Требует банк, процентную ставку вклада и сумму!
    Если пользователь не указал валюту - по умолчанию используются рубли.
    Если пользователь указал доллары - currency = "USD",
    если евро - currency = "EUR",
    юани - currency = "CNY"

    Args:
        bank_name: название банка (Сбер, Тинькофф, ВТБ и т.д.)
        amount: сумма в цифрах
        currency: валюта (RUB, USD, EUR)
        rate: процентная ставка по вкладу (например 10.0)
    Returns:
        Ответ в виде строки, содержащий:
        - Информацию о реальной доходности вклада
        - Предупреждение, что вклад валютный (если валюта вклада не рубли)
        ЕСЛИ НЕ ПОЛУЧАЕТСЯ РАССЧИТАТЬ РЕАЛЬНУЮ ДОХОДНОСТЬ - СКАЖИ ОБ ЭТОМ ПОЛЬЗОВАТЕЛЮ!!!
    """
    if currency != "RUB":
        return "Не могу рассчитать реальную доходность по валютному вкладу!"
    inflation_rate = get_inflation_rate()
    if inflation_rate is None:
        return "Не удалось получить информацию об инфляции. Не получится рассчитать реальную доходность.ы"
    real_rate = float(rate / 100.0)- inflation_rate
    if real_rate < 0:
        return (f"Доходность вклада в банке {bank_name} не покрывает инфляцию! "
                f"Текущая инфляция: {inflation_rate} %, Ваша ставка по депозиту: {rate} %")
    elif real_rate == 0:
        return (f"Доходность вклада в банке {bank_name} равна инфляции."
                f"Текущая инфляция: {inflation_rate} %, Ваша ставка по депозиту: {rate} %")
    else:
        return (f"Доходность вклада в банке {bank_name} больше инфляции - вы зарабатываете с помощью вклада!"
                f"Текущая инфляция: {inflation_rate} %, Ваша ставка по депозиту: {rate} %, "
                f"примерная годовая доходность: {real_rate * amount} рублей")


def get_inflation_rate() -> float | None:
    """
    Парсинг сайта ЦБ РФ для получения текущего значения инфляции
    """
    url = "https://cbr.ru/hd_base/infl/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        else:
            soup = BeautifulSoup(response.content, "html.parser")
            table = soup.find('table')
            if not table:
                return None
            rows = table.find_all('tr')
            if len(rows) < 2:
                return None
            second_row = rows[1]
            cells = second_row.find_all('td')
            if len(cells) < 3:
                return None
            third_cell = cells[2]
            value_text = third_cell.get_text(strip=True).replace(',', '.')

            return float(value_text) / 100.0
    except Exception as e:
        return None

root = os.path.dirname(__file__)
print(root)
prompt_path = os.path.join(root, "prompts", "prompt_financial_agent.txt")

with open(prompt_path, mode='r', encoding='utf-8') as f:
    financial_agent_prompt = f.read()

model = GigaChat(
    credentials="MDE5YTJiN2MtZjg4NC03MDJiLWE3NWMtNGRlZWE0NDU1ZDJlOmUxMWRkODZkLTI3NWYtNDVhMC1iMWQ0LTZmNzQ5OTYwMTAxYw==",
    model="Gigachat",
    scope="GIGACHAT_API_PERS",
    verify_ssl_certs=False,
    temperature=0.3
)

agent = create_agent(
    model=model,
    tools=[check_asv],
    system_prompt=financial_agent_prompt
)

memory = SimpleMemory()


def main():
    print("АГЕНТ АСВ")
    print("Спросите про вклад в банке")
    print("Например: 'У меня в сбере 2.5 млн рублей'")
    print("Или: '5000 долларов в райффайзене'")
    print("Для выхода напишите 'пока'\n")

    while True:
        user_input = input("Вы: ").strip()

        if user_input.lower() in ['пока', 'выход', 'exit', 'quit']:
            print("Агент: До свидания!")
            break

        if not user_input:
            continue

        history_text = memory.load_memory_variables()["chat_history"]
        print(f'history:\n{history_text}')
        user_input_formated = f'Запрос: {user_input}, история: {history_text}'
        memory.save_context(role="user", message=user_input)
        #print(f"user_input:\n{user_input}")

        try:
            result = agent.invoke({
                "messages": [
                    {"role": "user", "content": user_input_formated},
                ]
            })

            #print(f"result: {result}")

            if isinstance(result, dict) and "messages" in result:
                last_message = result["messages"][-1]
                if hasattr(last_message, "content"):
                    agent_response = last_message.content
                else:
                    agent_response = str(last_message)
            elif hasattr(result, "content"):
                agent_response = result.content
            else:
                agent_response = str(result)

            #print(f"agent_response: {agent_response}")
            memory.save_context(role="assistant", message=agent_response)
            new_memory = memory.load_memory_variables()["chat_history"]
            print(f'history_after_agent_response:\n{new_memory}')

            print(f"Агент: {agent_response}\n")

        except Exception as e:
            print(f"Ошибка: {e}\n")


if __name__ == "__main__":
    main()
