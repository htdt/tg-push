# tg-push

Python CLI for sending text plus an optional file to Telegram.

There is no bot polling loop, no MCP bridge, and no long-running server, just simple one-way messages.

## Install

```bash
pip install tg-push
```

Or with [pipx](https://pipx.pypa.io) for an isolated install:

```bash
pipx install tg-push
```

## Environment

| Variable | Required | Description |
|---|---|---|
| `TG_BOT_TOKEN` | yes | Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `TG_CHAT_ID` | yes | Target chat ID or `@channelusername` |

For a 1:1 bot chat, `TG_CHAT_ID` is your Telegram user id. For groups and channels, use the actual chat id instead.

## Usage

```bash
tg-push --text "build finished"
tg-push --file ./render.png
tg-push --text "latest render" --file ./render.png
tg-push --text "report" --file ./report.pdf
git log -5 | tg-push --stdin
tg-push --stdin --file ./report.pdf < notes.txt
```

### Multi-line text

Text is sent as-is, as plain text (no Markdown or HTML parsing). Telegram breaks the line wherever the text contains a real newline character, and an empty line gives a paragraph gap. A typed `\n` is not converted: `--text "one\ntwo"` arrives as the literal `one\ntwo`.

```bash
tg-push --text $'line one\nline two'      # bash/zsh $'...' quoting
printf 'line one\nline two\n' | tg-push --stdin
tg-push --stdin <<'EOF'                   # best for long messages
line one

line three, after a blank line
EOF
```

With `--stdin`, trailing newlines are dropped; everything else is kept.

## Behavior

- At least one of `--text`, `--stdin` or `--file` is required. `--text` and `--stdin` cannot be combined.
- If `--file` is present, recognized images and videos are sent as Telegram media.
- Other files are sent as documents, so PDFs, archives, and extensionless files work.
- Supported image extensions: `.jpg`, `.jpeg`, `.png`, `.webp`
- Supported video extensions: `.mp4`, `.mov`, `.m4v`, `.webm`, `.mkv`, `.avi`
- If the text is longer than Telegram's media caption limit, the file is sent first and the text is sent as follow-up messages.
- Text over 4096 characters is split into several messages, at line breaks where possible.
- On success a one-line confirmation is printed to stdout, for example `Sent report.pdf (document) to @mychannel`. Errors go to stderr with exit code 1.
- The project has no runtime dependencies outside the Python standard library.
