#!/usr/bin/env python3

from __future__ import annotations

import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

TEXT_LIMIT = 4096
CAPTION_LIMIT = 1024

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".m4v",
    ".webm",
    ".mkv",
    ".avi",
}


class CliError(RuntimeError):
    pass


@dataclass(frozen=True)
class Args:
    text: str = ""
    file: str = ""
    stdin: bool = False
    help: bool = False


@dataclass(frozen=True)
class Config:
    token: str
    chat_id: str


def usage(program_name: str) -> str:
    return "\n".join(
        [
            "Usage:",
            f"  {program_name} --text \"hello\"",
            f"  {program_name} --file ./image.png",
            f"  {program_name} --text \"caption\" --file ./video.mp4",
            f"  {program_name} --text \"report\" --file ./report.pdf",
            f"  git log -5 | {program_name} --stdin",
            f"  {program_name} --stdin --file ./report.pdf < notes.txt",
            "",
            "Options:",
            "  --text TEXT    Message text, or the caption when --file is given",
            "  --file PATH    File to send",
            "  --stdin        Read the message text from standard input instead of --text",
            "  -h, --help     Show this help",
            "",
            "Environment:",
            "  TG_BOT_TOKEN   Telegram bot token (required)",
            "  TG_CHAT_ID     Target chat ID or @channelusername (required)",
            "",
            "Multi-line text:",
            "  Text is sent as-is, as plain text (no Markdown or HTML parsing). Telegram",
            "  breaks the line wherever the text contains a real newline character; an",
            "  empty line gives a paragraph gap. A typed backslash-n is not converted:",
            f"  {program_name} --text \"one\\ntwo\" arrives as the literal one\\ntwo.",
            "",
            "  Ways to pass real newlines:",
            f"    {program_name} --text $'line one\\nline two'      # bash/zsh $'...' quoting",
            f"    {program_name} --text \"line one",
            "    line two\"                                 # press Enter inside the quotes",
            f"    printf 'line one\\nline two\\n' | {program_name} --stdin",
            f"    {program_name} --stdin <<'EOF'              # best for long messages",
            "    line one",
            "",
            "    line three, after a blank line",
            "    EOF",
            "",
            "  With --stdin, trailing newlines are dropped; everything else is kept.",
            "",
            "Notes:",
            "  - At least one of --text, --stdin or --file is required.",
            "  - --text and --stdin cannot be combined.",
            "  - Images and videos are sent as Telegram media when the extension is recognized.",
            "  - Other files are sent as documents, so PDFs, archives, and extensionless files work.",
            "  - If the text is too long for a media caption, the file is sent first and the text is sent as follow-up messages.",
            f"  - Text over {TEXT_LIMIT} characters is split into several messages, at line breaks where possible.",
        ]
    )


def resolve_program_name(raw_program_name: str) -> str:
    program_name = Path(raw_program_name).name
    if program_name == "tg_push.py":
        return "python3 -m tg_push"
    return program_name or "tg-push"


def parse_args(argv: list[str], program_name: str) -> Args:
    args = Args()
    index = 0

    while index < len(argv):
        current = argv[index]

        if current in {"--help", "-h"}:
            args = replace(args, help=True)
            index += 1
            continue

        if current == "--stdin":
            args = replace(args, stdin=True)
            index += 1
            continue

        if current not in {"--text", "--file"}:
            raise CliError(f"Unknown argument: {current}\n\n{usage(program_name)}")

        if index + 1 >= len(argv):
            raise CliError(f"Missing value for {current}\n\n{usage(program_name)}")

        value = argv[index + 1]
        if current == "--text":
            args = replace(args, text=value)
        else:
            args = replace(args, file=value)

        index += 2

    return args


def read_stdin_text() -> str:
    return sys.stdin.read().rstrip("\r\n")


def get_config() -> Config:
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")

    if not token:
        raise CliError(
            "TG_BOT_TOKEN is not set.\n"
            "Get a token from @BotFather on Telegram: https://t.me/BotFather\n"
            "Then set it: export TG_BOT_TOKEN=<your-token>"
        )
    if not chat_id:
        raise CliError(
            "TG_CHAT_ID is not set.\n"
            "For a 1:1 bot chat, use your Telegram user ID (send /start to @userinfobot to find it).\n"
            "For a group or channel, use its numeric ID or @username.\n"
            "Then set it: export TG_CHAT_ID=<your-chat-id>"
        )

    return Config(token=token, chat_id=chat_id)


def detect_media_type(file_path: Path) -> tuple[str, str]:
    extension = file_path.suffix.lower()
    if extension in IMAGE_EXTENSIONS:
        return ("sendPhoto", "photo")
    if extension in VIDEO_EXTENSIONS:
        return ("sendVideo", "video")

    return ("sendDocument", "document")


def telegram_request(
    token: str,
    method: str,
    *,
    json_payload: dict[str, str] | None = None,
    form_payload: bytes | None = None,
    content_type: str | None = None,
) -> object:
    headers: dict[str, str] = {}
    body: bytes | None = None

    if json_payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(json_payload).encode("utf-8")
    elif form_payload is not None:
        if content_type is None:
            raise CliError("Missing content type for form upload.")
        headers["Content-Type"] = content_type
        body = form_payload

    request = urllib.request.Request(
        url=f"https://api.telegram.org/bot{token}/{method}",
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request) as response:
            status = response.status
            response_bytes = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        response_bytes = error.read()
    except urllib.error.URLError as error:
        raise CliError(f"Telegram API request failed: {error.reason}") from error

    response_text = response_bytes.decode("utf-8", errors="replace")
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise CliError(
            f"Telegram API returned non-JSON response ({status}): {response_text}"
        ) from error

    if status >= 400 or not payload.get("ok"):
        description = payload.get("description", f"Telegram API request failed with status {status}")
        if status == 401:
            description += "\nCheck that TG_BOT_TOKEN is correct (get one from @BotFather)."
        elif status == 400 and "chat not found" in (description or "").lower():
            description += "\nCheck that TG_CHAT_ID is correct."
        raise CliError(description)

    return payload.get("result")


def split_text(text: str, limit: int = TEXT_LIMIT) -> list[str]:
    chunks = []
    start = 0

    while len(text) - start > limit:
        # Break at the last newline that keeps the chunk within the limit.
        newline = text.rfind("\n", start + 1, start + limit + 1)
        if newline == -1:
            end = next_start = start + limit
        else:
            end, next_start = newline, newline + 1

        chunks.append(text[start:end])
        start = next_start

    chunks.append(text[start:])

    # Telegram rejects messages that are empty or whitespace-only.
    return [chunk for chunk in chunks if chunk.strip()]


def send_text(token: str, chat_id: str, text: str) -> int:
    sent = 0
    for chunk in split_text(text):
        telegram_request(
            token,
            "sendMessage",
            json_payload={
                "chat_id": chat_id,
                "text": chunk,
            },
        )
        sent += 1

    return sent


def build_multipart_form(
    *,
    fields: dict[str, str],
    file_field: str,
    file_path: Path,
) -> tuple[bytes, str]:
    boundary = f"----tg-send-{uuid.uuid4().hex}"
    body = bytearray()

    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
        )
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")

    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        (
            f'Content-Disposition: form-data; name="{file_field}"; '
            f'filename="{file_path.name}"\r\n'
        ).encode("utf-8")
    )
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
    body.extend(file_path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    return bytes(body), boundary


def send_file(token: str, chat_id: str, file_name: str, text: str) -> tuple[str, int]:
    file_path = Path(file_name).expanduser()

    if not file_path.exists():
        raise CliError(f"File not found: {file_path}")
    if not file_path.is_file():
        raise CliError(f"Not a file: {file_path}")

    method, field = detect_media_type(file_path)
    caption = text if text and len(text) <= CAPTION_LIMIT else ""

    fields = {"chat_id": chat_id}
    if caption:
        fields["caption"] = caption

    form_payload, boundary = build_multipart_form(
        fields=fields,
        file_field=field,
        file_path=file_path,
    )

    telegram_request(
        token,
        method,
        form_payload=form_payload,
        content_type=f"multipart/form-data; boundary={boundary}",
    )

    follow_up_count = 0
    if text and not caption:
        follow_up_count = send_text(token, chat_id, text)

    return f"{file_path.name} ({field})", follow_up_count


def describe_delivery(chat_id: str, file_label: str, message_count: int) -> str:
    parts = []
    if file_label:
        parts.append(file_label)
    if message_count == 1:
        parts.append("1 message")
    elif message_count > 1:
        parts.append(f"{message_count} messages")

    return f"Sent {' + '.join(parts)} to {chat_id}"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    program_name = resolve_program_name(sys.argv[0])

    try:
        args = parse_args(argv, program_name)
        if args.help:
            print(usage(program_name))
            return 0

        if args.stdin and args.text:
            raise CliError("--text and --stdin cannot be combined.")

        if not args.text and not args.stdin and not args.file:
            raise CliError(
                "At least one of --text, --stdin or --file is required."
                f"\n\n{usage(program_name)}"
            )

        text = read_stdin_text() if args.stdin else args.text
        if not text.strip() and not args.file:
            raise CliError("No text to send: standard input was empty.")

        config = get_config()
        if args.file:
            file_label, message_count = send_file(
                config.token, config.chat_id, args.file, text
            )
        else:
            file_label = ""
            message_count = send_text(config.token, config.chat_id, text)

        print(describe_delivery(config.chat_id, file_label, message_count))
        return 0
    except CliError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
