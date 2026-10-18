import argparse
import html
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests


STATE_FILE = Path("state.json")
REQUEST_TIMEOUT = 25


def get_env(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"Не заполнена переменная или секрет GitHub: {name}"
        )

    return value


def load_state() -> dict:
    default_state = {
        "is_live": False,
        "last_stream_id": ""
    }

    if not STATE_FILE.exists():
        return default_state

    try:
        with STATE_FILE.open("r", encoding="utf-8") as file:
            state = json.load(file)

        if not isinstance(state, dict):
            return default_state

        return {
            "is_live": bool(state.get("is_live", False)),
            "last_stream_id": str(state.get("last_stream_id", ""))
        }

    except (OSError, json.JSONDecodeError):
        return default_state


def save_state(state: dict) -> None:
    temporary_file = STATE_FILE.with_suffix(".tmp")

    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(
            state,
            file,
            ensure_ascii=False,
            indent=2
        )
        file.write("\n")

    temporary_file.replace(STATE_FILE)


def get_twitch_access_token(
    client_id: str,
    client_secret: str
) -> str:
    response = requests.post(
        "https://id.twitch.tv/oauth2/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials"
        },
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()

    data = response.json()
    access_token = data.get("access_token")

    if not access_token:
        raise RuntimeError(
            "Twitch не вернул access_token. "
            "Проверьте TWITCH_CLIENT_ID и TWITCH_CLIENT_SECRET."
        )

    return access_token


def get_stream(
    channel: str,
    client_id: str,
    access_token: str
) -> dict | None:
    response = requests.get(
        "https://api.twitch.tv/helix/streams",
        headers={
            "Client-ID": client_id,
            "Authorization": f"Bearer {access_token}"
        },
        params={
            "user_login": channel
        },
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()

    data = response.json().get("data", [])

    if not data:
        return None

    return data[0]


def send_telegram_message(
    bot_token: str,
    chat_id: str,
    text: str,
    channel: str
) -> None:
    channel_url = f"https://www.twitch.tv/{quote(channel)}"

    response = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {
                            "text": "🟣 Смотреть стрим",
                            "url": channel_url
                        }
                    ]
                ]
            }
        },
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(
            f"Telegram вернул ошибку: {result}"
        )


def create_live_message(stream: dict) -> str:
    streamer = html.escape(
        str(stream.get("user_name", "Стример"))
    )

    title = html.escape(
        str(stream.get("title", "Без названия"))
    )

    game = html.escape(
        str(stream.get("game_name", "Категория не указана"))
    )

    viewers = stream.get("viewer_count", 0)

    return (
        "🔴 <b>СТРИМ НАЧАЛСЯ!</b>\n\n"
        f"🎙 <b>{streamer}</b> уже в эфире!\n\n"
        f"🎮 <b>Категория:</b> {game}\n"
        f"📝 <b>Название:</b> {title}\n"
        f"👥 <b>Зрителей:</b> {viewers}\n\n"
        "Залетайте на стрим! 🐭🧀"
    )


def send_test_message() -> None:
    bot_token = get_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_env("TELEGRAM_CHAT_ID")
    channel = get_env("TWITCH_CHANNEL").lower()

    text = (
        "✅ <b>Проверка уведомлений</b>\n\n"
        "Telegram-бот успешно подключён.\n"
        "Уведомления о начале стрима будут приходить сюда. 🐭🧀"
    )

    send_telegram_message(
        bot_token=bot_token,
        chat_id=chat_id,
        text=text,
        channel=channel
    )

    print("Тестовое сообщение успешно отправлено.")


def check_stream() -> None:
    twitch_client_id = get_env("TWITCH_CLIENT_ID")
    twitch_client_secret = get_env("TWITCH_CLIENT_SECRET")
    twitch_channel = get_env("TWITCH_CHANNEL").lower()

    telegram_bot_token = get_env("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = get_env("TELEGRAM_CHAT_ID")

    state = load_state()

    print(f"Проверяется Twitch-канал: {twitch_channel}")

    access_token = get_twitch_access_token(
        twitch_client_id,
        twitch_client_secret
    )

    stream = get_stream(
        channel=twitch_channel,
        client_id=twitch_client_id,
        access_token=access_token
    )

    if stream is None:
        print("Сейчас канал не в эфире.")

        if state.get("is_live"):
            state["is_live"] = False
            save_state(state)
            print("Состояние изменено на OFFLINE.")

        return

    stream_id = str(stream.get("id", ""))

    print(f"Канал в эфире. Stream ID: {stream_id}")

    already_notified = (
        stream_id
        and stream_id == state.get("last_stream_id")
    )

    if already_notified:
        print("Уведомление об этом стриме уже отправлялось.")

        if not state.get("is_live"):
            state["is_live"] = True
            save_state(state)

        return

    message = create_live_message(stream)

    send_telegram_message(
        bot_token=telegram_bot_token,
        chat_id=telegram_chat_id,
        text=message,
        channel=twitch_channel
    )

    state["is_live"] = True
    state["last_stream_id"] = stream_id
    save_state(state)

    print("Уведомление о начале стрима отправлено.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Twitch → Telegram notifier"
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Отправить тестовое сообщение"
    )

    args = parser.parse_args()

    try:
        if args.test:
            send_test_message()
        else:
            check_stream()

    except requests.HTTPError as error:
        print(
            f"Ошибка HTTP: {error}",
            file=sys.stderr
        )

        if error.response is not None:
            print(
                error.response.text[:1000],
                file=sys.stderr
            )

        sys.exit(1)

    except Exception as error:
        print(
            f"Ошибка: {error}",
            file=sys.stderr
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
