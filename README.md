# Universal AI-Powered Public Information Research Assistant

FastAPI backend for public information research. It searches permitted public sources, filters ads/spam/duplicates, ranks relevant results, summarizes each result, and returns clean JSON.

This is not an e-commerce recommendation system. By default it does not recommend products, suppliers, purchases, or selling strategies.

## Core Rules

- Collect only publicly available information.
- Prefer official APIs whenever available.
- Do not bypass login, CAPTCHA, rate limits, paywalls, website protections, or anti-bot systems.
- Do not collect private personal data.
- Use X/Twitter only through the official X API when `X_BEARER_TOKEN` is configured.
- Do not login-scrape TikTok. Use manual CSV imports, licensed providers, or supported public data sources only.

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

6. Test search with authentication:

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

`POST /search`

- Requires `X-API-Key`.
- Searches selected public sources.

Request:

```json
{
  "query": "natural language search request",
  "sources": ["youtube", "x", "tiktok", "reddit", "google_news", "web"],
  "days": 30,
  "limit": 50,
  "language": "any",
  "country": "any"
}
```

Response:

```json
{
  "query": "...",
  "sources": [],
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
      "reason_selected": ""
    }
  ],
  "exports": {}
}
```

Optional exports:

```json
{
  "export_csv": true,
  "export_markdown": true
}
```

Exports are written to `reports/`.

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

- Production placeholder server: `https://YOUR-DOMAIN.com`
- Local development server: `http://127.0.0.1:8000`
- `X-API-Key` header authentication for `/search`
- Public `/health` endpoint

After deploying, replace `https://YOUR-DOMAIN.com` in `openapi.yaml` with your deployed API base URL.

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
curl https://YOUR-DOMAIN.com/health
```

3. Edit `openapi.yaml` and replace:

```text
https://YOUR-DOMAIN.com
```

with your real deployed base URL.

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
