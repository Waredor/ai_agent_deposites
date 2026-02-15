import os

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
