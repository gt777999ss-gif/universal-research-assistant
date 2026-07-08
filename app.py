from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, Security, status
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, field_validator

from collectors import COLLECTORS
from exporters.csv_exporter import export_csv
from models import SearchResult
from exporters.markdown_exporter import export_markdown
from processors.dedupe import dedupe_results
from processors.filter import remove_ads_spam_irrelevant
from processors.ranker import rank_results
from processors.summarizer import summarize_results


SourceName = Literal["youtube", "x", "tiktok", "reddit", "google_news", "web", "manual_csv"]


class HealthResponse(BaseModel):
    status: str = Field(..., description="Service health status.", examples=["ok"])
    service: str = Field(..., description="Service identifier.", examples=["universal-research-assistant"])


class SearchRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Natural language public information search request.",
        examples=["Find recent Reddit discussions and Google News articles about AI search tools."],
    )
    sources: List[SourceName] = Field(
        default=["google_news", "web"],
        description="Sources to search. Defaults to Google News and general web search.",
        examples=[["google_news", "web"]],
    )
    days: int = Field(default=30, ge=1, le=365, description="Search recency window in days.")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of results to return.")
    language: str = Field(default="any", min_length=2, max_length=20, description="Language code or 'any'.")
    country: str = Field(default="any", min_length=2, max_length=20, description="Country/region code or 'any'.")
    export_csv: bool = Field(default=False, description="When true, also write a CSV report under reports/.")
    export_markdown: bool = Field(default=False, description="When true, also write a Markdown report under reports/.")

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        return " ".join(value.split())


class SearchResponse(BaseModel):
    query: str
    sources: List[str]
    results: List[SearchResult]
    exports: Dict[str, str] = Field(default_factory=dict)


settings = yaml.safe_load(open("config/settings.yaml", "r", encoding="utf-8"))
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

app = FastAPI(
    title=settings["app"]["name"],
    version=settings["app"]["version"],
    description=(
        "Universal public information research assistant. It searches permitted public sources, "
        "filters spam and duplicates, ranks relevant results, and returns clean JSON. It does not "
        "recommend products, suppliers, purchases, or sales strategies unless explicitly asked."
    ),
    servers=[
        {
            "url": "https://universal-research-assistant.onrender.com",
            "description": "Production server",
        },
    ],
)


@app.get(
    "/health",
    response_model=HealthResponse,
    operation_id="getHealth",
    summary="Check service health",
    description="Public health check endpoint. Does not require an API key.",
    openapi_extra={"security": []},
)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="universal-research-assistant")


@app.get(
    "/privacy",
    response_class=HTMLResponse,
    operation_id="getPrivacyPolicy",
    summary="Privacy policy",
    description="Public privacy policy page. Does not require an API key.",
    openapi_extra={"security": []},
)
async def privacy() -> HTMLResponse:
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Privacy Policy - Universal Research Assistant</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.6; max-width: 840px; margin: 40px auto; padding: 0 20px; color: #1f2937; }
    h1, h2 { line-height: 1.25; color: #111827; }
    a { color: #2563eb; }
  </style>
</head>
<body>
  <h1>Privacy Policy</h1>
  <p><strong>Service:</strong> Universal Research Assistant</p>
  <p>Universal Research Assistant helps users search, collect, filter, and organize public information based on user-provided queries.</p>

  <h2>Information We Process</h2>
  <p>The service processes search queries submitted by users. It may send those queries to configured public data sources or APIs, such as public news, web, video, forum, or social information providers.</p>

  <h2>Public Information Only</h2>
  <p>The service is designed to collect only publicly available information. It does not intentionally collect private personal data, bypass login systems, bypass CAPTCHA, bypass paywalls, or access protected content.</p>

  <h2>Sensitive Information</h2>
  <p>Users should not submit sensitive personal information, private credentials, financial information, medical information, or other confidential data in search queries.</p>

  <h2>API Keys And Server Configuration</h2>
  <p>API keys used to access configured third-party data sources are stored as environment variables on the server. They are not intended to be exposed in API responses or public documentation.</p>

  <h2>Contact And Owner Information</h2>
  <p>Project repository: <a href="https://github.com/gt777999ss-gif/universal-research-assistant">https://github.com/gt777999ss-gif/universal-research-assistant</a></p>
</body>
</html>"""
    return HTMLResponse(content=html)


def verify_api_key(request: Request, api_key: Optional[str] = Security(api_key_header)) -> None:
    expected = os.getenv("RESEARCH_ASSISTANT_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="RESEARCH_ASSISTANT_API_KEY is not configured.",
        )
    api_key = api_key or request.headers.get("X-Api-Key") or request.headers.get("x-api-key")
    if api_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key.")


@app.post(
    "/search",
    response_model=SearchResponse,
    operation_id="searchPublicInformation",
    summary="Search public information sources",
    description=(
        "Searches selected public sources, removes duplicate/spam/advertising results, ranks by relevance, "
        "summarizes each result, and returns clean JSON. Requires the `X-API-Key` header."
    ),
    dependencies=[Depends(verify_api_key)],
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "recent_public_discussions": {
                            "summary": "Recent public discussions",
                            "value": {
                                "query": "Find recent public discussions about AI search tools",
                                "sources": ["google_news", "web"],
                                "days": 30,
                                "limit": 10,
                                "language": "any",
                                "country": "any",
                            },
                        },
                        "youtube_videos": {
                            "summary": "Recent YouTube videos",
                            "value": {
                                "query": "Find recent YouTube videos about automatic pet feeders",
                                "sources": ["youtube"],
                                "days": 30,
                                "limit": 20,
                                "language": "en",
                                "country": "US",
                            },
                        },
                    }
                }
            }
        }
    },
)
async def search(request: SearchRequest) -> SearchResponse:
    selected_sources = request.sources or ["google_news", "web"]
    collectors = [COLLECTORS[source] for source in selected_sources if source in COLLECTORS]
    per_source_limit = max(10, min(request.limit, 100))

    batches = await asyncio.gather(
        *[
            collector(request.query, request.days, per_source_limit, request.language, request.country)
            for collector in collectors
        ],
        return_exceptions=True,
    )

    raw_results: List[Dict[str, Any]] = []
    for batch in batches:
        if isinstance(batch, Exception):
            continue
        raw_results.extend(result.model_dump() if hasattr(result, "model_dump") else result for result in batch)

    filtered = remove_ads_spam_irrelevant(raw_results, request.query)
    deduped = dedupe_results(filtered)
    ranked = rank_results(deduped, request.query)[: request.limit]
    summarized = summarize_results(ranked, settings.get("processing", {}).get("max_summary_chars", 500))

    exports: Dict[str, str] = {}
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    if request.export_csv:
        exports["csv"] = export_csv(summarized, f"reports/{timestamp}-results.csv")
    if request.export_markdown:
        exports["markdown"] = export_markdown(request.query, summarized, f"reports/{timestamp}-results.md")

    return SearchResponse(query=request.query, sources=selected_sources, results=summarized, exports=exports)
