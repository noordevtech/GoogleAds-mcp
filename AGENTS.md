# Google Ads MCP Server — Project Guide

> **Audience**: any AI coding agent (Claude Code, Codex, Cursor, Aider, etc.) or human picking up this project. This document is the single source of truth for how the codebase is structured, what conventions every change must respect, and the recipe for adding new tools without reintroducing already-fixed bugs.
>
> A copy of this file exists at both `AGENTS.md` and `CLAUDE.md` so any tool's auto-loading convention picks it up. If you edit one, edit both.

---

## What this is

A **Model Context Protocol (MCP) server** that exposes Google Ads API v20 as a set of tools an AI agent can call. The server runs as an HTTP service (wrapped by `mcp-proxy` over the underlying stdio MCP server) and is deployed to **`gads.noordev.net`** via **Coolify** on a self-hosted VPS.

- **Origin**: forked/cloned from `https://github.com/DigitalRocket-biz/google-ads-mcp-v20.git`. The upstream was a scaffold — many tools were registered but not implemented, several had broken GAQL queries, and a handful of cross-cutting bugs blocked all child-account access. Most files in `src/` have been substantially rewritten here.
- **Repo on GitHub**: `noordevtech/GoogleAds-mcp`
- **Active development branch**: `claude/clone-google-ads-mcp-4rCX8`
- **Deployment branch**: `main` (Coolify pulls from here)
- **Production URL**: `https://gads.noordev.net/sse` (MCP SSE endpoint)

---

## Repo layout

```
.
├── Dockerfile               # python:3.11-slim + mcp-proxy on port 8000
├── entrypoint.sh            # writes service-account JSON if env-supplied, exec's mcp-proxy
├── pyproject.toml           # google-ads, mcp, structlog, etc.
├── run_server.py            # entrypoint - calls src/__main__.main()
├── config.example.json      # auth config template
└── src/
    ├── __init__.py
    ├── __main__.py          # configures logging, calls server.main()
    ├── auth.py              # GoogleAdsAuthManager - OAuth + service account; MCC login_customer_id logic
    ├── error_handler.py     # ErrorHandler.format_error_response() and retry helpers
    ├── server.py            # GoogleAdsMCPServer - MCP handlers, json.dumps via ProtoJSONEncoder
    ├── tools.py             # ⚠️ LEGACY - BROKEN, NOT WIRED UP. Has 3 working account methods only.
    ├── tools_complete.py    # ⭐ MAIN GoogleAdsTools class - composes campaign+reporting,
    │                        #    holds 49+ tool handlers, the registry, and asset/keyword/CA tools.
    ├── tools_campaigns.py   # CampaignTools class (composed into GoogleAdsTools)
    ├── tools_reporting.py   # ReportingTools class (composed) + gaql_date_filter / aliases
    └── utils.py             # micros conversion, derived_metrics, gaql_date_filter, ProtoJSONEncoder
```

**Where tools live**:
- All tool *registrations* are in `tools_complete.py` (the dict registries inside `_register_*` methods).
- Tool *handlers* are split: campaign tools in `tools_campaigns.py`, reporting tools in `tools_reporting.py`, everything else (account, ad group, ad, asset, budget, keyword, conversion-action, advanced) directly on the `GoogleAdsTools` class in `tools_complete.py`.

**Avoid `src/tools.py`**: it's the upstream scaffold's broken `GoogleAdsTools` class. `server.py` does NOT import from it. The 3 account methods in there have been moved into `tools_complete.py`. The file is left in place to minimize churn but is not on the runtime path.

---

## Critical conventions — break these and you reintroduce known bugs

Every one of these was a real production bug. Each fix has a commit. **Don't undo any of them.**

### 1. JSON Schema cleanliness — never put `required: true` inside a property

The MCP `tools/list` schema is JSON Schema Draft 2020-12. `required` belongs **only** as a root-level array of property names, **never** as a boolean inside a property definition.

The **registry** uses `"required": True` as a compact authoring shorthand:

```python
"customer_id": {"type": "string", "required": True}
```

…but `get_all_tools()` in `tools_complete.py` strips that key when emitting the schema, then computes the root-level `required: [...]` array from the same flag. **Don't bypass `get_all_tools()`** — if you build schemas elsewhere, run them through the same strip step or strict MCP clients will reject the tool with `True is not of type 'array'`.

### 2. Proto-safe JSON via `ProtoJSONEncoder`

Google Ads response objects can contain `google.protobuf.Value`, `Struct`, `ListValue`, etc. that vanilla `json.dumps` can't serialize. **Every `json.dumps` call must use `cls=ProtoJSONEncoder`** (defined in `utils.py`).

The encoder unwraps:
- `google.protobuf.Message` via `MessageToDict(preserving_proto_field_name=True)`
- proto-plus wrappers (anything with `._pb`)
- `datetime`/`date` (ISO 8601), `Decimal` (float), `bytes` (utf-8), Python enums (`.name`)

`server.py` already passes `cls=ProtoJSONEncoder` at every JSON serialization boundary. **Don't write new `json.dumps` calls without it.**

### 3. Dynamic `login_customer_id` injection for MCC

When the authenticated user is on an MCC and queries a child account, the gRPC `login-customer-id` header must be the MCC, **not** the queried child. The auth manager handles this automatically:

- `GOOGLE_ADS_LOGIN_CUSTOMER_ID` env var → `self.config["login_customer_id"]` (the MCC ID)
- `auth.get_client(customer_id)` sets `login_customer_id` on the returned client to the MCC for child queries, omits it when querying the MCC itself
- Cached by `("login", effective_login)` so at most 2 distinct cached clients exist regardless of how many children are queried

**Always call `self.auth_manager.get_client(customer_id)` to get the client** — never construct `GoogleAdsClient` directly in a handler. The handler then passes its `customer_id` to the API call separately (e.g. `service.search(customer_id=cid_clean, query=...)`).

If `GOOGLE_ADS_LOGIN_CUSTOMER_ID` is unset, the auth manager logs a startup warning and falls back to no header — direct-access accounts still work, child queries return `authorization_error.2`.

### 4. FieldMask construction

For partial updates (`update_*` tools), use `google.protobuf.field_mask_pb2.FieldMask`:

```python
from google.protobuf import field_mask_pb2

operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=update_mask))
```

**Do NOT** use `client.get_type("FieldMask")` — google-ads can't resolve `FieldMask` through `get_type()` (it lives in `google.protobuf`, not the Google Ads service proto namespace). That returns `Specified type 'FieldMask' does not exist in Google Ads API v24`.

`update_mask` should contain only the field names actually being modified — never include unspecified fields, or you'll zero them out.

### 5. GAQL date filtering via `gaql_date_filter()`

GAQL's `DURING` clause does **not** accept `ALL_TIME`. Lifetime data is implemented by *omitting* the `segments.date` filter. The helper in `utils.py` handles all three input forms:

```python
from .utils import gaql_date_filter

clause, label = gaql_date_filter(date_range)
where_parts = []
if clause:  # empty string for ALL_TIME — skip the date filter
    where_parts.append(clause)
# ... add other where conditions ...
where_str = " WHERE " + " AND ".join(where_parts) if where_parts else ""
query = f"SELECT ... FROM resource {where_str}"
```

| Input | Returned clause | Returned label |
|---|---|---|
| `"LAST_30_DAYS"` | `segments.date DURING LAST_30_DAYS` | `LAST_30_DAYS` |
| `"ALL_TIME"` (case-insensitive) | `""` (omit date filter) | `ALL_TIME` |
| `"2024-01-01,2024-12-31"` | `segments.date BETWEEN '2024-01-01' AND '2024-12-31'` | (same) |
| anything else | raises `ValueError` with a helpful message | — |

Return `date_label` in the response envelope as `"date_range"` — never the raw user input.

### 6. Keyword match type defaults to PHRASE, not BROAD

`add_keywords` and `add_negative_keywords` accept plain strings or `{text, match_type, ...}` dicts. **Plain strings now default to PHRASE** (used to be BROAD — the single largest source of wasted spend in Google Ads accounts). Use `_resolve_match_type(client, mt, default="PHRASE")` helper; it rejects `"BROAD_MATCH_MODIFIER"` (deprecated 2021) with a helpful message.

Always validate keyword text via `_validate_keyword_text()` — strips whitespace, collapses internal runs, rejects empty input and chars Google rejects (`!@%^()={}|<>`).

### 7. GAQL field-name pitfalls

These are real things the API will reject. Check before adding to a SELECT:

| Wrong | Correct |
|---|---|
| `metrics.conversion_rate` | `metrics.conversions_from_interactions_rate` |
| `metrics.conversion_value` | `metrics.conversions_value` (plural) |
| `metrics.cpc` / `metrics.cpm` | `metrics.average_cpc` / `metrics.average_cpm` |
| `metrics.average_position` | (deprecated, removed — drop it) |
| `campaign.start_date` / `campaign.end_date` in a SELECT alongside `segments.date DURING` | drop them. Use `campaign.serving_status` for lifecycle info. They're still valid for write/mutate operations — just not in this combination on reads. |

A friendly-name → real-GAQL-name map exists in `tools_reporting.py:_GAQL_METRIC_ALIASES` — extend it when you want callers to keep using a familiar name.

### 8. Derived metrics helper

`utils.derived_metrics(impressions, clicks, cost, conversions, conversions_value)` returns `{ctr, average_cpc, conversion_rate, cost_per_conversion, roas, value_per_conversion}` with `None` for ratios that would divide by zero (so consumers can distinguish "no data" from a real zero). Splat it into the metrics object on every list/perf response:

```python
"metrics": {
    "clicks": clicks,
    "impressions": impressions,
    "cost": cost,
    "conversions": conversions,
    "conversions_value": conv_value,
    "average_cpc": micros_to_currency(row.metrics.average_cpc),
    **derived_metrics(impressions, clicks, cost, conversions, conv_value),
},
```

---

## Tool registry pattern

A "tool" is a dict entry in one of the `_register_*_tools` methods on `GoogleAdsTools`:

```python
"tool_name": {
    "description": "Human-readable description shown to MCP clients.",
    "handler": self.method_or_self.helper.method,
    "parameters": {
        "customer_id": {"type": "string", "required": True},
        "optional_param": {"type": "string", "default": "FOO"},
    },
},
```

`_register_all_tools()` calls every `_register_*_tools` method and merges the dicts. To add a new category, add a `_register_xxx_tools()` method and call `tools.update(self._register_xxx_tools())` from `_register_all_tools()`.

`get_all_tools()` builds the MCP `Tool` objects (stripping the `required` shorthand into a root array — see Convention #1).

`execute_tool(name, arguments)` validates required params (using the same shorthand) and calls the handler. Handlers are async.

---

## Recipe — adding a new tool

1. **Decide where the handler lives**:
   - If it's campaign-related → method on `CampaignTools` in `tools_campaigns.py`
   - If it's reporting/GAQL → method on `ReportingTools` in `tools_reporting.py`
   - Otherwise → method directly on `GoogleAdsTools` in `tools_complete.py`

2. **Write the handler** following the canonical pattern:

```python
async def my_new_tool(
    self,
    customer_id: str,
    other_param: Optional[str] = None,
    date_range: str = "LAST_30_DAYS",
) -> Dict[str, Any]:
    """One-line description.

    Multi-line context. ``date_range`` accepts a Google Ads named range,
    'ALL_TIME', or a custom 'YYYY-MM-DD,YYYY-MM-DD' window.
    """
    # 1. Validate inputs up front, return structured errors on bad input
    try:
        date_clause, date_label = gaql_date_filter(date_range)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    try:
        # 2. Get client (auth manager handles MCC login_customer_id)
        client = self.auth_manager.get_client(customer_id)
        service = client.get_service("GoogleAdsService")

        # 3. Build query — use gaql_date_filter, never f-string user input
        where_parts = []
        if date_clause:
            where_parts.append(date_clause)
        # ... validate and add other filters ...
        where_str = " WHERE " + " AND ".join(where_parts) if where_parts else ""

        query = f"""
            SELECT ...
            FROM ...
            {where_str}
            ORDER BY ...
        """

        response = service.search(
            customer_id=customer_id.replace("-", "").strip(),  # strip hyphens
            query=query,
        )

        # 4. Manually extract fields (don't pass raw rows to json.dumps)
        items = []
        for row in response:
            items.append({
                "id": str(row.x.id),
                "metrics": {
                    "clicks": row.metrics.clicks,
                    # ... and so on, with **derived_metrics(...) if applicable
                },
            })

        # 5. Return canonical envelope
        return {
            "success": True,
            "items": items,
            "count": len(items),
            "date_range": date_label,
        }

    except GoogleAdsException as e:
        logger.error(f"Failed to my_new_tool: {e}")
        return self.error_handler.format_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in my_new_tool: {e}")
        raise
```

3. **Register it** in the appropriate `_register_*_tools` method:

```python
"my_new_tool": {
    "description": "...",
    "handler": self.my_new_tool,  # or self.helper_class.my_new_tool
    "parameters": {
        "customer_id": {"type": "string", "required": True},
        "other_param": {"type": "string"},
        "date_range": {"type": "string", "default": "LAST_30_DAYS"},
    },
},
```

4. **Compile-check**:

```bash
python3 -m py_compile src/tools_complete.py src/tools_reporting.py src/tools_campaigns.py
```

5. **Verify the tool registers cleanly** — extract the registry via AST and confirm:
   - the new entry exists,
   - the handler attribute resolves to a real method,
   - no nested `"required"` booleans in the property definitions.

   See the AST verification one-liners in past commits for templates.

6. **Commit on `claude/clone-google-ads-mcp-4rCX8`**, push, then merge to `main` (Coolify deploys from `main`).

### Patterns to NEVER use

- `client.get_type("FieldMask")` (use `field_mask_pb2.FieldMask`)
- `json.dumps(result)` without `cls=ProtoJSONEncoder`
- `customer_id` as `login_customer_id` (the auth manager already handles this)
- Plain `f"WHERE segments.date DURING {date_range}"` (use `gaql_date_filter`)
- Raw GAQL with f-string-spliced user-supplied strings (validate first; the `customer_id`/`campaign_id`/`ad_group_id` should be all-digit after stripping hyphens before splicing)
- `metrics.conversion_rate` / `campaign.start_date` in a SELECT (see GAQL pitfalls)
- `match_type = "BROAD"` as default for new keyword-related tools (use `"PHRASE"`)

---

## Authentication & environment variables

The auth manager (`src/auth.py:GoogleAdsAuthManager`) reads from `config.example.json`-style file or env vars (env wins). Required:

| Env var | Purpose |
|---|---|
| `GOOGLE_ADS_DEVELOPER_TOKEN` | **Required.** Your Google Ads developer token. |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | The MCC ID for accessing child accounts (digits only or with dashes). Without this, child-account queries fail with `authorization_error.2`. Mark as a secret in Coolify. |

OAuth path (most common):

| Env var | Purpose |
|---|---|
| `GOOGLE_ADS_CLIENT_ID` | OAuth client ID |
| `GOOGLE_ADS_CLIENT_SECRET` | OAuth client secret |
| `GOOGLE_ADS_REFRESH_TOKEN` | Long-lived refresh token |

Service account path (alternative):

| Env var | Purpose |
|---|---|
| `GOOGLE_ADS_SERVICE_ACCOUNT_JSON` | Full service-account JSON blob; `entrypoint.sh` materializes it to `/app/service_account.json` |
| `GOOGLE_ADS_IMPERSONATED_EMAIL` | Optional — impersonate a user |

Optional:

| Env var | Purpose |
|---|---|
| `GOOGLE_ADS_LINKED_CUSTOMER_ID` | When operating on a linked account |
| `GOOGLE_ADS_USE_PROTO_PLUS` | Defaults to True |

---

## Deployment (Coolify)

- **Build pack**: Dockerfile
- **Repo**: `noordevtech/GoogleAds-mcp`
- **Branch**: `main`
- **Exposed port**: `8000`
- **Healthcheck path**: `/sse` (NOT `/` — `mcp-proxy` returns 404 on root)
- **Domain**: `gads.noordev.net`

`Dockerfile` installs the project from `pyproject.toml` plus `mcp-proxy`. `entrypoint.sh` runs:

```sh
mcp-proxy --port 8000 --host 0.0.0.0 --allow-origin "*" --pass-environment -- python /app/run_server.py
```

`--pass-environment` forwards all `GOOGLE_ADS_*` env vars from the container into the Python process so `auth.py` can read them.

### Branch + merge flow

This repo follows: develop on `claude/clone-google-ads-mcp-4rCX8`, merge to `main` for deploy.

```bash
# Make changes, commit
git checkout claude/clone-google-ads-mcp-4rCX8
git commit -m "..."
git push -u origin claude/clone-google-ads-mcp-4rCX8

# Merge to main (no fast-forward to keep merge commits visible)
git checkout main
git pull origin main
git merge --no-ff claude/clone-google-ads-mcp-4rCX8 -m "Merge branch '...'"
git push origin main
```

Coolify pulls `main` on redeploy. `git push --force` is never needed.

---

## What the server can and can't do today

### Tools available (49 total at last count)

**Account**: `list_accounts`, `get_account_info`, `get_account_hierarchy`

**Campaigns**: `create_campaign`, `update_campaign`, `pause_campaign`, `resume_campaign`, `list_campaigns`, `get_campaign`

**Ad groups**: `create_ad_group`, `update_ad_group`, `list_ad_groups`

**Ads**: `create_responsive_search_ad`, `create_expanded_text_ad` (Google deprecated ETAs in 2022 — most accounts will get a policy violation), `list_ads`

**Assets**: `upload_image_asset`, `upload_text_asset`, `list_assets` (with linkage info), `create_call_asset`, `create_location_asset`, `create_sitelink_asset`, `create_callout_asset`, `create_structured_snippet_asset`, `link_asset_to_campaign` / `unlink_asset_from_campaign`, `link_asset_to_account` / `unlink_asset_from_account`

**Budgets**: `create_budget`, `update_budget`, `list_budgets`

**Keywords**: `add_keywords`, `update_keyword`, `remove_keywords`, `add_negative_keywords`, `remove_negative_keywords`, `list_keywords`

**Reporting**: `get_campaign_performance`, `get_ad_group_performance`, `get_keyword_performance`, `run_gaql_query`, `get_search_terms_report`, **`list_search_terms`** (the audit workhorse — the primary tool for finding wasted ad spend)

**Conversion actions**: `list_conversion_actions` (with summary), `get_conversion_action` (with tag_snippets), `create_conversion_action`, `update_conversion_action`

**Advanced**: `get_recommendations`, `apply_recommendation`, `get_change_history`

### Known limitations

- **`create_expanded_text_ad`**: ETAs were deprecated June 2022. The code is correct but live accounts return a policy violation. Recommend `create_responsive_search_ad` instead.
- **`apply_recommendation`**: passes only the recommendation resource_name. Recommendation types that require an additional payload (e.g., target-CPA opt-in with explicit values) will fail. Simple types (keyword/ad suggestions, callout extensions, etc.) work as-is.
- **`search_term_view` retention**: Google caps this at ~24 months regardless of `date_range="ALL_TIME"`. The docstring on `list_search_terms` notes this.
- **`get_keyword_performance` always filters `ad_group_criterion.type = 'KEYWORD'`** — that's not date-related, just resource typing. Lifetime keyword data still works with `date_range="ALL_TIME"`.

---

## Testing approach

Live calls against the Google Ads API are not possible from a local dev environment without credentials. The verification approach instead:

1. **`python3 -m py_compile`** — every file edit
2. **AST extraction** of the tool registry to confirm new entries exist and handlers resolve to real methods
3. **Helper smoke tests** — exercise validators (`gaql_date_filter`, `_validate_keyword_text`, `_resolve_match_type`, `_normalize_phone_e164`, `derived_metrics`, `ProtoJSONEncoder`) in isolation against representative inputs and edge cases
4. **Live verification by the user** after Coolify redeploy — invoke the tool from `claude.ai` against the production server with a real customer_id (the test account is `1922993180` / Corso Électrique under MCC `7347865874`)

The user reports any production error response and we trace from there.

---

## Commit map — what fixed what

Reverse chronological. Most recent commit first.

| Commit | What it did |
|---|---|
| `f39753c` | `gaql_date_filter` helper + `date_range`/`ALL_TIME`/custom support across every list/perf tool |
| `a1a4213` | Hardened keyword tools (default PHRASE, validation, update/remove tools); added 4 conversion-action tools |
| `5985209` | Fixed FieldMask (`google.protobuf` import); added 9 asset/extension tools (call/location/sitelink/callout/snippet + link/unlink) |
| `9be3ddb` | Fixed GAQL field names (`conversion_rate` → `conversions_from_interactions_rate`, drop `start_date`/`end_date`/`average_position`); added `list_search_terms` |
| `463f565` | Inject MCC as `login_customer_id` for child-account queries (Convention #3) |
| `5ec4e1a` | `ProtoJSONEncoder` + `proto_to_dict` in `utils.py`; wired into every `json.dumps` site (Convention #2) |
| `539311f` | Strip per-property `required` booleans from emitted schemas (Convention #1) |
| `20ebc67` | Implemented 21 missing tool handlers in `GoogleAdsTools` |
| `6f3539a` | `Dockerfile` + `entrypoint.sh` for Coolify (port 8000, mcp-proxy wrapping stdio) |
| `c1a4203` | Initial clone of source from `DigitalRocket-biz/google-ads-mcp-v20` |

Use `git log --oneline -20` for the live list.

---

## Quick reference for adding env vars in Coolify

Coolify dashboard → Project → Application → **Environment Variables**:

1. Add as **Production Environment Variable** (not build-time)
2. Mark sensitive values (refresh token, developer token, MCC ID) as secret
3. Save and **redeploy** — env var changes don't hot-reload
4. To verify post-deploy: hit `https://gads.noordev.net/sse` — should return a hanging `text/event-stream` connection (success). Root path returns 404 (expected — `mcp-proxy` only serves `/sse` and `/messages`).

---

## When in doubt

- Read recent commits — every fix has a detailed commit message explaining the bug and the fix
- Check the conventions in this file before introducing new patterns
- Validate user input up-front, return structured errors, never let the API reject opaquely
- Match existing response envelopes: `{"success": bool, "<entity>s": [...], "count": int, ...}` for list ops, `{"success": bool, "<resource>_resource_name": "...", ...}` for create/update/remove ops
- Don't introduce new dependencies — `google-ads`, `mcp`, `google.protobuf`, and stdlib cover everything
