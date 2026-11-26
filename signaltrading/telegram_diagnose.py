"""Safe local Telegram diagnostics; no sends, webhook changes or update offsets."""

import argparse
import json
import os
from pathlib import Path
import re
import socket
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def query(token, method):
    if method not in ("getMe", "getWebhookInfo", "getUpdates"):
        raise ValueError("Unsupported diagnostic method")
    try:
        with urlopen(f"https://api.telegram.org/bot{token}/{method}", timeout=10) as response:
            data = json.load(response)
    except HTTPError as exc:
        return {"ok": False, "error": {401: "TOKEN_REJECTED", 404: "TOKEN_OR_ENDPOINT_INVALID",
                                       409: "UPDATES_CONFLICT", 429: "RATE_LIMITED"}.get(exc.code, "HTTP_ERROR"),
                "http_status": exc.code}
    except (TimeoutError, socket.timeout):
        return {"ok": False, "error": "NETWORK_TIMEOUT"}
    except URLError as exc:
        reason = exc.reason
        category = ("DNS_ERROR" if isinstance(reason, socket.gaierror) else
                    "TLS_ERROR" if isinstance(reason, ssl.SSLError) else
                    "NETWORK_TIMEOUT" if isinstance(reason, TimeoutError) else "NETWORK_ERROR")
        return {"ok": False, "error": category}
    except (ValueError, OSError):
        return {"ok": False, "error": "INVALID_RESPONSE_OR_NETWORK_ERROR"}
    if not isinstance(data, dict) or data.get("ok") is not True:
        return {"ok": False, "error": "API_REJECTED"}
    return {"ok": True, "result": data.get("result")}


def diagnose(token, request=query):
    if not isinstance(token, str) or not re.fullmatch(r"\d+:[A-Za-z0-9_-]+", token):
        return {"status": "TOKEN_MISSING_OR_BAD_FORMAT"}
    identity = request(token, "getMe")
    if not identity.get("ok"):
        return {"stage": "getMe", **identity}
    result = identity.get("result")
    if not isinstance(result, dict) or result.get("is_bot") is not True:
        return {"status": "INVALID_BOT_RESPONSE"}
    report = {"bot_username": result.get("username"), "token_valid": True}
    webhook = request(token, "getWebhookInfo")
    if not webhook.get("ok"):
        return {**report, "stage": "getWebhookInfo", **webhook}
    info = webhook.get("result")
    if not isinstance(info, dict):
        return {**report, "status": "INVALID_WEBHOOK_RESPONSE"}
    if info.get("url"):
        return {**report, "status": "WEBHOOK_ACTIVE", "note": "Webhook preserved; getUpdates not called."}
    updates = request(token, "getUpdates")
    if not updates.get("ok"):
        return {**report, "stage": "getUpdates", **updates}
    if not isinstance(updates.get("result"), list):
        return {**report, "status": "INVALID_UPDATES_RESPONSE"}
    chats = {}
    for update in updates["result"]:
        if not isinstance(update, dict):
            continue
        for key in ("message", "edited_message", "channel_post", "my_chat_member"):
            message = update.get(key)
            chat = message.get("chat") if isinstance(message, dict) else None
            if isinstance(chat, dict) and type(chat.get("id")) is int:
                chats[chat["id"]] = chat.get("type", "unknown")
    return {**report, "status": "CHATS_FOUND" if chats else "NO_RECENT_MESSAGES",
            "chats": [{"chat_id": ident, "type": kind} for ident, kind in chats.items()]}


def read_env_value(path, name):
    """Read only the token assignment; no shell execution/interpolation."""
    tokens = []
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        raise ValueError("ENV_FILE_UNREADABLE") from None
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != name:
            continue
        value = value.strip()
        if value.startswith(("'", '"')):
            quote = value[0]
            end = value.find(quote, 1)
            if end < 0 or (value[end+1:].strip() and not value[end+1:].strip().startswith("#")):
                raise ValueError("TOKEN_QUOTING_ERROR" if name == "TELEGRAM_BOT_TOKEN" else "CHAT_IDS_QUOTING_ERROR")
            value = value[1:end]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        tokens.append(value)
    if len(tokens) > 1:
        raise ValueError("DUPLICATE_TOKEN_ASSIGNMENT" if name == "TELEGRAM_BOT_TOKEN" else "DUPLICATE_CHAT_IDS_ASSIGNMENT")
    return tokens[0] if tokens else ""


def read_env_token(path):
    return read_env_value(path, "TELEGRAM_BOT_TOKEN")


def token_problem(token):
    if not token:
        return "TOKEN_EMPTY_OR_NOT_LOADED"
    if any(c in token for c in "‘’“”"):
        return "TOKEN_CONTAINS_SMART_QUOTES"
    if any(c.isspace() or ord(c) > 127 for c in token):
        return "TOKEN_CONTAINS_WHITESPACE_OR_HIDDEN_UNICODE"
    if token.startswith(("bot", "http")):
        return "USE_TOKEN_ONLY_NOT_URL_OR_BOT_PREFIX"
    return "TOKEN_FORMAT_INVALID"


def main():
    parser = argparse.ArgumentParser(description="Safe Telegram diagnosis; never sends messages")
    parser.add_argument("--env-file", type=Path, help="Read token directly from this file instead of shell environment")
    args = parser.parse_args()
    try:
        token = read_env_token(args.env_file) if args.env_file else os.environ.get("TELEGRAM_BOT_TOKEN", "")
    except ValueError as exc:
        print(json.dumps({"status": str(exc)}))
        return 2
    report = diagnose(token)
    if report.get("status") == "TOKEN_MISSING_OR_BAD_FORMAT":
        report["reason"] = token_problem(token)
    report["token_source"] = "env_file" if args.env_file else "process_environment"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "CHATS_FOUND" else 2


if __name__ == "__main__":
    raise SystemExit(main())