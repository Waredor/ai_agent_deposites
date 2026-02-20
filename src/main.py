import requests

def main():
    url = 'http://127.0.0.1'
    port = 8000
    full_url = url + ":" + str(port)

    print(full_url)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Content-Type': 'application/json'
    }

    while True:
        user_message = input("Вы: ").strip()
        if user_message.lower() in ["пока", "до свидания!", "выход", "exit", "quit"]:
            print("Агент: До свидания!")
            break

        if not user_message:
            continue

        data = {"user_input": user_message}


        try:
            response = requests.post(full_url + '/invoke', headers=headers, json=data)
            if response.status_code == 200:
                answer = response.json()["assistant_message"]
                print(f"Агент: {answer}")

        except Exception as e:
            print(f"Ошибка: {e}")
            print("Попробуйте еще раз.\n")


if __name__ == '__main__':
    main()