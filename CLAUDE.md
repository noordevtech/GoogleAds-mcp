# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Install
```bash
pip install -e .            # runtime deps
pip install -e ".[dev]"     # adds pytest, pytest-asyncio, black, ruff, mypy
```

### Run the server
```bash
python run_server.py        # stdio MCP server (preferred entry point — adds src/ to sys.path)
python -m src               # equivalent, via src/__main__.py
LOG_LEVEL=DEBUG python -m src   # debug logging
```

The server speaks MCP over stdio. To expose it over HTTP (port 8000), use the Docker image — `entrypoint.sh` wraps the stdio server with `mcp-proxy`.

### Lint / format / typecheck
```bash
ruff check src/
black src/
mypy src/                   # strict: disallow_untyped_defs = true
```

### Tests
`pyproject.toml` declares `pytest`/`pytest-asyncio` as dev deps and the README mentions `pytest tests/`, but **no `tests/` directory exists in the repo**. There is currently no test suite to run.

## Architecture

### Entry-point chain
`run_server.py` → `src/__main__.py` (configures structlog + JSON logging to stderr) → `src.server.main()` → `GoogleAdsMCPServer.run()` over `mcp.server.stdio.stdio_server`.

`main()` searches three config locations in order: `~/.config/google-ads-mcp/config.json`, `~/.google-ads-mcp.json`, `./google-ads-config.json`. Env vars (see README) always override file values — see `auth._load_config`.

### Layered design
The server is composed of four layers, each owning one concern:

1. **`server.py` — `GoogleAdsMCPServer`**: registers MCP `list_tools`, `call_tool`, `list_resources`, `read_resource` handlers. `call_tool` always returns a single `TextContent`; results are JSON-serialized with `ProtoJSONEncoder` (handles google.protobuf objects). On `GoogleAdsException` it merges `error_handler.format_error_response` into the response.
2. **`auth.py` — `GoogleAdsAuthManager`**: dual auth (OAuth2 refresh-token *or* service account, optionally with domain-wide impersonation). The non-obvious behavior is dynamic MCC handling in `get_client(customer_id)`:
   - If a manager (`login_customer_id`) is configured *and* the queried customer differs, the gRPC `login-customer-id` header is set to the MCC.
   - If the queried customer **is** the MCC itself, the header is omitted (some accounts reject `login == queried`).
   - Clients are cached in a `TTLCache` keyed only on `(login, effective_login)` — in practice ≤ 2 cached clients.
3. **`error_handler.py` — `ErrorHandler` + `RetryableGoogleAdsClient`/`RetryableService`**: the retryable wrappers proxy `__getattr__` and auto-wrap every callable returned from `get_service(...)` with `with_retry`. `should_retry` covers `INTERNAL_ERROR`, `TRANSIENT_ERROR`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED`, `QUOTA_ERROR`, plus `httpx.TimeoutException`/`ConnectError`. Exponential backoff with 10% jitter, capped at 60s. `handle_partial_failure` parses `partial_failure_error` from mutate responses.
4. **Tools** — see below.

### Tool registry (important gotcha)
There are **two** files that look like tool implementations:

- `src/tools_complete.py` — **this is the live one.** `server.py` imports `GoogleAdsTools` from here. It composes `CampaignTools` (`tools_campaigns.py`) and `ReportingTools` (`tools_reporting.py`), and registers ~10 categories: account, campaign, ad group, ad, asset, budget, keyword, conversion action, reporting, advanced.
- `src/tools.py` — appears to be an older / partial duplicate that defines its own `GoogleAdsTools`. It is **not imported anywhere**. Do not edit `tools.py` expecting changes to take effect; edit `tools_complete.py` (or the relevant submodule) instead.

To add a tool: register it in the appropriate `_register_*_tools` method inside `tools_complete.py`, then implement the handler either in that class or in `CampaignTools`/`ReportingTools`. Tools are dispatched by `execute_tool(name, arguments)` near the bottom of `tools_complete.py`.

### Currency / GAQL conventions
- Google Ads expresses money in **micros** (1 currency unit = 1,000,000 micros). Use `currency_to_micros` / `micros_to_currency` from `utils.py` at every API boundary — never pass raw floats to mutate calls.
- GAQL queries are written as plain strings; see `_get_gaql_reference` in `server.py` for the in-tree reference exposed as the `googleads://gaql-reference` resource.

### API version
Pinned to **Google Ads API v20**. `RetryableGoogleAdsClient.get_service` defaults to `version="v20"`, and error documentation URLs are built against `/v20/errors`. When bumping versions, search for the literal `"v20"` and update both spots.

## Docker

`Dockerfile` installs the package + `mcp-proxy`, then `entrypoint.sh` runs `mcp-proxy --port 8000 --host 0.0.0.0 --allow-origin "*" --pass-environment -- python /app/run_server.py`. The entrypoint also materializes `GOOGLE_ADS_SERVICE_ACCOUNT_JSON` (raw JSON in env) to `/app/service_account.json` and points `GOOGLE_ADS_SERVICE_ACCOUNT_PATH` at it — this is how service-account creds are injected without mounting a file.
