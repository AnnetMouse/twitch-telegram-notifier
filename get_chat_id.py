import os
import sys

import requests


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    if not token:
        print(
            "Не заполнен секрет TELEGRAM_BOT_TOKEN.",
            file=sys.stderr
        )
        sys.exit(1)

    response = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        params={
            "timeout": 10,
            "allowed_updates": '["message","channel_post"]'
        },
        timeout=25
    )

    response.raise_for_status()
    data = response.json()

    if not data.get("ok"):
        print(f"Ошибка Telegram: {data}", file=sys.stderr)
        sys.exit(1)

    chats = {}

    for update in data.get("result", []):
        message = (
            update.get("message")
            or update.get("channel_post")
            or {}
        )

        chat = message.get("chat", {})
        chat_id = chat.get("id")

        if chat_id is None:
            continue

        title = (
            chat.get("title")
            or chat.get("username")
            or chat.get("first_name")
            or "Без названия"
        )

        chats[str(chat_id)] = {
            "id": chat_id,
            "type": chat.get("type", "unknown"),
            "title": title
        }

    if not chats:
        print("Сообщения не найдены.")
        print("Сначала отправьте боту команду /start.")
        print(
            "Если уведомления нужны в группе — "
            "добавьте туда бота и отправьте сообщение."
        )
        print(
            "Если уведомления нужны в канале — "
            "назначьте бота администратором и опубликуйте запись."
        )
        return

    print("Найдены Telegram-чаты:\n")

    for chat in chats.values():
        print(f"Название: {chat['title']}")
        print(f"Тип:      {chat['type']}")
        print(f"Chat ID:  {chat['id']}")
        print("-" * 40)


if __name__ == "__main__":
    main()
