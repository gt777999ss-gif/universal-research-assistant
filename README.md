# Universal AI-Powered Public Information Research Assistant V5 Enterprise Monitoring

FastAPI backend for public information research, deterministic analysis, and monitoring. It searches permitted public sources, filters ads/spam/duplicates, ranks relevant results, summarizes each result, groups repeated themes, identifies trends/risks/opportunities, creates daily and weekly reports, and can continuously monitor public information sources.

This is not an e-commerce recommendation system. By default it does not recommend products, suppliers, purchases, or selling strategies.

## Core Rules

- Collect only publicly available information.
- Prefer official APIs whenever available.
- Do not bypass login, CAPTCHA, rate limits, paywalls, website protections, or anti-bot systems.
- Do not collect private personal data.
- Use X/Twitter only through the official X API when `X_BEARER_TOKEN` is configured.
- Do not login-scrape TikTok. Use manual CSV imports, licensed providers, or supported public data sources only.

## V5 Enterprise Monitoring Features

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

## V5 Source Coverage

Each source has its own collector module and returns a common `SearchResult` model. If one source is unavailable or not configured, the API continues searching the remaining sources.

| Source ID | Collector | Notes |
|---|---|---|
| `google_news` | `collectors/google_news_collector.py` | Uses public Google News RSS. |
| `reddit` | `collectors/reddit_collector.py` | Uses public Reddit search JSON. |
| `youtube` | `collectors/youtube_collector.py` | Uses the official YouTube Data API when `YOUTUBE_API_KEY` is configured. |
| `x` | `collectors/x_collector.py` | Uses the official X API when `X_BEARER_TOKEN` is configured. |
| `tiktok` | `collectors/tiktok_public_collector.py` | Placeholder for public/official/licensed TikTok data only; no login scraping. |
| `web` | `collectors/web_search_collector.py` | Uses Bing Web Search when `BING_SEARCH_API_KEY` is configured. |
| `manual_csv` | `collectors/manual_csv_collector.py` | Optional public-data CSV import. |

Results are merged, filtered for spam/ads/irrelevance, deduplicated by URL and similar titles, then sorted by relevance and recency. Missing optional API keys produce warnings instead of request failures.

## Analyzer Modules

V5 analysis is deterministic and does not require OpenAI or other LLM API keys.

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
- No notification secrets are required for the placeholder framework.

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

The generated schema includes:

- Production server: `https://universal-research-assistant.onrender.com`
- `X-API-Key` header authentication for `/search`, `/analyze`, `/report`, and `/batch`
- `X-API-Key` header authentication for monitoring, report history, dashboard, and notification test endpoints
- Public `/health`, `/privacy`, and `/sources` endpoints with `security: []`

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

3. Confirm `openapi.yaml` lists the production server:

```text
https://universal-research-assistant.onrender.com
```

4. In ChatGPT, create or edit a Custom GPT.
5. Open **Configure > Actions**.
6. Choose **Create new action**.
7. Import or paste the contents of `openapi.yaml`.
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
