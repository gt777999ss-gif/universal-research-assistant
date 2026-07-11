# Universal AI-Powered Public Information Research Assistant V11 Automation and Notifications

FastAPI backend for public information research, deterministic reporting, optional AI-enhanced analysis, monitoring automation, alert rules, scheduler status, downloadable report exports, HTML dashboard pages, and MCP-compatible wrappers. It is useful without Gemini or OpenAI: if AI keys are missing or invalid, the system falls back to deterministic analysis and still generates reports.

This is not an e-commerce recommendation system. By default it does not recommend products, suppliers, purchases, or selling strategies.

## V11 Automation and Notifications

V11 adds persistent, non-secret scheduled jobs under `data/automation/jobs/`, execution history under `data/automation/runs/`, and deterministic change summaries under `data/automation/changes/`. Jobs run existing V10 research templates, save reports through the normal workflow path, compare each successful run with its prior successful run, and can create local alerts.

Supported schedules are `hourly`, `daily`, `weekly`, and `manual`. Jobs are disabled by default. The in-process scheduler is best-effort while the service remains awake; use `POST /automation/tick` with an external scheduler for reliable production execution. Each job/scheduled-time pair has a persistent execution key, preventing duplicate ticks from creating duplicate runs.

Protected automation APIs include `/automation/jobs`, `/automation/runs`, `/automation/tick`, daily and weekly digests, and alert acknowledgement. Public UI pages are `/ui/automation`, `/ui/automation/jobs`, `/ui/automation/runs`, and `/ui/alerts`.

Supported deterministic alert rules: `new_keyword`, `result_count_above`, `result_count_below`, `source_count_change`, `score_above`, `platform_mentioned`, `workflow_failed`, and `warning_present`.

Optional notification channels are webhook, Telegram, Discord, and SMTP email. None is required. Missing configuration produces a redacted warning and does not fail the workflow. Credentials are read only from server environment variables: `WEBHOOK_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DISCORD_WEBHOOK_URL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TO`, and `SMTP_USE_TLS`.

For Render Cron Job, GitHub Actions cron, or a local scheduler, run:

```bash
AUTOMATION_BASE_URL=https://universal-research-assistant.onrender.com \
RESEARCH_ASSISTANT_API_KEY=your-key \
python3 scripts/automation_tick.py
```

The script sends an authenticated `POST /automation/tick`. Do not commit credentials. The GPT Actions import URL remains `https://universal-research-assistant.onrender.com/openapi_gpt.json`.

## V10 Unified Research Workflows

V10 adds a local-first unified workflow API. `POST /research/run` executes these structured stages: `plan`, `search`, `collect`, `normalize`, `deduplicate`, `filter`, `rank`, `analyze`, `report`, `save`, and `export`. A workflow saves non-secret metadata in `data/workflows/` and reports under `reports/YYYY-MM-DD/`, with stable download links when `save_report` is enabled.

```json
{
  "topic": "AI video tools",
  "queries": ["Google Veo latest updates", "Runway latest updates", "Kling AI latest updates"],
  "sources": ["google_news", "youtube", "reddit", "rss", "web"],
  "days": 7,
  "limit_per_source": 20,
  "use_ai": false,
  "output_formats": ["markdown", "html", "json"],
  "save_report": true
}
```

The response records every stage, warnings, traceable result fields, deterministic analysis, report sections, and download URLs. If an optional provider fails, the workflow continues with available sources. If no public results remain after collection and filtering, it returns `status: "failed"` without fabricating a report.

Reusable templates are available through `GET /research/templates` and `POST /research/run-template`:

- `ai_video_weekly`
- `ai_news_daily`
- `youtube_channel_watch`
- `tiktok_pet_thailand`
- `competitor_monitor`
- `custom`

`ai_video_weekly` covers Google Veo, Runway, Kling AI, Seedance, Pika, HeyGen, and Luma AI. `tiktok_pet_thailand` only uses permitted public sources and never login-scrapes TikTok or generates product or supplier recommendations.

Workflow UI pages are public and never expose secrets: `GET /ui/research`, `GET /ui/workflows`, and `GET /ui/templates`.

Deterministic reports distinguish verified source facts, deterministic interpretation, and forecast/inference. AI enhancement remains optional; a missing or failed provider adds a warning and does not claim AI was used.

## Core Rules

- Collect only publicly available information.
- Prefer official APIs whenever available.
- Do not bypass login, CAPTCHA, rate limits, paywalls, website protections, or anti-bot systems.
- Do not collect private personal data.
- Use X/Twitter only through the official X API when `X_BEARER_TOKEN` is configured.
- Do not login-scrape TikTok. Use manual CSV imports, licensed providers, or supported public data sources only.

## V9 Enterprise Automation Platform Features

- Single-query and batch-query public information search.
- Source availability reporting through `GET /sources`.
- Per-source warnings when optional API keys are missing or a source fails.
- Common `SearchResult` model across collectors.
- Result `score` and `tags` fields for ranking context.
- Optional CSV and Markdown exports.
- Basic Chinese query support: original Chinese queries are preserved, and simple English search terms may be added internally when useful.
- Structured deterministic analysis through `POST /analyze`.
- Markdown research report generation through `POST /report`.
- Multi-task analysis through `POST /batch`.
- Analyzer modules for themes, trends, risks, opportunities, and report building.
- Saved monitors through `POST /monitor/create`, `GET /monitor`, `GET /monitor/{id}`, and `DELETE /monitor/{id}`.
- Manual monitor execution through `POST /monitor/run`.
- Built-in background scheduler for hourly, daily, and weekly monitors.
- Daily monitoring reports through `POST /report/daily`.
- Weekly monitoring reports through `POST /report/weekly`.
- Stored report comparison through `POST /report/compare`.
- Monitoring dashboard API through `GET /dashboard`.
- Notification framework placeholders for email, Telegram, Discord, and webhook through `POST /notify/test`.
- Report history under `reports/YYYY-MM-DD/`.
- Research planning through `POST /agent/plan`.
- Autonomous multi-step research runs through `POST /agent/run`.
- Long-term topic watches through `POST /agent/watch/create`.
- Topic change detection through `POST /agent/changes`.
- Concise research briefings through `POST /agent/briefing`.
- Deterministic agent modules under `agents/`; no external LLM API key is required.
- Optional AI provider framework under `ai_providers/`.
- Supported AI providers: Gemini, OpenAI, and fallback deterministic mode.
- AI-enhanced `/analyze`, `/report`, `/agent/run`, and `/agent/briefing` with `use_ai` and `ai_provider`.
- Enterprise report export through `POST /report/export` for Markdown, HTML, JSON, and PDF placeholder.
- Public HTML dashboard through `GET /ui`.
- Public report history API through `GET /reports` and `GET /reports/{date}`.
- Public report downloads through `/reports/download/{date}/{filename}`.
- Public dashboard pages: `/ui`, `/ui/reports`, `/ui/monitors`, and `/ui/status`.
- Deterministic reports include executive summary, top stories, trend signals, risks, opportunities, and recommended follow-up queries.
- MCP-compatible endpoints: `GET /mcp/manifest`, `POST /mcp/search`, `POST /mcp/analyze`, and `POST /mcp/briefing`.
- Webhook notification test support with `WEBHOOK_URL` when configured.
- Monitoring Center API through `GET /monitors`, `POST /monitors`, `PUT /monitors/{id}`, and `DELETE /monitors/{id}`.
- Monitor jobs can be created, edited, deleted, enabled, and disabled.
- Scheduler supports hourly, daily, and weekly frequencies.
- Monitor targets include Google News, Reddit, YouTube, RSS, and web pages when the relevant collectors are configured.
- Saved searches are stored inside monitor definitions.
- Alert rules support new keywords, trend spikes, source updates, and competitor mentions.
- Recent alerts are available through `GET /alerts`.
- Scheduler state is available through `GET /scheduler`.

## V9 Source Coverage

Each source has its own collector module and returns a common `SearchResult` model. If one source is unavailable or not configured, the API continues searching the remaining sources.

| Source ID | Collector | Notes |
|---|---|---|
| `google_news` | `collectors/google_news_collector.py` | Uses public Google News RSS. |
| `reddit` | `collectors/reddit_collector.py` | Uses public Reddit search JSON. |
| `youtube` | `collectors/youtube_collector.py` | Uses the official YouTube Data API when `YOUTUBE_API_KEY` is configured. |
| `x` | `collectors/x_collector.py` | Uses the official X API when `X_BEARER_TOKEN` is configured. |
| `tiktok` | `collectors/tiktok_public_collector.py` | Placeholder for public/official/licensed TikTok data only; no login scraping. |
| `rss` | `collectors/rss_collector.py` | Uses public RSS feed URLs. |
| `web` | `collectors/web_search_collector.py` | Uses Bing Web Search when `BING_SEARCH_API_KEY` is configured. |
| `manual_csv` | `collectors/manual_csv_collector.py` | Optional public-data CSV import. |

Results are merged, filtered for spam/ads/irrelevance, deduplicated by URL and similar titles, then sorted by relevance and recency. Missing optional API keys produce warnings instead of request failures.

## Analyzer Modules

V9 analysis and agent planning remain deterministic by default. AI enhancement is optional and only runs when `use_ai: true` and a configured provider key is available. Missing or invalid AI keys never block report generation.

```text
analyzers/
├── theme_extractor.py
├── trend_analyzer.py
├── risk_analyzer.py
├── opportunity_analyzer.py
└── report_builder.py
```

The analyzers use keyword frequency, repeated phrases, source counts, recency, engagement signals, title/summary clustering, topic importance scores, and trend scores.

## Project Structure

```text
universal-research-assistant/
├── app.py
├── openapi.yaml
├── requirements.txt
├── README.md
├── Procfile
├── render.yaml
├── .env.example
├── config/
│   └── settings.yaml
├── collectors/
├── ai_providers/
├── agents/
├── analyzers/
├── monitoring/
├── scheduler/
├── notifications/
├── processors/
└── exporters/
```

## Environment Variables

Required:

```bash
RESEARCH_ASSISTANT_API_KEY=change-me-to-a-long-random-secret
```

Optional source API keys:

```bash
YOUTUBE_API_KEY=...
X_BEARER_TOKEN=...
BING_SEARCH_API_KEY=...
```

Optional AI provider variables:

```bash
AI_PROVIDER=auto
GEMINI_API_KEY=...
OPENAI_API_KEY=...
```

`AI_PROVIDER` supports `auto`, `gemini`, `openai`, and `none`. If no AI key is configured, the API keeps deterministic analysis working and returns a warning when `use_ai` is requested.

Optional notification webhook:

```bash
WEBHOOK_URL=https://example.com/webhook
```

Enable YouTube search by creating a YouTube Data API key in Google Cloud and setting:

```bash
export YOUTUBE_API_KEY="..."
```

Enable X/Twitter search by creating an official X API bearer token and setting:

```bash
export X_BEARER_TOKEN="..."
```

Enable general web search by creating a Bing Web Search API key and setting:

```bash
export BING_SEARCH_API_KEY="..."
```

Enable Gemini AI enhancement by creating a Gemini API key and setting:

```bash
export AI_PROVIDER="gemini"
export GEMINI_API_KEY="..."
```

Enable OpenAI AI enhancement by creating an OpenAI API key and setting:

```bash
export AI_PROVIDER="openai"
export OPENAI_API_KEY="..."
```

Copy the example file locally:

```bash
cp .env.example .env
```

The app reads environment variables from the shell or deployment platform. If using `.env` locally, export the values before starting the server.

## Run Locally

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set the API key:

```bash
export RESEARCH_ASSISTANT_API_KEY="local-dev-secret"
```

4. Start the API:

```bash
python3 -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

5. Test health without authentication:

```bash
curl http://127.0.0.1:8000/health
```

6. Test source status without authentication:

```bash
curl http://127.0.0.1:8000/sources
```

7. Test search with authentication:

```bash
curl -X POST http://127.0.0.1:8000/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: local-dev-secret" \
  -d '{
    "query": "recent discussions about AI search tools",
    "sources": ["google_news", "reddit"],
    "days": 30,
    "limit": 10,
    "language": "any",
    "country": "any"
  }'
```

## API

`GET /health`

- Public endpoint.
- Does not require `X-API-Key`.

`GET /privacy`

- Public HTML privacy policy endpoint.
- Does not require `X-API-Key`.

`GET /sources`

- Public endpoint.
- Does not require `X-API-Key`.
- Returns source availability, API-key requirements, and configuration status.

`POST /search`

- Requires `X-API-Key`.
- Searches selected public sources.
- Supports `query`, `queries`, `sources`, `days`, `language`, `country`, and `limit`.
- Provide either `query` or `queries`.
- Defaults are `sources: ["google_news", "web"]`, `days: 30`, `limit: 10`, `language: "any"`, and `country: "any"`.
- Optional `include_analysis: true` adds a lightweight analysis summary to the search response.

Single-query request:

```json
{
  "query": "natural language search request",
  "sources": ["youtube", "x", "tiktok", "reddit", "google_news", "web"],
  "days": 30,
  "limit": 10,
  "language": "any",
  "country": "any"
}
```

Batch request:

```json
{
  "queries": [
    "AI video tools",
    "AI agent tools",
    "TikTok Shop Thailand pet products"
  ],
  "sources": ["google_news", "reddit", "youtube", "web"],
  "days": 30,
  "limit": 20
}
```

Response:

```json
{
  "query": "...",
  "queries": [],
  "sources": [],
  "warnings": [],
  "results": [
    {
      "source": "",
      "title": "",
      "url": "",
      "author": "",
      "date": "",
      "summary": "",
      "full_text": "",
      "image_url": "",
      "video_url": "",
      "likes": null,
      "comments": null,
      "shares": null,
      "views": null,
      "reason_selected": "",
      "score": 0,
      "tags": []
    }
  ],
  "exports": {}
}
```

Core result fields include source, title, URL, summary, published date or indexed date, image URL when available, score, and tags.

`POST /analyze`

- Requires `X-API-Key`.
- Runs the search pipeline, deduplicates results, groups themes, identifies trends/risks/opportunities, and returns structured analysis.

Example:

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H "Content-Type: application/json" \
  -H "X-API-Key: local-dev-secret" \
  -d '{
    "query": "AI video tools",
    "sources": ["google_news", "reddit", "youtube", "web"],
    "days": 30,
    "limit": 20,
    "analysis_type": "trend",
    "output_language": "auto"
  }'
```

Supported `analysis_type` values:

```text
general, trend, market, competitor, customer_feedback, risk, opportunity
```

`POST /report`

- Requires `X-API-Key`.
- Generates a Markdown research report from search and analysis results.
- If `export_markdown` is true, saves the report under `reports/YYYY-MM-DD/`.

Example:

```bash
curl -X POST http://127.0.0.1:8000/report \
  -H "Content-Type: application/json" \
  -H "X-API-Key: local-dev-secret" \
  -d '{
    "query": "AI video tools",
    "sources": ["google_news", "web"],
    "limit": 20,
    "export_markdown": true
  }'
```

`POST /batch`

- Requires `X-API-Key`.
- Runs multiple research analysis tasks in one request.

Example:

```bash
curl -X POST http://127.0.0.1:8000/batch \
  -H "Content-Type: application/json" \
  -H "X-API-Key: local-dev-secret" \
  -d '{
    "tasks": [
      {
        "query": "AI video tools",
        "analysis_type": "trend",
        "sources": ["google_news", "reddit", "youtube"],
        "days": 30,
        "limit": 20
      },
      {
        "query": "TikTok Shop Thailand pet products",
        "analysis_type": "market",
        "sources": ["google_news", "web", "reddit"],
        "days": 30,
        "limit": 20
      }
    ],
    "output_language": "auto"
  }'
```

Optional exports:

```json
{
  "export_csv": true,
  "export_markdown": true
}
```

Exports are written to `reports/`.

`POST /monitor/create`

- Requires `X-API-Key`.
- Saves a monitor definition under `data/monitors/`.
- Supported frequencies: `hourly`, `daily`, `weekly`.

Example:

```bash
curl -X POST http://127.0.0.1:8000/monitor/create \
  -H "Content-Type: application/json" \
  -H "X-API-Key: local-dev-secret" \
  -d '{
    "name": "AI Video",
    "query": "AI video tools",
    "sources": ["google_news", "reddit", "youtube", "web"],
    "analysis_type": "trend",
    "frequency": "daily",
    "days": 30,
    "limit": 50,
    "language": "auto",
    "country": "any",
    "enabled": true
  }'
```

`GET /monitor`

- Requires `X-API-Key`.
- Lists saved monitors with last run and next run metadata.

`GET /monitor/{id}`

- Requires `X-API-Key`.
- Returns one saved monitor.

`DELETE /monitor/{id}`

- Requires `X-API-Key`.
- Deletes one saved monitor.

`POST /monitor/run`

- Requires `X-API-Key`.
- Manually runs one monitor by ID or all enabled monitors.

Example:

```bash
curl -X POST http://127.0.0.1:8000/monitor/run \
  -H "Content-Type: application/json" \
  -H "X-API-Key: local-dev-secret" \
  -d '{"force": true}'
```

`GET /monitors`

- Requires `X-API-Key`.
- Lists monitor jobs for the Monitoring Center.

`POST /monitors`

- Requires `X-API-Key`.
- Creates a monitor job with saved searches and optional alert rules.

Example:

```json
{
  "name": "AI Video Monitor",
  "query": "AI video tools",
  "sources": ["google_news", "reddit", "youtube", "web"],
  "frequency": "daily",
  "enabled": true,
  "saved_searches": ["AI video tools", "Runway updates"],
  "alert_rules": {
    "new_keyword": ["launch", "funding"],
    "competitor_mentioned": ["Runway", "Pika"],
    "trend_spike": true,
    "trend_spike_threshold": 3,
    "source_updated": true
  }
}
```

`PUT /monitors/{id}`

- Requires `X-API-Key`.
- Edits a monitor job.
- Set `"enabled": false` to disable a job or `"enabled": true` to enable it.

`DELETE /monitors/{id}`

- Requires `X-API-Key`.
- Deletes a monitor job.

`GET /alerts`

- Requires `X-API-Key`.
- Lists recent alert events stored under `data/alerts/`.

`GET /scheduler`

- Requires `X-API-Key`.
- Returns scheduler running state, interval, supported frequencies, enabled monitors, due monitors, and recent scheduler warnings.

`POST /report/daily`

- Requires `X-API-Key`.
- Generates a daily Markdown and JSON monitoring report.
- Includes executive summary, top stories, emerging trends, risks, opportunities, most discussed topics, follow-up queries, and sources used.

`POST /report/weekly`

- Requires `X-API-Key`.
- Generates a weekly Markdown and JSON monitoring report.
- Includes week summary, trend changes, new topics, topics losing attention, risk changes, and opportunity changes.

`POST /report/compare`

- Requires `X-API-Key`.
- Compares stored JSON reports by date.

Example:

```json
{
  "report_a": "2026-07-01",
  "report_b": "2026-07-08"
}
```

`GET /dashboard`

- Requires `X-API-Key`.
- Returns running monitors, last run, next run, recent reports, and warnings.

`POST /notify/test`

- Requires `X-API-Key`.
- Returns placeholder status for `email`, `telegram`, `discord`, or `webhook`.
- Uses `WEBHOOK_URL` for webhook tests when configured.
- Email, Telegram, and Discord remain placeholders unless future provider credentials are added.

`POST /report/export`

- Requires `X-API-Key`.
- Generates and exports a report as `markdown`, `html`, `json`, or `pdf`.
- PDF is a placeholder when PDF dependencies are not configured.

Example:

```bash
curl -X POST http://127.0.0.1:8000/report/export \
  -H "Content-Type: application/json" \
  -H "X-API-Key: local-dev-secret" \
  -d '{
    "query": "AI video tools",
    "sources": ["google_news", "web"],
    "limit": 10,
    "format": "html",
    "use_ai": false
  }'
```

`GET /reports`

- Public endpoint.
- Lists available report dates and recent Markdown, HTML, and JSON report files.
- Each file includes a `download_url`.

`GET /reports/{date}`

- Public endpoint.
- Lists downloadable reports for one date, such as `2026-07-09`.

`GET /reports/download/{date}/{filename}`

- Public endpoint.
- Downloads a report file from `reports/YYYY-MM-DD/`.
- File names are constrained to the local reports directory.

`GET /ui`

- Public HTML dashboard.
- Shows service status, available sources, monitor list, recent reports, and documentation links.
- Does not expose API keys.

`GET /ui/reports`

- Public HTML report history browser with download links.

`GET /ui/monitors`

- Public HTML monitor overview.

`GET /ui/status`

- Public HTML service and source status page.

`GET /mcp/manifest`

- Public MCP compatibility manifest.

`POST /mcp/search`

- Requires `X-API-Key`.
- MCP-compatible wrapper around `/search`.

`POST /mcp/analyze`

- Requires `X-API-Key`.
- MCP-compatible wrapper around `/analyze`.

`POST /mcp/briefing`

- Requires `X-API-Key`.
- MCP-compatible wrapper around `/agent/briefing`.

AI-enhanced analysis fields:

```json
{
  "use_ai": true,
  "ai_provider": "auto"
}
```

These optional fields are supported by `/analyze`, `/report`, `/report/export`, `/agent/run`, and `/agent/briefing`. If the selected AI provider is missing or fails, the API returns a warning and falls back to deterministic analysis.

`POST /agent/plan`

- Requires `X-API-Key`.
- Creates a deterministic multi-step research plan from a broad goal and topic list.

Example:

```bash
curl -X POST http://127.0.0.1:8000/agent/plan \
  -H "Content-Type: application/json" \
  -H "X-API-Key: local-dev-secret" \
  -d '{
    "goal": "Monitor AI video generation tools and summarize important changes",
    "topics": ["Runway", "Google Veo", "Pika", "Kling AI", "OpenAI video"],
    "sources": ["google_news", "reddit", "youtube", "web"],
    "timeframe_days": 30,
    "output_language": "auto"
  }'
```

`POST /agent/run`

- Requires `X-API-Key`.
- Creates a plan, executes planned searches, deduplicates results, analyzes findings, and returns JSON plus Markdown briefing.

`POST /agent/watch/create`

- Requires `X-API-Key`.
- Creates one or more saved monitors internally for a long-term research goal.

Example:

```json
{
  "name": "AI Video Watch",
  "goal": "Track major AI video generation tool updates",
  "topics": ["Runway", "Google Veo", "Pika", "Kling AI", "OpenAI video"],
  "sources": ["google_news", "reddit", "youtube", "web"],
  "frequency": "daily",
  "analysis_type": "trend",
  "enabled": true
}
```

`POST /agent/changes`

- Requires `X-API-Key`.
- Compares current public information signals with prior saved reports when available.
- If no prior report exists, the current search is saved and returned as the baseline with a warning.

`POST /agent/briefing`

- Requires `X-API-Key`.
- Generates a concise deterministic briefing with top items and watch-next topics.

## Manual CSV Import

Put CSV files in:

```text
data/manual_imports/
```

Supported columns:

```text
source,title,url,author,date,summary,full_text,image_url,video_url,likes,comments,shares,views,reason_selected
```

Then include `manual_csv` in `sources`.

## Generate OpenAPI Schema

Generate YAML for ChatGPT Custom GPT Actions:

```bash
python3 scripts/export_openapi_yaml.py
```

Generate JSON if needed:

```bash
python3 scripts/export_openapi.py
```

Generate the ChatGPT Actions optimized schema:

```bash
python3 scripts/export_openapi_gpt.py
```

The generated schema includes:

- Production server: `https://universal-research-assistant.onrender.com`
- `X-API-Key` header authentication for `/search`, `/analyze`, `/report`, and `/batch`
- `X-API-Key` header authentication for monitoring, report history, dashboard, notification test, and agent endpoints
- Public `/health`, `/privacy`, and `/sources` endpoints with `security: []`

For ChatGPT Custom GPT Actions, use the optimized 23-operation schema:

```text
https://universal-research-assistant.onrender.com/openapi_gpt.json
```

The full `openapi.yaml` and `openapi.json` remain available for complete API documentation.

## Example ChatGPT Prompts

```text
Search YouTube and Google News for recent AI video tools.
```

```text
Search public information about TikTok Shop Thailand pet products.
```

```text
Search recent public discussions about pet carrier backpacks.
```

```text
Search Google News and Reddit for customer complaints about automatic pet feeders.
```

```text
Batch search these topics: AI video tools, AI agent tools, and TikTok Shop Thailand pet products.
```

```text
搜索最近关于 AI 视频工具的公开信息。
```

```text
Analyze recent customer complaints about automatic pet feeders using Google News and Reddit.
```

```text
Generate a Markdown report about TikTok Shop Thailand pet products.
```

```text
Run batch research for AI video tools and AI agent tools, then summarize trends and risks.
```

```text
Create a daily monitor for AI video tools using Google News, Reddit, YouTube, and web.
```

```text
Generate a daily monitoring report for recent AI agent tools.
```

```text
Generate a weekly report comparing public discussion trends about TikTok Shop Thailand.
```

```text
Show the monitoring dashboard.
```

```text
Plan a research workflow for tracking AI video generation tools.
```

```text
Run an autonomous research investigation on Runway, Google Veo, Pika, and Kling AI.
```

```text
Create a daily topic watch for AI video tools.
```

```text
Detect changes in public discussion about AI video tools.
```

```text
Generate a concise daily briefing on AI video tools.
```

```text
Use AI-enhanced analysis to summarize recent public information about AI video tools.
```

```text
Export an HTML enterprise report about AI search tools.
```

```text
Open the public UI dashboard.
```

```text
Use the MCP search wrapper to find recent Google News about autonomous agents.
```

```text
Show my recent research reports and download links.
```

```text
Export a deterministic HTML report about AI video tools without using AI.
```

```text
Open the reports dashboard page.
```

## Deploy To Render

1. Push this project to a GitHub repository.
2. In Render, choose **New > Web Service**.
3. Connect the repository.
4. Use these settings:

```text
Environment: Python
Build Command: pip install -r requirements.txt
Start Command: python3 -m uvicorn app:app --host 0.0.0.0 --port $PORT
```

5. Add environment variables in Render:

```text
RESEARCH_ASSISTANT_API_KEY=your-production-secret
YOUTUBE_API_KEY=optional
X_BEARER_TOKEN=optional
BING_SEARCH_API_KEY=optional
AI_PROVIDER=auto
GEMINI_API_KEY=optional
OPENAI_API_KEY=optional
WEBHOOK_URL=optional
```

6. Deploy.
7. Test:

```bash
curl https://YOUR-RENDER-DOMAIN.onrender.com/health
```

8. Update `openapi.yaml` server URL to your Render URL.

The included `render.yaml` can also be used for Render Blueprint deployment.

## Deploy To Railway

1. Push this project to a GitHub repository.
2. In Railway, choose **New Project > Deploy from GitHub repo**.
3. Select the repository.
4. Railway should detect Python automatically.
5. Set the start command:

```bash
python3 -m uvicorn app:app --host 0.0.0.0 --port $PORT
```

6. Add variables in Railway:

```text
RESEARCH_ASSISTANT_API_KEY=your-production-secret
YOUTUBE_API_KEY=optional
X_BEARER_TOKEN=optional
BING_SEARCH_API_KEY=optional
AI_PROVIDER=auto
GEMINI_API_KEY=optional
OPENAI_API_KEY=optional
WEBHOOK_URL=optional
```

7. Deploy and generate a public domain.
8. Test:

```bash
curl https://YOUR-RAILWAY-DOMAIN.up.railway.app/health
```

9. Update `openapi.yaml` server URL to your Railway URL.

## Connect To ChatGPT Custom GPT Actions

1. Deploy the API to Render, Railway, Replit, Google Cloud Run, or another public HTTPS host.
2. Confirm the public health endpoint works:

```bash
curl https://universal-research-assistant.onrender.com/health
```

3. Confirm the optimized ChatGPT Actions schema is available:

```text
https://universal-research-assistant.onrender.com/openapi_gpt.json
```

4. In ChatGPT, create or edit a Custom GPT.
5. Open **Configure > Actions**.
6. Choose **Create new action**.
7. Import from `https://universal-research-assistant.onrender.com/openapi_gpt.json`, or paste the contents of `openapi_gpt.json`.
8. Set authentication:

```text
Authentication type: API Key
Auth type: Custom
Custom header name: X-API-Key
API key: your RESEARCH_ASSISTANT_API_KEY value
```

9. Save the action.
10. Test with a prompt such as:

```text
Find recent Reddit and Google News information about AI search tools.
```

## Deployment Notes

For Render, Railway, Replit, and similar platforms, use:

```bash
python3 -m uvicorn app:app --host 0.0.0.0 --port $PORT
```

For Google Cloud Run, use:

```bash
python3 -m uvicorn app:app --host 0.0.0.0 --port 8080
```

Set API keys as environment variables in the deployment platform. Do not hardcode secrets in `openapi.yaml`, source code, or committed files.
