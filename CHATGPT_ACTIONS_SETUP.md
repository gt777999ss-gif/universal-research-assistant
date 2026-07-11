# ChatGPT Custom GPT Actions Setup

Use this checklist to connect the Universal Public Information Research Assistant API to a ChatGPT Custom GPT Action.

## 1. Deploy The API

Deploy the FastAPI service to a public HTTPS URL, such as Render, Railway, Replit, or Google Cloud Run.

Example deployed URL:

```text
https://YOUR-DOMAIN.com
```

Confirm the service is reachable:

```bash
curl https://YOUR-DOMAIN.com/health
```

Expected response:

```json
{"status":"ok"}
```

## 2. Update `openapi.yaml`

Open `openapi.yaml` and replace:

```text
https://YOUR-DOMAIN.com
```

with your real deployed API base URL.

Example:

```text
https://your-research-assistant.onrender.com
```

## 3. Create A Custom GPT

1. Open ChatGPT.
2. Go to **Explore GPTs**.
3. Click **Create**.
4. Open the **Configure** tab.
5. Add a name, description, and instructions for your GPT.
6. Scroll to **Actions**.
7. Click **Create new action**.

## 4. Paste The OpenAPI Schema

1. In the action editor, find the schema input area.
2. Paste the full contents of `openapi.yaml`.
3. Confirm ChatGPT detects the `/search` operation.
4. Save the action.

## 5. Set Authentication

Configure authentication in the Custom GPT Action settings:

```text
Authentication type: API Key
Auth type: Custom
Custom header name: X-API-Key
```

Example API key value:

```text
test-secret-123
```

Your deployed service must use the same value in the environment variable:

```text
RESEARCH_ASSISTANT_API_KEY=test-secret-123
```

Use a long random secret for production.

## 6. Test With Curl

Replace the URL and API key with your deployed values:

```bash
curl -X POST https://YOUR-DOMAIN.com/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-secret-123" \
  -d '{
    "query": "Search Google News and Reddit for recent AI video tools",
    "sources": ["google_news", "reddit"],
    "days": 30,
    "limit": 10,
    "language": "any",
    "country": "any"
  }'
```

Expected response shape:

```json
{
  "query": "...",
  "sources": ["google_news", "reddit"],
  "results": [],
  "exports": {}
}
```

`results` may be empty if the selected sources return no relevant public results or required API keys are not configured.

## 7. Test Prompts In ChatGPT

Use these prompts after the action is connected:

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
Find recent Reddit discussions and Google News articles about AI search tools from the last 30 days.
```

```text
Search public website information and Google News for recent trends in AI-powered research assistants.
```

## 8. Recommended GPT Instructions

Add instructions like these to the Custom GPT:

```text
You are a public information research assistant. Use the connected action to search public sources when the user asks for recent public information, discussions, articles, videos, complaints, user feedback, or trends. Return concise structured summaries. Do not recommend products, suppliers, purchases, or selling strategies unless the user explicitly asks.
```

## 9. Troubleshooting

| Symptom | Meaning | Fix |
|---|---|---|
| `401 Unauthorized` | Missing or wrong API key | Confirm `X-API-Key` in ChatGPT matches `RESEARCH_ASSISTANT_API_KEY` on the server |
| `404 Not Found` | Wrong deployed URL or path | Confirm `openapi.yaml` server URL points to the deployed API base URL, not a frontend URL |
| Timeout | Service may be sleeping or a collector is slow | Open `/health` first, wait for the host to wake, then retry with fewer sources or lower `limit` |
| Empty results | Sources may be unavailable or no relevant public results were found | Try `google_news` and `reddit` first; configure `YOUTUBE_API_KEY` or `X_BEARER_TOKEN` when needed |
| ChatGPT says schema is invalid | OpenAPI file may have an old URL or formatting issue | Regenerate with `python3 scripts/export_openapi_yaml.py`, update the server URL, then paste again |
| Action works locally but not in ChatGPT | Deployed server may not be publicly reachable over HTTPS | Test with `curl https://YOUR-DOMAIN.com/health` from a separate network |

## 10. Final Checklist

- `/health` works without authentication.
- `/search` rejects requests without `X-API-Key`.
- `/search` works with the correct `X-API-Key`.
- `openapi.yaml` contains the deployed HTTPS server URL.
- ChatGPT Action authentication uses header `X-API-Key`.
- Production `RESEARCH_ASSISTANT_API_KEY` is stored only as an environment variable.
