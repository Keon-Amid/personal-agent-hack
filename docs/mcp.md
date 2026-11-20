# Room Furnisher MCP server

`agent/mcp_server.py` exposes the agent's tools to any MCP client: Claude Code, Claude Desktop, and claude.ai
once it is deployed behind HTTPS. The web app uses the same tools through `claude -p`. The tools enforce the rules
(only fitting items get picked, no cart without a verified Senso check, every step audited). The model only
decides the order and writes the explanations.

**Tools (9):** `create_plan`, `analyze_room`, `style_match`, `fit_options`, `pick`, `senso_check`, `swap`,
`cart_add`, `get_plan`. Every result includes `plan_url`, and its first line reads `Open your room: <plan_url>`.
`plan_url` is `$PUBLIC_BASE_URL/plan/<plan_id>`, or `http://localhost:5173/plan/<plan_id>` when the variable isn't set.

Plans live in `~/.cache/room-furnisher/plans` (override with `ROOM_FURNISHER_PLANS_DIR`). FastAPI and the MCP
server share that folder, so a plan created from Claude shows up on the web page.

Below, `REPO` is the repo's absolute path, e.g. `/Users/brendankeane/Documents/GitHub/personal-agent-hack`. Use
the shared venv: `$REPO/.venv/bin/python` (it has `mcp`, which is listed in `agent/requirements.txt`).

## Claude Code (stdio, nothing to deploy)

```bash
claude mcp add room_furnisher -e PYTHONPATH=$REPO -- $REPO/.venv/bin/python -m agent.mcp_server
```

- Add `--scope user` to make it available in every project, or `--scope project` to write it to `.mcp.json`.
- `PYTHONPATH` lets `agent` import no matter which directory Claude Code starts in.
- Put `--` before the command, because `-e` takes several values.
- Check it with `claude mcp get room_furnisher`. A project-scoped server shows "Pending approval" until you
  open `claude` in that directory and approve it.

What we ran (about 13:55 PT, Nov 20): `claude mcp add --scope project room_furnisher -e PYTHONPATH=... -- .../python -m
agent.mcp_server` in a scratch directory. It wrote this `.mcp.json`, and `claude mcp get` listed the server as
pending approval:

```json
{"mcpServers": {"room_furnisher": {"type": "stdio",
  "command": "REPO/.venv/bin/python", "args": ["-m", "agent.mcp_server"],
  "env": {"PYTHONPATH": "REPO"}}}}
```

We also launched that same command from another directory with the `mcp` Python client, using only `PYTHONPATH`
in the environment. `list_tools` returned all 9 tools, and `create_plan` returned
`Open your room: http://localhost:5173/plan/<id>`. We did not approve the server inside an interactive Claude
Code session.

## Claude Desktop (stdio)

Settings > Developer > Edit Config opens `~/Library/Application Support/Claude/claude_desktop_config.json`. Add
this entry, using absolute paths, then restart Claude Desktop:

```json
{
  "mcpServers": {
    "room_furnisher": {
      "command": "/Users/brendankeane/Documents/GitHub/personal-agent-hack/.venv/bin/python",
      "args": ["-m", "agent.mcp_server"],
      "env": {
        "PYTHONPATH": "/Users/brendankeane/Documents/GitHub/personal-agent-hack",
        "PUBLIC_BASE_URL": "http://localhost:5173"
      }
    }
  }
}
```

Not tested in Claude Desktop yet. This is the same command and environment that we tested over stdio above.

## Streamable HTTP (for claude.ai)

```bash
$REPO/.venv/bin/python -m agent.mcp_server --http --port 8765                  # http://127.0.0.1:8765/mcp
$REPO/.venv/bin/python -m agent.mcp_server --http --host 0.0.0.0 --port 8765   # behind a proxy
```

What we ran: we started the server with `--http --port 8799` and pointed the `mcp` client at
`http://127.0.0.1:8799/mcp`. `list_tools` returned 9 tools and `create_plan` returned a plan_url.

On 127.0.0.1 the SDK turns on DNS-rebinding protection, so it accepts only localhost Host headers. On any other
`--host` that protection is off, which means the proxy in front decides who can reach it.

claude.ai needs (not done yet; kyle's deploy):
- A public **HTTPS** URL on port 443, e.g. `https://<host>/mcp`, with TLS terminated by the proxy and traffic
  forwarded to the server port. claude.ai connects from Anthropic's servers, so localhost or a LAN address
  won't work.
- `PUBLIC_BASE_URL` set to the deployed web app, so `plan_url` links open for the person.
- In claude.ai, add it as a custom connector with the `/mcp` URL (Settings > Connectors; menu path not checked by us).
- **No auth is built in.** Anyone with the URL can call the tools. That's fine for the demo because the tools only
  build carts and never buy anything, but don't leave it up afterwards.

## Tests

```bash
$REPO/.venv/bin/python -m unittest discover -s agent -t .     # offline; agent.tools mocked
LIVE=1 $REPO/.venv/bin/python -m unittest agent.test_mcp_server  # also spawns the real stdio server
```
