# MCP Stock Markets

A demonstration of the [Model Context Protocol](https://modelcontextprotocol.io) (MCP). An AI agent manages a
virtual portfolio of S&P 500 stocks — $5,000 to start with, no real money — and it can do nothing but call the tools
of three MCP servers. Every run is recorded step by step: what the model said, each tool it called, with the
arguments it sent and the answer it got.

Code follows [coding_recipe](https://github.com/dbajet/coding_recipe).

## What MCP does here

```
                 ┌──────────────── this app (one FastAPI process) ─────────────────┐
                 │                                                                  │
 language model ◀┼─ agent ──── MCP client ──HTTP──▶ /mcp/sp500/   ─ Wikipedia's S&P 500 list
 (Claude, or any │  (AgentCommand)  (McpClientBox)  /mcp/quotes/  ─ Google Finance, Alpaca
  OpenAI-compat.)│                                  /mcp/broker/  ─ the portfolio, the orders
                 └──────────────────────────────────────────────────────────────────┘
```

1. **Three MCP servers** (`handlers/*_mcp_server.py`), built with the official Python SDK (`mcp`, `MCPServer`) and
   mounted inside the app on the Streamable HTTP transport:
   - **sp500** — `list_sectors`, `search_companies`, `get_company`: the index's members, read daily from
     Wikipedia's [List of S&P 500 companies](https://en.wikipedia.org/wiki/List_of_S%26P_500_companies).
   - **quotes** — `get_market_status`, `get_quote`, `get_daily_history`: the US market's hours (the NYSE
     calendar), a stock's latest price from [Google Finance](https://www.google.com/finance/), and its daily bars
     from [Alpaca](https://alpaca.markets/)'s free market data, whose latest IEX trade is also the fallback when
     Google fails.
   - **broker** — `get_portfolio`, `get_transactions`, `buy`, `sell`: the virtual account.

   A tool is a Python method: the SDK reads its signature for the JSON Schema of its arguments and its docstring
   for its description. Tools carry annotations (`readOnlyHint`, `openWorldHint`…). A refused order is a tool
   error (`isError`) whose message the model reads and acts on.
2. **The agent** (`commands/agent_command.py`) is an MCP client: it asks each server for its tools
   (`tools/list`), hands them to the language model with its instructions, and runs each tool the model calls
   (`tools/call`) until the model writes a summary — at most 16 rounds. It reaches the servers over HTTP on its
   own port, like any MCP client would, with a bearer token; it takes no shortcut into the code behind them.
3. **The rules are the broker's**, not the model's: whole shares; only the companies the owner chose may be
   bought, anything held may be sold; orders only while the US market is open, at a price from a trade at most
   15 minutes old that the broker fetches itself; no fees, no short selling, no borrowing — **the cash never goes
   below $0**, which the database enforces too (`CHECK (cash >= 0)`).

Every transaction is kept with its time, the stock, its price then (and where that price came from), buy or
sell, the shares, the amount and the cash left after it — and the run that placed it, with the model's reason.

## The app

- **One user**: the address in `BOOTSTRAP_ADMIN_EMAIL` signs in with an emailed link. Any other account is
  disabled at startup. The portfolio is theirs, created at the first start with `STARTING_BUDGET`.
- **Market**: the owner picks up to `MAX_COMPANIES` (10) S&P 500 companies: the only ones the agent may buy.
- **Agent**: runs every `AGENT_INTERVAL_MINUTES` (30) while the market is open, and on *Run now*. Each run's
  transcript is shown, every MCP call with its server, arguments, answer and duration. *The MCP servers and
  their tools* lists what the servers advertise, asked live over MCP.
- **Portfolio**: cash, positions at their latest price, and the value over time (a valuation is recorded
  after each run and every half hour of market time).
- **Settings › Language models**: Claude (cloud) or any OpenAI-compatible endpoint that supports tool calls,
  such as a local vLLM. Each connection has a green or red light; one is chosen to trade.

## Running it locally

```bash
cp .env.example .env && chmod 600 .env       # APP_ENV=dev; leave SMTP_HOST empty
docker run -d --name mcp_stock_markets-dev-db -p 127.0.0.1:5550:5432 \
    -e POSTGRES_DB=db_mcp_stock_markets -e POSTGRES_USER=user_mcp_stock_markets -e POSTGRES_PASSWORD=dev \
    postgres:16-alpine
DATABASE_URL=postgresql://user_mcp_stock_markets:dev@127.0.0.1:5550/db_mcp_stock_markets \
BOOTSTRAP_ADMIN_EMAIL=you@example.com \
    uv run --env-file .env uvicorn mcp_stock_markets.main:app --app-dir app --port 8150
```

Open <http://localhost:8150> and ask for a sign-in link: without `SMTP_HOST` it is written to the log. The S&P 500
list is read at the first start. Choose companies in *Market*, add a language model in *Settings*, then *Run now*.
An Alpaca key pair (free) adds the daily history; without one the agent is told the history is unavailable.

To point another MCP client at a laptop's servers (the
[MCP Inspector](https://github.com/modelcontextprotocol/inspector), a desktop assistant), set `MCP_TOKEN` in
`.env` and give the client a server's URL (`http://127.0.0.1:8150/mcp/quotes/`, Streamable HTTP) and the header
`Authorization: Bearer <token>`.
In production nginx answers `/mcp/` with 404: the servers exist for the app's own agent.

## Checks

```bash
docker run -d --name mcp_stock_markets-test-db -p 127.0.0.1:55452:5432 \
    -e POSTGRES_DB=mcp_stock_markets_test -e POSTGRES_USER=mcp_stock_markets -e POSTGRES_PASSWORD=mcp_stock_markets \
    postgres:16-alpine
export TEST_DATABASE_URL=postgresql://mcp_stock_markets:mcp_stock_markets@127.0.0.1:55452/mcp_stock_markets_test

uv run ruff check .            # lint
uv run ruff format --check .   # formatting
uv run mypy .                  # strict types
uv run pytest                  # tests, 100% coverage required
```

CI runs the same four on every push; a deploy refuses a commit that did not pass. The tests never reach Google,
Wikipedia, Alpaca or a language model: each has a fake in `tests/support/`. The MCP servers and client
are tested for real, in process.

## Code layout

```
app/mcp_stock_markets/
├── main.py        # AppFactory: builds and wires everything, mounts the MCP servers
├── handlers/      # HTTP routes, and the three MCP servers (*McpServer) with their token guard
├── commands/      # what the app does: the broker, quotes, companies, the agent, the scheduler's routine…
├── libraries/     # database stores, outside services (*Box: Google, Wikipedia, Alpaca, LLMs, MCP client)
├── structures/    # immutable data types
├── constants/     # settings that are not configuration: market hours, the agent's instructions…
└── static/        # the web app: plain HTML, CSS and JavaScript
tests/             # mirrors app/; tests/support/ holds fakes for outside services
deploy/            # deploy scripts, nginx site, backup container
```

## Deploying

One VM with Docker Compose, nginx and certbot. The app listens on the loopback only; nginx is the only way in.
Two copies run in turn (blue and green), so a release starts beside the old one and takes over only once healthy.

1. Clone the repository on the server (`/opt/mcp_stock_markets`). Create `.env` from `.env.example`
   (`APP_ENV=production`, your domain, a fresh `DATA_ENCRYPTION_KEY`, the owner's address, the Alpaca
   key pair) and `.env.backup` from `.env.backup.example`, both `chmod 600`. **Keep a copy of the encryption key and
   the backup private key off the server**: a restored backup needs both.
2. Install `deploy/nginx-mcp_stock_markets.conf` as the site, with your domain, and run
   `certbot --nginx -d <domain>`. Give the deploy user that one file, and sudo rights for `nginx -t` and
   `nginx -s reload` only.
3. On your laptop, fill `deploy/local.env` (server, SSH key, a read-only GitHub token for CI status), then run
   `deploy/deploy-from-local.sh`.

**Rollback**: the deploy prints the commands: start the previous color again and point nginx back to it.
Database changes are additive, so the previous release still runs.

**Backups**: a sidecar container dumps the database daily, encrypts the dump with
[age](https://age-encryption.org) to a key whose private half never touches the server, and uploads it to S3.
Set `BACKUP_HEARTBEAT_URL` to a monitor (healthchecks.io…) that alerts when backups stop; left empty, every backup and every deploy warns that nobody would be alerted. What a backup keeps:
the account, the model connections, the chosen companies, the portfolio, every transaction and every run.

### Restore drill (every quarter)

Restores into a throwaway container, never over the live database:

```bash
(
set -euo pipefail
aws s3 cp s3://<bucket>/daily/mcp_stock_markets/<date>/db_mcp_stock_markets.dump.age .
age -d -i mcp_stock_markets-backup.key -o db_mcp_stock_markets.dump db_mcp_stock_markets.dump.age
docker run -d --name mcp_stock_markets-restore-drill -p 127.0.0.1:55499:5432 -e POSTGRES_PASSWORD=drill postgres:16-alpine
until docker exec mcp_stock_markets-restore-drill pg_isready -q -h 127.0.0.1 -U postgres; do sleep 1; done
docker exec -i mcp_stock_markets-restore-drill pg_restore -U postgres -d postgres --create --no-owner --exit-on-error < db_mcp_stock_markets.dump
docker exec mcp_stock_markets-restore-drill psql -U postgres -d db_mcp_stock_markets -c '\dt+'
)
```

Then start a local copy of the app against it
(`DATABASE_URL=postgresql://postgres:drill@127.0.0.1:55499/db_mcp_stock_markets` and the production
`DATA_ENCRYPTION_KEY`) and open the portfolio and a run. Clean up with
`docker rm -f mcp_stock_markets-restore-drill && shred -u db_mcp_stock_markets.dump*`.

**Real recovery**: the same download and decryption; then stop both app colors,
`pg_restore --clean --if-exists` into the live database, and start the color nginx points at. Up to a day of
data can be lost.

## Limitations

- **Google Finance has no API.** The price is read from its quote page, whose embedded data may change shape at
  any time; the app then falls back to Alpaca, and when neither answers, to the last price read — which the
  broker refuses once it is more than 15 minutes old.
- **Alpaca's free plan** carries live trades from IEX only, one exchange among many: for a quiet stock its last
  trade may be minutes old. Each company's daily history (every exchange) is fetched once a day.
- **The holiday calendar** is written into `MarketConstants` through 2027. A holiday it does not know reads as
  a trading day — and the broker still refuses, since the latest trade is a day old.
- The agent's decisions are a language model's: this is a demonstration of MCP, not investment advice.
