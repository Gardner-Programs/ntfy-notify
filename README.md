# ntfy-notify

A tiny [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that
lets Claude / Cowork push notifications to your phone via
[ntfy](https://ntfy.sh). Point a scheduled task at it and the results land on your
lock screen instead of waiting in a log somewhere.

**Why I built this:** I run a scheduled daily job-search inbox sweep, and I wanted
the summary on my phone the moment it finishes instead of having to go check on it.
ntfy is a dead-simple pub/sub-over-HTTP service, so the whole thing is one HTTP POST
behind an MCP tool.

## What it does

Exposes two MCP tools over stdio:

| Tool | Purpose |
| --- | --- |
| `send_notification(message, title="", priority="default", tags="", click_url="")` | Send any push notification to your configured ntfy topic. |
| `send_job_alert(summary)` | Convenience wrapper: title **"Job sweep"**, high priority, briefcase tag. |

`priority` accepts `min` / `low` / `default` / `high` / `urgent` (or `"1"`..`"5"`).
`tags` is a comma-separated list of [emoji shortcodes](https://docs.ntfy.sh/emojis/),
e.g. `tada,computer`. `click_url` opens when you tap the notification.

## How ntfy works (30-second version)

ntfy is pub/sub over HTTP. You pick a **topic** — any string — and subscribe to it
in the phone app. Anyone who knows the topic name can publish to it with a single
HTTP POST, and it shows up on every subscribed device. There's no account or auth
for public topics, which means **the topic name is the only secret**, so make it
long and random.

## How it works

There's no daemon and no always-on process. A **stdio MCP server** is launched
by the client (Claude/Cowork) as a child process when a session starts, speaks
JSON-RPC over stdin/stdout, stays idle until a tool is called, and is shut down
when the session ends.

```
Claude / Cowork session
        │  (launches as subprocess, JSON-RPC over stdio)
        ▼
   server.py  ──►  @mcp.tool() functions
        │              send_notification / send_job_alert
        │  builds one HTTP POST:
        │    body    = message text
        │    headers = Title / Priority / Tags / Click / Authorization
        ▼
   https://ntfy.sh/<NTFY_TOPIC>
        │  (pub/sub fan-out)
        ▼
   ntfy app on your phone
```

Key design points:

- **The topic is read from the environment, never hardcoded** (`_config()`). Since
  the topic name is the only secret in ntfy, this is what makes the repo safe to
  be public — and it fails loudly with a clear error if `NTFY_TOPIC` is unset.
- **`@mcp.tool()` turns a plain function into a tool.** The function name, type
  hints, and docstring become the schema and description that Claude reads to
  decide when and how to call it.
- **ntfy has no JSON payload.** The message is the raw request body; everything
  else (title, priority, tags, click URL, auth token) rides along as HTTP headers.
- **Every call returns an `OK:` / `FAILED:` status string** so the model knows
  whether the push actually went out. Network errors and non-2xx responses are
  caught and reported rather than raised.

## Development

Run the test suite (pure logic + header construction, no network calls):

```bash
pip install -e ".[dev]"
pytest
```

## 1. Install the ntfy app and pick a topic

1. Install ntfy on your phone:
   - **iOS:** <https://apps.apple.com/us/app/ntfy/id1625396347>
   - **Android:** [Play Store](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
     or [F-Droid](https://f-droid.org/en/packages/io.heckel.ntfy/)
2. Generate a long, random topic name so nobody else can guess it:
   ```bash
   openssl rand -hex 16
   ```
3. In the app, tap **+** and subscribe to that exact string.

## 2. Install the server

Requires Python 3.10+.

```bash
git clone https://github.com/Gardner-Programs/ntfy-notify.git
cd ntfy-notify
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Configure environment variables

Copy the example and fill it in:

```bash
cp .env.example .env
```

| Variable | Required | Default | Notes |
| --- | --- | --- | --- |
| `NTFY_TOPIC` | yes | — | Your long, random topic. Never hardcoded. |
| `NTFY_BASE_URL` | no | `https://ntfy.sh` | Set to your own host if self-hosting. |
| `NTFY_TOKEN` | no | — | Bearer token for protected / self-hosted topics. |

The server reads these from the process environment. The MCP config below sets
them directly, so a `.env` file is only needed for the curl test / manual runs.

## 4. Register the server with Cowork / Claude

Add an entry to your MCP client config. For **Claude Desktop**
(`claude_desktop_config.json`) or **Cowork**, point it at the cloned repo:

```json
{
  "mcpServers": {
    "ntfy-notify": {
      "command": "python",
      "args": ["/absolute/path/to/ntfy-notify/server.py"],
      "env": {
        "NTFY_TOPIC": "your-long-random-topic",
        "NTFY_BASE_URL": "https://ntfy.sh",
        "NTFY_TOKEN": ""
      }
    }
  }
}
```

For **Claude Code**, the equivalent one-liner:

```bash
claude mcp add ntfy-notify \
  --env NTFY_TOPIC=your-long-random-topic \
  -- python /absolute/path/to/ntfy-notify/server.py
```

> If you installed into a virtualenv, use that interpreter's absolute path
> (e.g. `/absolute/path/to/ntfy-notify/.venv/bin/python`) as the `command`.

Restart the client and the `send_notification` / `send_job_alert` tools will appear.

## 5. Verify with curl

You don't need this server to test ntfy itself — confirm your topic works first:

```bash
curl \
  -H "Title: Hello from ntfy" \
  -H "Priority: high" \
  -H "Tags: tada" \
  -d "It works!" \
  https://ntfy.sh/your-long-random-topic
```

With a token (protected / self-hosted):

```bash
curl \
  -H "Authorization: Bearer tk_yourtoken" \
  -d "It works!" \
  https://ntfy.example.com/your-long-random-topic
```

You should get a push on your phone within a second or two.

## Integration: daily job-inbox-sweep

Once the server is registered, update the scheduled **daily-job-inbox-sweep** task
so its final step calls the tool with the run's summary, e.g.:

> At the end of the run, call `send_job_alert` with a one-paragraph summary of
> what was found (new postings, replies, anything needing action).

`send_job_alert` already sets a sensible title and high priority, so a single call
with the summary text is all the task needs.

## License

MIT — see [LICENSE](LICENSE).
