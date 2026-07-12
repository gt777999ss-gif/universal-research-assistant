from __future__ import annotations

import asyncio
import logging
import os
from html import escape as html_escape
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, Security, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, field_validator, model_validator

from agents.briefing import build_concise_briefing
from agents.change_detector import detect_changes
from agents.planner import build_research_plan, resolve_language
from agents.runner import build_agent_briefing, recommended_next_steps
from agents.watcher import build_watch_monitors
from ai_providers.factory import run_ai_analysis
from automation.service import AutomationScheduler, PRESETS, create_job as create_automation_job, due_jobs, next_run_at, run_job as run_automation_job, update_job as update_automation_job
from automation.store import delete_job as delete_automation_job, get_job as get_automation_job, get_run as get_automation_run, list_jobs as list_automation_jobs, list_runs as list_automation_runs
from analyzers.opportunity_analyzer import analyze_opportunities
from analyzers.report_builder import (
    build_executive_summary,
    build_markdown_report,
    build_monitoring_report,
    build_weekly_report,
    save_markdown_report,
)
from analyzers.risk_analyzer import analyze_risks
from analyzers.theme_extractor import cluster_similar_stories, extract_themes, source_breakdown
from analyzers.trend_analyzer import analyze_trends
from collectors import COLLECTORS
from collectors.reddit_collector import reddit_configuration_status
from collectors.youtube_collector import youtube_configuration_status
from exporters.csv_exporter import export_csv
from exporters.report_exporter import export_report
from models import SearchResult
from monitoring.store import (
    create_monitor,
    acknowledge_alert,
    delete_monitor,
    enabled_due_monitors,
    get_monitor,
    list_alerts,
    list_report_dates,
    list_monitors,
    load_report_json,
    recent_reports,
    reports_for_date,
    save_history,
    save_report_files,
    save_alert,
    save_monitor,
    update_monitor,
    update_monitor_after_run,
)
from notifications.notifier import send_automation_notifications, send_test_notification
from exporters.markdown_exporter import export_markdown
from processors.dedupe import dedupe_results
from processors.filter import remove_ads_spam_irrelevant
from processors.ranker import rank_results
from processors.summarizer import summarize_results
from research_workflows.engine import run_workflow
from research_workflows.store import get_workflow, list_workflows
from research_workflows.templates import get_template, list_templates
from scheduler.scheduler import MonitorScheduler


SourceName = Literal["youtube", "x", "tiktok", "reddit", "google_news", "rss", "manual_csv"]
AnalysisType = Literal["general", "trend", "market", "competitor", "customer_feedback", "risk", "opportunity"]
MonitorFrequency = Literal["hourly", "daily", "weekly"]
NotificationChannel = Literal["email", "telegram", "discord", "webhook"]
AIProviderName = Literal["auto", "gemini", "openai", "none"]
ReportExportFormat = Literal["markdown", "html", "json", "pdf"]
DEFAULT_SOURCES: List[SourceName] = ["google_news"]
ALL_SOURCES: List[SourceName] = ["google_news", "reddit", "youtube", "x", "tiktok", "rss", "manual_csv"]
LOGGER = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: str = Field(..., description="Service health status.", examples=["ok"])
    service: str = Field(..., description="Service identifier.", examples=["universal-research-assistant"])


class ResearchRequest(BaseModel):
    query: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
        description="Natural language public information search request. Provide either query or queries.",
        examples=["Find recent Reddit discussions and Google News articles about AI search tools."],
    )
    queries: List[str] = Field(
        default_factory=list,
        description="Batch search queries. If provided, every query is searched and results are merged.",
        examples=[["AI video tools", "AI agent tools", "TikTok Shop Thailand pet products"]],
    )
    sources: List[SourceName] = Field(
        default=DEFAULT_SOURCES,
        description="Sources to search. Defaults to Google News.",
        examples=[["google_news", "reddit"]],
    )
    days: int = Field(default=30, ge=1, le=365, description="Search recency window in days.")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of results to return.")
    language: str = Field(default="any", min_length=2, max_length=20, description="Language code or 'any'.")
    country: str = Field(default="any", min_length=2, max_length=20, description="Country/region code or 'any'.")
    export_csv: bool = Field(default=False, description="When true, also write a CSV report under reports/.")
    export_markdown: bool = Field(default=False, description="When true, also write a Markdown report under reports/.")

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: Optional[str]) -> Optional[str]:
        return " ".join(value.split()) if value else value

    @field_validator("queries")
    @classmethod
    def normalize_queries(cls, value: List[str]) -> List[str]:
        return [" ".join(item.split()) for item in value if item and item.strip()]

    @model_validator(mode="after")
    def require_query_or_queries(self) -> "ResearchRequest":
        if not self.query and not self.queries:
            raise ValueError("Provide either query or queries.")
        return self


class SearchRequest(ResearchRequest):
    include_analysis: bool = Field(default=False, description="Include a lightweight deterministic analysis summary.")


class SearchResponse(BaseModel):
    query: str = ""
    queries: List[str] = Field(default_factory=list)
    sources: List[str]
    warnings: List[str] = Field(default_factory=list)
    results: List[SearchResult]
    exports: Dict[str, str] = Field(default_factory=dict)
    analysis: Optional[Dict[str, Any]] = None


class AnalysisRequest(ResearchRequest):
    analysis_type: AnalysisType = "general"
    output_language: str = Field(default="auto", description="auto, English, Chinese, or a language code.")
    use_ai: bool = Field(default=False, description="When true, optionally enhance deterministic analysis with a configured AI provider.")
    ai_provider: AIProviderName = Field(default="auto", description="AI provider preference: auto, gemini, openai, or none.")


class Finding(BaseModel):
    title: str
    summary: str
    supporting_sources: List[str] = Field(default_factory=list)
    confidence: str = "low"


class TrendItem(BaseModel):
    trend: str
    explanation: str
    evidence: List[str] = Field(default_factory=list)
    confidence: str = "low"


class RiskItem(BaseModel):
    risk: str
    explanation: str
    evidence: List[str] = Field(default_factory=list)


class OpportunityItem(BaseModel):
    opportunity: str
    explanation: str
    evidence: List[str] = Field(default_factory=list)


class SourceBreakdownItem(BaseModel):
    source: str
    result_count: int
    major_topics: List[str] = Field(default_factory=list)


class AnalysisResponse(BaseModel):
    query: str = ""
    queries: List[str] = Field(default_factory=list)
    analysis_type: AnalysisType
    sources: List[str]
    warnings: List[str] = Field(default_factory=list)
    executive_summary: str
    key_findings: List[Finding] = Field(default_factory=list)
    trends: List[TrendItem] = Field(default_factory=list)
    risks: List[RiskItem] = Field(default_factory=list)
    opportunities: List[OpportunityItem] = Field(default_factory=list)
    source_breakdown: List[SourceBreakdownItem] = Field(default_factory=list)
    top_results: List[SearchResult] = Field(default_factory=list)
    recommended_follow_up_queries: List[str] = Field(default_factory=list)
    markdown_report: str = ""


class ReportResponse(BaseModel):
    query: str = ""
    report_title: str
    markdown_report: str
    results_count: int
    warnings: List[str] = Field(default_factory=list)
    export_path: str = ""


class BatchTask(BaseModel):
    query: str
    analysis_type: AnalysisType = "general"
    sources: List[SourceName] = Field(default=DEFAULT_SOURCES)
    days: int = Field(default=30, ge=1, le=365)
    limit: int = Field(default=20, ge=1, le=100)
    language: str = "any"
    country: str = "any"


class BatchRequest(BaseModel):
    tasks: List[BatchTask]
    output_language: str = "auto"


class BatchTaskResponse(BaseModel):
    query: str
    analysis_type: AnalysisType
    executive_summary: str
    key_findings: List[Finding] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class BatchResponse(BaseModel):
    tasks: List[BatchTaskResponse]
    combined_markdown_report: str


class SourceStatus(BaseModel):
    name: SourceName
    available: bool
    requires_api_key: bool
    configured: bool
    note: str = ""


class SourcesResponse(BaseModel):
    sources: List[SourceStatus]


class MonitorConfig(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, examples=["AI Video"])
    query: str = Field(..., min_length=1, max_length=500, examples=["AI video tools"])
    sources: List[SourceName] = Field(default=DEFAULT_SOURCES, examples=[["google_news", "reddit", "youtube"]])
    analysis_type: AnalysisType = "trend"
    frequency: MonitorFrequency = "daily"
    days: int = Field(default=30, ge=1, le=365)
    limit: int = Field(default=50, ge=1, le=100)
    language: str = Field(default="auto", min_length=2, max_length=20)
    country: str = Field(default="any", min_length=2, max_length=20)
    enabled: bool = True
    export_csv: bool = False
    saved_searches: List[str] = Field(default_factory=list)
    alert_rules: Dict[str, Any] = Field(default_factory=dict)


class MonitorUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    query: Optional[str] = Field(default=None, min_length=1, max_length=500)
    sources: Optional[List[SourceName]] = None
    analysis_type: Optional[AnalysisType] = None
    frequency: Optional[MonitorFrequency] = None
    days: Optional[int] = Field(default=None, ge=1, le=365)
    limit: Optional[int] = Field(default=None, ge=1, le=100)
    language: Optional[str] = Field(default=None, min_length=2, max_length=20)
    country: Optional[str] = Field(default=None, min_length=2, max_length=20)
    enabled: Optional[bool] = None
    export_csv: Optional[bool] = None
    saved_searches: Optional[List[str]] = None
    alert_rules: Optional[Dict[str, Any]] = None


class Monitor(MonitorConfig):
    id: str
    created_at: str = ""
    updated_at: str = ""
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    last_status: str = "never_run"
    last_warning_count: int = 0


class MonitorListResponse(BaseModel):
    monitors: List[Monitor]


class MonitorRunRequest(BaseModel):
    id: Optional[str] = Field(default=None, description="Optional monitor ID. If omitted, all enabled due monitors are run.")
    force: bool = Field(default=True, description="When true, run selected monitor even if it is not due.")


class MonitorRunResponse(BaseModel):
    ran: int
    results: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class AlertItem(BaseModel):
    id: str = ""
    job_id: str = ""
    run_id: str = ""
    created_at: str = ""
    monitor_id: str = ""
    monitor_name: str = ""
    rule: str = ""
    message: str = ""
    severity: str = "info"
    evidence: List[str] = Field(default_factory=list)
    path: str = ""
    acknowledged: bool = False
    related_workflow_id: str = ""


class AlertsResponse(BaseModel):
    alerts: List[AlertItem] = Field(default_factory=list)


class SchedulerResponse(BaseModel):
    running: bool
    interval_seconds: int
    supported_frequencies: List[str] = Field(default_factory=list)
    enabled_monitors: int = 0
    due_monitors: int = 0
    last_warnings: List[str] = Field(default_factory=list)


class MonitoringReportResponse(BaseModel):
    report_type: str
    query: str = ""
    markdown_report: str
    json_report: Dict[str, Any]
    export_paths: Dict[str, str] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)


class CompareReportsRequest(BaseModel):
    report_a: str = Field(..., examples=["2026-07-01"])
    report_b: str = Field(..., examples=["2026-07-08"])


class CompareReportsResponse(BaseModel):
    report_a: str
    report_b: str
    new_topics: List[str] = Field(default_factory=list)
    removed_topics: List[str] = Field(default_factory=list)
    growing_trends: List[str] = Field(default_factory=list)
    declining_trends: List[str] = Field(default_factory=list)
    risk_differences: List[str] = Field(default_factory=list)
    opportunity_differences: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class NotifyTestRequest(BaseModel):
    channel: NotificationChannel
    target: str = ""
    message: str = "Universal Research Assistant notification test."


class NotifyTestResponse(BaseModel):
    channel: str
    sent: bool
    status: str
    detail: str
    target: str = ""


class DashboardResponse(BaseModel):
    running_monitors: List[Monitor]
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    recent_reports: List[Dict[str, Any]] = Field(default_factory=list)
    recent_alerts: List[Dict[str, Any]] = Field(default_factory=list)
    scheduler_status: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)


class AgentPlanRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=500)
    topics: List[str] = Field(default_factory=list)
    sources: List[SourceName] = Field(default=DEFAULT_SOURCES)
    timeframe_days: int = Field(default=30, ge=1, le=365)
    output_language: str = "auto"


class AgentPlanStep(BaseModel):
    step: int
    task: str
    query: str
    sources: List[str]
    reason: str


class AgentPlanResponse(BaseModel):
    goal: str
    research_plan: List[AgentPlanStep]
    recommended_monitors: List[Dict[str, Any]] = Field(default_factory=list)
    recommended_reports: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class AgentRunRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=500)
    topics: List[str] = Field(default_factory=list)
    sources: List[SourceName] = Field(default=DEFAULT_SOURCES)
    days: int = Field(default=30, ge=1, le=365)
    limit: int = Field(default=50, ge=1, le=100)
    analysis_type: AnalysisType = "trend"
    output_language: str = "auto"
    use_ai: bool = False
    ai_provider: AIProviderName = "auto"


class AgentRunResponse(BaseModel):
    goal: str
    plan: List[AgentPlanStep]
    executed_queries: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    executive_summary: str
    key_findings: List[Finding] = Field(default_factory=list)
    trend_changes: List[TrendItem] = Field(default_factory=list)
    risks: List[RiskItem] = Field(default_factory=list)
    opportunities: List[OpportunityItem] = Field(default_factory=list)
    recommended_next_steps: List[str] = Field(default_factory=list)
    recommended_follow_up_queries: List[str] = Field(default_factory=list)
    top_results: List[SearchResult] = Field(default_factory=list)
    markdown_briefing: str = ""


class TopicWatchCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    goal: str = Field(..., min_length=1, max_length=500)
    topics: List[str] = Field(default_factory=list)
    sources: List[SourceName] = Field(default=DEFAULT_SOURCES)
    frequency: MonitorFrequency = "daily"
    analysis_type: AnalysisType = "trend"
    enabled: bool = True


class TopicWatchCreateResponse(BaseModel):
    watch_id: str
    name: str
    created_monitors: List[Monitor] = Field(default_factory=list)
    status: str = "created"
    warnings: List[str] = Field(default_factory=list)


class AgentChangesRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    days: int = Field(default=30, ge=1, le=365)
    sources: List[SourceName] = Field(default=DEFAULT_SOURCES)


class AgentChangesResponse(BaseModel):
    topic: str
    new_topics: List[str] = Field(default_factory=list)
    growing_topics: List[str] = Field(default_factory=list)
    declining_topics: List[str] = Field(default_factory=list)
    repeated_topics: List[str] = Field(default_factory=list)
    new_risks: List[str] = Field(default_factory=list)
    new_opportunities: List[str] = Field(default_factory=list)
    summary: str
    warnings: List[str] = Field(default_factory=list)


class AgentBriefingRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=500)
    topics: List[str] = Field(default_factory=list)
    sources: List[SourceName] = Field(default=DEFAULT_SOURCES)
    days: int = Field(default=7, ge=1, le=365)
    output_language: str = "auto"
    use_ai: bool = False
    ai_provider: AIProviderName = "auto"


class AgentBriefingResponse(BaseModel):
    title: str
    date: str
    briefing: str
    top_items: List[SearchResult] = Field(default_factory=list)
    watch_next: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ReportExportRequest(AnalysisRequest):
    format: ReportExportFormat = "html"


class ReportExportResponse(BaseModel):
    format: str
    export_path: str
    download_url: str = ""
    warnings: List[str] = Field(default_factory=list)


class ReportFileItem(BaseModel):
    path: str
    date: str
    name: str
    type: str
    size_bytes: int = 0
    download_url: str = ""


class ReportsIndexResponse(BaseModel):
    dates: List[str] = Field(default_factory=list)
    recent_reports: List[ReportFileItem] = Field(default_factory=list)


class ReportsByDateResponse(BaseModel):
    date: str
    reports: List[ReportFileItem] = Field(default_factory=list)


class ReportReaderResponse(BaseModel):
    workflow_id: str
    template: str = ""
    topic: str = ""
    generated_at: str = ""
    markdown: str = ""
    html: str = ""
    json_content: Dict[str, Any] = Field(default_factory=dict, alias="json")
    download_urls: List[str] = Field(default_factory=list)


class ReportDownloadResponse(BaseModel):
    workflow_id: str
    download_urls: List[str] = Field(default_factory=list)


class MCPManifestResponse(BaseModel):
    name: str
    version: str
    description: str
    tools: List[Dict[str, Any]] = Field(default_factory=list)


class WorkflowStage(BaseModel):
    name: str
    status: str
    started_at: str
    completed_at: str
    details: str = ""
    metrics: Dict[str, Any] = Field(default_factory=dict)


class WorkflowDownload(BaseModel):
    format: str
    path: str
    download_url: str


class ResearchWorkflowRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    queries: List[str] = Field(default_factory=list)
    sources: List[SourceName] = Field(default=["google_news", "youtube", "reddit", "rss"])
    days: int = Field(default=7, ge=1, le=365)
    limit_per_source: int = Field(default=20, ge=1, le=50)
    language: str = Field(default="any", min_length=2, max_length=20)
    country: str = Field(default="any", min_length=2, max_length=20)
    use_ai: bool = False
    ai_provider: AIProviderName = "auto"
    output_formats: List[ReportExportFormat] = Field(default=["markdown", "html", "json"])
    save_report: bool = True
    output_language: str = "auto"
    template_name: str = ""

    @field_validator("queries")
    @classmethod
    def clean_workflow_queries(cls, value: List[str]) -> List[str]:
        return [" ".join(query.split()) for query in value if query and query.strip()]

    @field_validator("output_formats")
    @classmethod
    def unique_workflow_formats(cls, value: List[ReportExportFormat]) -> List[ReportExportFormat]:
        return list(dict.fromkeys(value)) or ["markdown", "html", "json"]


class ResearchWorkflowResponse(BaseModel):
    workflow_id: str
    status: str
    topic: str
    started_at: str
    completed_at: str
    stages: List[WorkflowStage] = Field(default_factory=list)
    result_count: int = 0
    warnings: List[str] = Field(default_factory=list)
    analysis: Dict[str, Any] = Field(default_factory=dict)
    report: Dict[str, Any] = Field(default_factory=dict)
    downloads: List[WorkflowDownload] = Field(default_factory=list)


class WorkflowListItem(BaseModel):
    workflow_id: str
    status: str
    topic: str
    started_at: str
    completed_at: str
    result_count: int = 0
    warnings: List[str] = Field(default_factory=list)


class WorkflowListResponse(BaseModel):
    workflows: List[WorkflowListItem] = Field(default_factory=list)


class ResearchTemplate(BaseModel):
    id: str
    name: str
    description: str
    topic: str
    queries: List[str] = Field(default_factory=list)
    sources: List[SourceName] = Field(default_factory=list)
    days: int
    limit_per_source: int
    output_formats: List[ReportExportFormat] = Field(default_factory=list)


class ResearchTemplatesResponse(BaseModel):
    templates: List[ResearchTemplate] = Field(default_factory=list)


class RunTemplateRequest(BaseModel):
    template: str = Field(
        ...,
        min_length=1,
        max_length=80,
        description="Exact template ID returned by GET /research/templates.",
        examples=["ai_video_weekly"],
    )
    overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional non-secret workflow overrides for the selected template.",
        examples=[{"days": 7, "use_ai": False}],
    )


AutomationScheduleType = Literal["hourly", "daily", "weekly", "manual"]


class AutomationJobRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    template: str = Field(..., min_length=1, max_length=80)
    enabled: bool = False
    overrides: Dict[str, Any] = Field(default_factory=dict)
    schedule_type: AutomationScheduleType = "manual"
    timezone: str = "UTC"
    hour: int = Field(default=8, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    weekday: int = Field(default=0, ge=0, le=6)
    interval_hours: int = Field(default=1, ge=1, le=168)
    notification_channels: List[NotificationChannel] = Field(default_factory=list)
    alert_rules: Dict[str, Any] = Field(default_factory=dict)


class AutomationJobUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    enabled: Optional[bool] = None
    template: Optional[str] = None
    overrides: Optional[Dict[str, Any]] = None
    schedule_type: Optional[AutomationScheduleType] = None
    timezone: Optional[str] = None
    hour: Optional[int] = Field(default=None, ge=0, le=23)
    minute: Optional[int] = Field(default=None, ge=0, le=59)
    weekday: Optional[int] = Field(default=None, ge=0, le=6)
    interval_hours: Optional[int] = Field(default=None, ge=1, le=168)
    notification_channels: Optional[List[NotificationChannel]] = None
    alert_rules: Optional[Dict[str, Any]] = None


class AutomationJob(AutomationJobRequest):
    id: str
    created_at: str
    updated_at: str
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    last_status: str = "never_run"
    last_workflow_id: str = ""


class AutomationJobsResponse(BaseModel):
    jobs: List[AutomationJob] = Field(default_factory=list)


class AutomationRun(BaseModel):
    id: str = ""
    job_id: str = ""
    job_name: str = ""
    execution_key: str = ""
    scheduled_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    status: str = ""
    workflow_id: str = ""
    result_count: int = 0
    warnings: List[str] = Field(default_factory=list)
    alerts: List[str] = Field(default_factory=list)
    change_path: str = ""
    notification_warnings: List[str] = Field(default_factory=list)


class AutomationRunsResponse(BaseModel):
    runs: List[AutomationRun] = Field(default_factory=list)


class AutomationTickResponse(BaseModel):
    mode: str
    due_job_count: int
    runs: List[AutomationRun] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class AutomationDigestRequest(BaseModel):
    send_notifications: bool = False
    notification_channels: List[NotificationChannel] = Field(default_factory=list)


class AutomationDigestResponse(BaseModel):
    period: str
    completed_jobs: int
    failed_jobs: int
    new_alerts: List[AlertItem] = Field(default_factory=list)
    top_changes: List[str] = Field(default_factory=list)
    latest_reports: List[ReportFileItem] = Field(default_factory=list)
    download_links: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class StatusResponse(BaseModel):
    success: bool
    message: str


settings = yaml.safe_load(open("config/settings.yaml", "r", encoding="utf-8"))
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
scheduler_instance: Optional[MonitorScheduler] = None
automation_scheduler_instance: Optional[AutomationScheduler] = None

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


@app.on_event("startup")
async def start_monitor_scheduler() -> None:
    global scheduler_instance, automation_scheduler_instance
    scheduler_instance = MonitorScheduler(run_monitor_job)
    LOGGER.info("YouTube startup diagnostic: %s", youtube_configuration_status()["message"])
    asyncio.create_task(scheduler_instance.loop_forever())
    automation_scheduler_instance = AutomationScheduler(automation_tick_once)
    asyncio.create_task(automation_scheduler_instance.loop_forever())


@app.on_event("shutdown")
async def stop_monitor_scheduler() -> None:
    if scheduler_instance:
        scheduler_instance.stop()
    if automation_scheduler_instance:
        automation_scheduler_instance.stop()


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


@app.get(
    "/sources",
    response_model=SourcesResponse,
    operation_id="getSources",
    summary="List source availability",
    description="Public endpoint showing which sources are configured and available.",
    openapi_extra={"security": []},
)
async def sources() -> SourcesResponse:
    return SourcesResponse(sources=[source_status(source) for source in ALL_SOURCES])


@app.get(
    "/openapi_gpt.json",
    operation_id="getGPTOptimizedOpenAPIJson",
    summary="GPT optimized OpenAPI JSON",
    description="Public ChatGPT Actions optimized OpenAPI JSON specification.",
    openapi_extra={"security": []},
)
async def openapi_gpt_json() -> FileResponse:
    path = Path("openapi_gpt.json")
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="openapi_gpt.json not found.")
    return FileResponse(path, media_type="application/json")


@app.get(
    "/openapi_gpt.yaml",
    operation_id="getGPTOptimizedOpenAPIYaml",
    summary="GPT optimized OpenAPI YAML",
    description="Public ChatGPT Actions optimized OpenAPI YAML specification.",
    openapi_extra={"security": []},
)
async def openapi_gpt_yaml() -> FileResponse:
    path = Path("openapi_gpt.yaml")
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="openapi_gpt.yaml not found.")
    return FileResponse(path, media_type="application/yaml")


@app.get(
    "/reports",
    response_model=ReportsIndexResponse,
    operation_id="listReports",
    summary="List report history",
    description="Public endpoint listing report dates and recent report files.",
    openapi_extra={"security": []},
)
async def reports_index() -> ReportsIndexResponse:
    return ReportsIndexResponse(
        dates=list_report_dates(),
        recent_reports=[ReportFileItem(**item) for item in recent_reports(50)],
    )


@app.get(
    "/reports/latest",
    response_model=ReportReaderResponse,
    operation_id="getLatestReport",
    summary="Read the latest generated workflow report",
    description="Public endpoint returning the latest saved workflow report from reports/YYYY-MM-DD/.",
    openapi_extra={"security": []},
)
async def reports_latest() -> ReportReaderResponse:
    for workflow in list_workflows(200):
        try:
            return ReportReaderResponse(**read_workflow_report(workflow))
        except FileNotFoundError:
            continue
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No saved workflow report was found.")


@app.get(
    "/reports/{workflow_id}/markdown",
    response_class=HTMLResponse,
    operation_id="getWorkflowReportMarkdown",
    summary="Read workflow report Markdown",
    description="Public endpoint returning saved Markdown report content.",
    openapi_extra={"security": []},
)
async def workflow_report_markdown(workflow_id: str) -> HTMLResponse:
    content = read_workflow_report_by_id(workflow_id)["markdown"]
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved Markdown report not found.")
    return HTMLResponse(content=content, media_type="text/markdown")


@app.get(
    "/reports/{workflow_id}/html",
    response_class=HTMLResponse,
    operation_id="getWorkflowReportHtml",
    summary="Read workflow report HTML",
    description="Public endpoint returning the saved HTML report content.",
    openapi_extra={"security": []},
)
async def workflow_report_html(workflow_id: str) -> HTMLResponse:
    content = read_workflow_report_by_id(workflow_id)["html"]
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved HTML report not found.")
    return HTMLResponse(content=content)


@app.get(
    "/reports/{workflow_id}/json",
    response_model=Dict[str, Any],
    operation_id="getWorkflowReportJson",
    summary="Read workflow report JSON",
    description="Public endpoint returning the saved JSON report content.",
    openapi_extra={"security": []},
)
async def workflow_report_json(workflow_id: str) -> Dict[str, Any]:
    payload = read_workflow_report_by_id(workflow_id)["json"]
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved JSON report not found.")
    return payload


@app.get(
    "/reports/{workflow_id}/download",
    response_model=ReportDownloadResponse,
    operation_id="getWorkflowReportDownloads",
    summary="Get workflow report download URLs",
    description="Public endpoint listing download URLs for saved report formats.",
    openapi_extra={"security": []},
)
async def workflow_report_downloads(workflow_id: str) -> ReportDownloadResponse:
    report = read_workflow_report_by_id(workflow_id)
    return ReportDownloadResponse(workflow_id=workflow_id, download_urls=report["download_urls"])


@app.get(
    "/reports/{workflow_id}",
    response_model=Union[ReportReaderResponse, ReportsByDateResponse],
    operation_id="getWorkflowReport",
    summary="Read report metadata for a workflow",
    description="Public endpoint returning saved report metadata and content for a workflow ID. Existing YYYY-MM-DD date values continue to return the legacy report-date listing.",
    openapi_extra={"security": []},
)
async def workflow_report(workflow_id: str):
    workflow = get_workflow(workflow_id)
    if workflow:
        return ReportReaderResponse(**read_workflow_report(workflow))
    if is_report_date(workflow_id):
        return ReportsByDateResponse(date=workflow_id, reports=[ReportFileItem(**item) for item in reports_for_date(workflow_id)])
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow report not found.")


@app.get(
    "/reports/download/{date}/{filename}",
    operation_id="downloadReportFile",
    summary="Download a report file",
    description="Public report download endpoint for files under reports/YYYY-MM-DD/.",
    openapi_extra={"security": []},
)
async def download_report_file(date: str, filename: str) -> FileResponse:
    if "/" in date or "/" in filename or ".." in date or ".." in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid report path.")
    path = Path("reports") / date / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report file not found.")
    return FileResponse(path)


@app.post(
    "/research/run",
    response_model=ResearchWorkflowResponse,
    operation_id="runUnifiedResearchWorkflow",
    summary="Run a unified research workflow",
    description="Plans, searches permitted public sources, deduplicates, ranks, analyzes, reports, saves, and exports one research workflow. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def research_run(request: ResearchWorkflowRequest) -> ResearchWorkflowResponse:
    result = await run_research_workflow(request)
    return ResearchWorkflowResponse(**result)


@app.get(
    "/research/workflows",
    response_model=WorkflowListResponse,
    operation_id="listResearchWorkflows",
    summary="List research workflow history",
    description="Lists locally stored research workflow metadata. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def research_workflows() -> WorkflowListResponse:
    fields = WorkflowListItem.model_fields
    return WorkflowListResponse(workflows=[WorkflowListItem(**{key: item.get(key) for key in fields}) for item in list_workflows()])


@app.get(
    "/research/workflows/{workflow_id}",
    response_model=ResearchWorkflowResponse,
    operation_id="getResearchWorkflow",
    summary="Get one research workflow",
    description="Returns a saved workflow, stage status, traceable results, report, and download links. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def research_workflow(workflow_id: str) -> ResearchWorkflowResponse:
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found.")
    return ResearchWorkflowResponse(**workflow)


@app.post(
    "/research/workflows/{workflow_id}/retry",
    response_model=ResearchWorkflowResponse,
    operation_id="retryResearchWorkflow",
    summary="Retry a saved research workflow",
    description="Runs a new workflow using the saved non-secret request parameters. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def retry_research_workflow(workflow_id: str) -> ResearchWorkflowResponse:
    workflow = get_workflow(workflow_id)
    if not workflow or not workflow.get("request"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow request was not found.")
    return ResearchWorkflowResponse(**await run_research_workflow(ResearchWorkflowRequest(**workflow["request"])))


@app.get(
    "/research/templates",
    response_model=ResearchTemplatesResponse,
    operation_id="listResearchTemplates",
    summary="List the actual research templates available in this deployment",
    description=(
        "This endpoint is the authoritative source of available template IDs. Always call this endpoint before "
        "claiming that a requested template does not exist. Do not infer or invent template names from memory. "
        "Requires the X-API-Key header."
    ),
    dependencies=[Depends(verify_api_key)],
    openapi_extra={
        "responses": {
            "200": {
                "description": "Authoritative template registry response.",
                "content": {"application/json": {"example": {"templates": [{"id": "ai_video_weekly", "name": "AI Video Weekly"}]}}},
            }
        }
    },
)
async def research_templates() -> ResearchTemplatesResponse:
    return ResearchTemplatesResponse(templates=[ResearchTemplate(**item) for item in list_templates()])


@app.post(
    "/research/run-template",
    response_model=ResearchWorkflowResponse,
    operation_id="runResearchTemplate",
    summary="Run an existing research template by exact template ID",
    description=(
        "Call listResearchTemplates first when availability is unknown. If the exact ID appears, run it immediately. "
        "For ai_video_weekly send {\"template\":\"ai_video_weekly\"}. Do not request confirmation when explicitly asked. "
        "Requires the X-API-Key header."
    ),
    dependencies=[Depends(verify_api_key)],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"example": {"template": "ai_video_weekly"}}},
        },
        "responses": {
            "200": {
                "description": "Workflow started from the exact template ID.",
                "content": {
                    "application/json": {
                        "example": {
                            "workflow_id": "3f9fbfd9-9d16-4ec5-9c1f-4b8565956c00",
                            "status": "completed",
                            "topic": "AI video tools weekly developments",
                            "started_at": "2026-07-11T00:00:00Z",
                            "completed_at": "2026-07-11T00:00:05Z",
                        }
                    }
                },
            }
        },
    },
)
async def research_run_template(request: RunTemplateRequest) -> ResearchWorkflowResponse:
    try:
        payload = get_template(request.template)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research template not found.")
    allowed = set(ResearchWorkflowRequest.model_fields)
    payload.update({key: value for key, value in request.overrides.items() if key in allowed})
    payload["template_name"] = request.template
    return ResearchWorkflowResponse(**await run_research_workflow(ResearchWorkflowRequest(**payload)))


@app.get("/automation/jobs", response_model=AutomationJobsResponse, operation_id="listAutomationJobs", dependencies=[Depends(verify_api_key)])
async def automation_jobs() -> AutomationJobsResponse:
    return AutomationJobsResponse(jobs=[AutomationJob(**item) for item in list_automation_jobs()])


@app.post("/automation/jobs", response_model=AutomationJob, operation_id="createAutomationJob", dependencies=[Depends(verify_api_key)])
async def automation_create_job(request: AutomationJobRequest) -> AutomationJob:
    if request.template not in {item["id"] for item in list_templates()}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research template not found.")
    return AutomationJob(**create_automation_job(request.model_dump()))


@app.get("/automation/jobs/{job_id}", response_model=AutomationJob, operation_id="getAutomationJob", dependencies=[Depends(verify_api_key)])
async def automation_get_job(job_id: str) -> AutomationJob:
    job = get_automation_job(job_id)
    if not job: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation job not found.")
    return AutomationJob(**job)


@app.put("/automation/jobs/{job_id}", response_model=AutomationJob, operation_id="updateAutomationJob", dependencies=[Depends(verify_api_key)])
async def automation_update_job(job_id: str, request: AutomationJobUpdate) -> AutomationJob:
    updates = request.model_dump(exclude_unset=True)
    if "template" in updates and updates["template"] not in {item["id"] for item in list_templates()}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research template not found.")
    job = update_automation_job(job_id, updates)
    if not job: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation job not found.")
    return AutomationJob(**job)


@app.delete("/automation/jobs/{job_id}", response_model=StatusResponse, operation_id="deleteAutomationJob", dependencies=[Depends(verify_api_key)])
async def automation_delete_job(job_id: str) -> StatusResponse:
    if not delete_automation_job(job_id): raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation job not found.")
    return StatusResponse(success=True, message="Automation job deleted.")


@app.post("/automation/jobs/{job_id}/run", response_model=AutomationRun, operation_id="runAutomationJob", dependencies=[Depends(verify_api_key)])
async def automation_run_job(job_id: str) -> AutomationRun:
    job = get_automation_job(job_id)
    if not job: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation job not found.")
    return AutomationRun(**await execute_automation_job(job, scheduled_at=f"manual:{datetime.utcnow().isoformat()}"))


@app.post("/automation/jobs/{job_id}/enable", response_model=AutomationJob, operation_id="enableAutomationJob", dependencies=[Depends(verify_api_key)])
async def automation_enable_job(job_id: str) -> AutomationJob:
    job = update_automation_job(job_id, {"enabled": True})
    if not job: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation job not found.")
    return AutomationJob(**job)


@app.post("/automation/jobs/{job_id}/disable", response_model=AutomationJob, operation_id="disableAutomationJob", dependencies=[Depends(verify_api_key)])
async def automation_disable_job(job_id: str) -> AutomationJob:
    job = update_automation_job(job_id, {"enabled": False})
    if not job: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation job not found.")
    return AutomationJob(**job)


@app.get("/automation/runs", response_model=AutomationRunsResponse, operation_id="listAutomationRuns", dependencies=[Depends(verify_api_key)])
async def automation_runs() -> AutomationRunsResponse:
    return AutomationRunsResponse(runs=[AutomationRun(**item) for item in list_automation_runs()])


@app.get("/automation/runs/{run_id}", response_model=AutomationRun, operation_id="getAutomationRun", dependencies=[Depends(verify_api_key)])
async def automation_get_run(run_id: str) -> AutomationRun:
    run = get_automation_run(run_id)
    if not run: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation run not found.")
    return AutomationRun(**run)


@app.post("/automation/tick", response_model=AutomationTickResponse, operation_id="tickAutomation", dependencies=[Depends(verify_api_key)])
async def automation_tick() -> AutomationTickResponse:
    runs = await automation_tick_once()
    return AutomationTickResponse(mode="external_trigger", due_job_count=len(runs), runs=[AutomationRun(**item) for item in runs])


@app.post("/automation/digest/daily", response_model=AutomationDigestResponse, operation_id="generateDailyAutomationDigest", dependencies=[Depends(verify_api_key)])
async def automation_daily_digest(request: AutomationDigestRequest) -> AutomationDigestResponse:
    return await build_automation_digest("daily", request)


@app.post("/automation/digest/weekly", response_model=AutomationDigestResponse, operation_id="generateWeeklyAutomationDigest", dependencies=[Depends(verify_api_key)])
async def automation_weekly_digest(request: AutomationDigestRequest) -> AutomationDigestResponse:
    return await build_automation_digest("weekly", request)


@app.post("/alerts/{alert_id}/acknowledge", response_model=AlertItem, operation_id="acknowledgeAlert", dependencies=[Depends(verify_api_key)])
async def alerts_acknowledge(alert_id: str) -> AlertItem:
    alert = acknowledge_alert(alert_id)
    if not alert: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found.")
    return AlertItem(**alert)


@app.get(
    "/ui",
    response_class=HTMLResponse,
    operation_id="getUIDashboard",
    summary="Simple public UI dashboard",
    description="Public HTML dashboard showing service status, source status, monitor summaries, recent reports, and documentation links.",
    openapi_extra={"security": []},
)
async def ui_dashboard() -> HTMLResponse:
    return HTMLResponse(build_ui_page("Dashboard", dashboard_sections()))


@app.get(
    "/ui/reports",
    response_class=HTMLResponse,
    operation_id="getUIReports",
    summary="Report history browser",
    description="Public HTML page for browsing local report history.",
    openapi_extra={"security": []},
)
async def ui_reports() -> HTMLResponse:
    return HTMLResponse(build_ui_page("Reports", reports_sections()))


@app.get(
    "/ui/monitors",
    response_class=HTMLResponse,
    operation_id="getUIMonitors",
    summary="Monitor browser",
    description="Public HTML page listing saved monitor definitions without exposing API keys.",
    openapi_extra={"security": []},
)
async def ui_monitors() -> HTMLResponse:
    return HTMLResponse(build_ui_page("Monitors", monitors_sections()))


@app.get(
    "/ui/status",
    response_class=HTMLResponse,
    operation_id="getUIStatus",
    summary="Status page",
    description="Public HTML page showing service and source status.",
    openapi_extra={"security": []},
)
async def ui_status() -> HTMLResponse:
    return HTMLResponse(build_ui_page("Status", status_sections()))


@app.get(
    "/ui/research",
    response_class=HTMLResponse,
    operation_id="getUIResearch",
    summary="Research workflow dashboard",
    description="Public HTML page showing workflow capabilities and saved report links.",
    openapi_extra={"security": []},
)
async def ui_research() -> HTMLResponse:
    return HTMLResponse(build_ui_page("Research", research_sections()))


@app.get(
    "/ui/workflows",
    response_class=HTMLResponse,
    operation_id="getUIWorkflows",
    summary="Research workflow history browser",
    description="Public HTML page showing recent saved workflow status without exposing secrets.",
    openapi_extra={"security": []},
)
async def ui_workflows() -> HTMLResponse:
    return HTMLResponse(build_ui_page("Workflows", workflow_sections()))


@app.get(
    "/ui/templates",
    response_class=HTMLResponse,
    operation_id="getUITemplates",
    summary="Research templates browser",
    description="Public HTML page listing reusable public-information workflow templates.",
    openapi_extra={"security": []},
)
async def ui_templates() -> HTMLResponse:
    return HTMLResponse(build_ui_page("Research Templates", template_sections()))


@app.get("/ui/automation", response_class=HTMLResponse, operation_id="getUIAutomation", openapi_extra={"security": []})
async def ui_automation() -> HTMLResponse:
    return HTMLResponse(build_ui_page("Automation", automation_sections()))


@app.get("/ui/automation/jobs", response_class=HTMLResponse, operation_id="getUIAutomationJobs", openapi_extra={"security": []})
async def ui_automation_jobs() -> HTMLResponse:
    return HTMLResponse(build_ui_page("Automation Jobs", [automation_job_table(list_automation_jobs(), "Scheduled Jobs")]))


@app.get("/ui/automation/runs", response_class=HTMLResponse, operation_id="getUIAutomationRuns", openapi_extra={"security": []})
async def ui_automation_runs() -> HTMLResponse:
    return HTMLResponse(build_ui_page("Automation Runs", [automation_run_table(list_automation_runs(), "Recent Executions")]))


@app.get("/ui/alerts", response_class=HTMLResponse, operation_id="getUIAlertBrowser", openapi_extra={"security": []})
async def ui_alerts() -> HTMLResponse:
    return HTMLResponse(build_ui_page("Alerts", [alert_table(list_alerts(100), "Recent Alerts")]))


@app.get("/ui/report/{workflow_id}", response_class=HTMLResponse, operation_id="getUIWorkflowReport", openapi_extra={"security": []})
async def ui_workflow_report(workflow_id: str) -> HTMLResponse:
    report = read_workflow_report_by_id(workflow_id)
    links = "".join(f"<a class='button' href='{url}'>Download</a>" for url in report["download_urls"])
    content = f"<section><h2>{html_escape(report['topic'])}</h2><p class='muted'>Generated: {html_escape(report['generated_at'])}</p><p>{links}</p><pre>{html_escape(report['markdown'])}</pre></section>"
    return HTMLResponse(build_ui_page("Report", [content]))


@app.get(
    "/mcp/manifest",
    response_model=MCPManifestResponse,
    operation_id="getMCPManifest",
    summary="MCP compatibility manifest",
    description="Public manifest describing MCP-compatible wrapper endpoints.",
    openapi_extra={"security": []},
)
async def mcp_manifest() -> MCPManifestResponse:
    return MCPManifestResponse(
        name="Universal Research Assistant",
        version=settings["app"]["version"],
        description="MCP-compatible wrappers for public information search, analysis, and briefing.",
        tools=[
            {"name": "mcpSearch", "path": "/mcp/search", "method": "POST"},
            {"name": "mcpAnalyze", "path": "/mcp/analyze", "method": "POST"},
            {"name": "mcpBriefing", "path": "/mcp/briefing", "method": "POST"},
        ],
    )


@app.get(
    "/monitors",
    response_model=MonitorListResponse,
    operation_id="listEnterpriseMonitors",
    summary="List monitor jobs",
    description="Lists saved monitor jobs for the monitoring center. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def monitors_list() -> MonitorListResponse:
    return MonitorListResponse(monitors=[Monitor(**item) for item in list_monitors()])


@app.post(
    "/monitors",
    response_model=Monitor,
    operation_id="createEnterpriseMonitor",
    summary="Create a monitor job",
    description="Creates a saved monitor job with optional saved searches and alert rules. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def monitors_create(config: MonitorConfig) -> Monitor:
    payload = config.model_dump()
    if not payload.get("saved_searches"):
        payload["saved_searches"] = [config.query]
    return Monitor(**create_monitor(payload))


@app.put(
    "/monitors/{id}",
    response_model=Monitor,
    operation_id="updateEnterpriseMonitor",
    summary="Edit, enable, or disable a monitor job",
    description="Updates monitor configuration. Set enabled true or false to enable/disable jobs. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def monitors_update(id: str, update: MonitorUpdate) -> Monitor:
    monitor = update_monitor(id, update.model_dump(exclude_unset=True))
    if not monitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found.")
    return Monitor(**monitor)


@app.delete(
    "/monitors/{id}",
    response_model=Dict[str, bool],
    operation_id="deleteEnterpriseMonitor",
    summary="Delete a monitor job",
    description="Deletes one monitor job. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def monitors_delete(id: str) -> Dict[str, bool]:
    deleted = delete_monitor(id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found.")
    return {"deleted": True}


@app.post(
    "/monitor/create",
    response_model=Monitor,
    operation_id="createMonitor",
    summary="Create a public information monitor",
    description="Creates a saved monitor definition under data/monitors/. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def monitor_create(config: MonitorConfig) -> Monitor:
    return Monitor(**create_monitor(config.model_dump()))


@app.get(
    "/monitor",
    response_model=MonitorListResponse,
    operation_id="listMonitors",
    summary="List monitors",
    description="Lists saved monitor definitions. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def monitor_list() -> MonitorListResponse:
    return MonitorListResponse(monitors=[Monitor(**item) for item in list_monitors()])


@app.get(
    "/monitor/{id}",
    response_model=Monitor,
    operation_id="getMonitor",
    summary="Get a monitor",
    description="Returns one saved monitor definition. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def monitor_get(id: str) -> Monitor:
    monitor = get_monitor(id)
    if not monitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found.")
    return Monitor(**monitor)


@app.delete(
    "/monitor/{id}",
    response_model=Dict[str, bool],
    operation_id="deleteMonitor",
    summary="Delete a monitor",
    description="Deletes one saved monitor definition. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def monitor_delete(id: str) -> Dict[str, bool]:
    deleted = delete_monitor(id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found.")
    return {"deleted": True}


@app.post(
    "/monitor/run",
    response_model=MonitorRunResponse,
    operation_id="runMonitors",
    summary="Run monitors manually",
    description="Runs one monitor by ID or all due enabled monitors. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def monitor_run(request: MonitorRunRequest = MonitorRunRequest()) -> MonitorRunResponse:
    warnings: List[str] = []
    if request.id:
        monitor = get_monitor(request.id)
        if not monitor:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found.")
        outputs = [await run_monitor_job(monitor)]
    elif request.force:
        outputs = [await run_monitor_job(monitor) for monitor in list_monitors() if monitor.get("enabled", True)]
    else:
        outputs = await scheduler_instance.run_due_once() if scheduler_instance else []
    if scheduler_instance:
        warnings.extend(scheduler_instance.last_warnings)
    return MonitorRunResponse(ran=len(outputs), results=outputs, warnings=unique_strings(warnings))


@app.get(
    "/alerts",
    response_model=AlertsResponse,
    operation_id="listAlerts",
    summary="List recent alerts",
    description="Lists locally stored alert events. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def alerts() -> AlertsResponse:
    return AlertsResponse(alerts=[AlertItem(**item) for item in list_alerts()])


@app.get(
    "/scheduler",
    response_model=SchedulerResponse,
    operation_id="getSchedulerStatus",
    summary="Get scheduler status",
    description="Returns in-process scheduler status and supported frequencies. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def scheduler_status() -> SchedulerResponse:
    return SchedulerResponse(**scheduler_status_payload())


@app.get(
    "/dashboard",
    response_model=DashboardResponse,
    operation_id="getMonitoringDashboard",
    summary="Get monitoring dashboard data",
    description="Returns monitor status, recent reports, and warnings. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def dashboard() -> DashboardResponse:
    monitors = [Monitor(**item) for item in list_monitors()]
    last_run = max((item.last_run for item in monitors if item.last_run), default=None)
    next_run = min((item.next_run for item in monitors if item.next_run), default=None)
    warnings = source_warnings(unique_source_names([source for monitor in monitors for source in monitor.sources]))
    if scheduler_instance:
        warnings.extend(scheduler_instance.last_warnings[-10:])
    return DashboardResponse(
        running_monitors=[monitor for monitor in monitors if monitor.enabled],
        last_run=last_run,
        next_run=next_run,
        recent_reports=recent_reports(),
        recent_alerts=list_alerts(10),
        scheduler_status=scheduler_status_payload(),
        warnings=unique_strings(warnings),
    )


@app.post(
    "/agent/plan",
    response_model=AgentPlanResponse,
    operation_id="planResearchAgent",
    summary="Plan an autonomous research task",
    description="Creates deterministic multi-step public information research plans from a broad goal. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def agent_plan(request: AgentPlanRequest) -> AgentPlanResponse:
    plan = build_research_plan(request.goal, request.topics, request.sources, request.timeframe_days, request.output_language)
    warnings = source_warnings(request.sources)
    return AgentPlanResponse(**{**plan, "warnings": unique_strings(plan.get("warnings", []) + warnings)})


@app.post(
    "/agent/run",
    response_model=AgentRunResponse,
    operation_id="runResearchAgent",
    summary="Run an autonomous research investigation",
    description="Plans, searches, deduplicates, analyzes, and returns a deterministic research briefing. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def agent_run(request: AgentRunRequest) -> AgentRunResponse:
    language = resolve_language(request.goal, request.topics, request.output_language)
    plan_payload = build_research_plan(request.goal, request.topics, request.sources, request.days, request.output_language)
    plan_steps = plan_payload["research_plan"]
    executed_queries = [step["query"] for step in plan_steps]
    analysis_request = AnalysisRequest(
        queries=executed_queries,
        sources=request.sources,
        days=request.days,
        limit=request.limit,
        language="any",
        country="any",
        analysis_type=request.analysis_type,
        output_language=language,
        use_ai=request.use_ai,
        ai_provider=request.ai_provider,
    )
    pipeline = await run_search_pipeline(analysis_request)
    analysis = build_analysis_response(analysis_request, pipeline)
    analysis = await maybe_enhance_analysis(analysis, analysis_request, pipeline)
    analysis_dict = analysis.model_dump()
    markdown = build_agent_briefing(request.goal, plan_steps, executed_queries, analysis_dict, language)
    return AgentRunResponse(
        goal=request.goal,
        plan=[AgentPlanStep(**step) for step in plan_steps],
        executed_queries=executed_queries,
        warnings=unique_strings(plan_payload.get("warnings", []) + analysis.warnings),
        executive_summary=analysis.executive_summary,
        key_findings=analysis.key_findings,
        trend_changes=analysis.trends,
        risks=analysis.risks,
        opportunities=analysis.opportunities,
        recommended_next_steps=recommended_next_steps(request.goal, language),
        recommended_follow_up_queries=analysis.recommended_follow_up_queries,
        top_results=analysis.top_results,
        markdown_briefing=markdown,
    )


@app.post(
    "/agent/watch/create",
    response_model=TopicWatchCreateResponse,
    operation_id="createTopicWatch",
    summary="Create a long-term topic watch",
    description="Creates one or more monitor definitions for a long-term research goal. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def agent_watch_create(request: TopicWatchCreateRequest) -> TopicWatchCreateResponse:
    watch = build_watch_monitors(
        request.name,
        request.goal,
        request.topics,
        request.sources,
        request.frequency,
        request.analysis_type,
        request.enabled,
    )
    created = [Monitor(**create_monitor(payload)) for payload in watch["monitor_payloads"]]
    return TopicWatchCreateResponse(
        watch_id=watch["watch_id"],
        name=request.name,
        created_monitors=created,
        status="created",
        warnings=source_warnings(request.sources),
    )


@app.post(
    "/agent/changes",
    response_model=AgentChangesResponse,
    operation_id="detectTopicChanges",
    summary="Detect topic changes",
    description="Compares current public information signals against prior saved reports when available. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def agent_changes(request: AgentChangesRequest) -> AgentChangesResponse:
    analysis_request = AnalysisRequest(
        query=request.topic,
        sources=request.sources,
        days=request.days,
        limit=50,
        language="any",
        country="any",
        analysis_type="trend",
        output_language="auto",
    )
    current = await build_period_report(analysis_request, "daily", monitor_name=f"changes-{request.topic}")
    prior = latest_report_before_today()
    warnings = list(current.warnings)
    if not prior:
        warnings.append("No prior saved report was found; current search results are being used as the baseline.")
        prior = {}
    changes = detect_changes(current.json_report, prior)
    summary = build_change_summary(request.topic, changes, bool(prior))
    return AgentChangesResponse(topic=request.topic, summary=summary, warnings=unique_strings(warnings), **changes)


@app.post(
    "/agent/briefing",
    response_model=AgentBriefingResponse,
    operation_id="generateAgentBriefing",
    summary="Generate an autonomous research briefing",
    description="Runs a deterministic public information research briefing for a goal and topics. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def agent_briefing(request: AgentBriefingRequest) -> AgentBriefingResponse:
    language = resolve_language(request.goal, request.topics, request.output_language)
    queries = [request.goal] + [f"{topic} recent developments updates" for topic in request.topics]
    analysis_request = AnalysisRequest(
        queries=queries,
        sources=request.sources,
        days=request.days,
        limit=25,
        language="any",
        country="any",
        analysis_type="trend",
        output_language=language,
        use_ai=request.use_ai,
        ai_provider=request.ai_provider,
    )
    pipeline = await run_search_pipeline(analysis_request)
    analysis = build_analysis_response(analysis_request, pipeline)
    analysis = await maybe_enhance_analysis(analysis, analysis_request, pipeline)
    briefing = build_concise_briefing(request.goal, request.topics, analysis.model_dump(), language)
    return AgentBriefingResponse(
        title=briefing["title"],
        date=briefing["date"],
        briefing=briefing["briefing"],
        top_items=[SearchResult(**item) if isinstance(item, dict) else item for item in briefing["top_items"]],
        watch_next=briefing["watch_next"],
        warnings=analysis.warnings,
    )


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
                                "sources": ["google_news", "reddit"],
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
    pipeline = await run_search_pipeline(request)
    exports: Dict[str, str] = {}
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    if request.export_csv:
        exports["csv"] = export_csv(pipeline["results"], f"reports/{timestamp}-results.csv")
    if request.export_markdown:
        exports["markdown"] = export_markdown(", ".join(pipeline["original_queries"]), pipeline["results"], f"reports/{timestamp}-results.md")

    return SearchResponse(
        query=request.query or "",
        queries=request.queries,
        sources=pipeline["sources"],
        warnings=pipeline["warnings"],
        results=pipeline["results"],
        exports=exports,
        analysis=lightweight_analysis(pipeline) if request.include_analysis else None,
    )


@app.post(
    "/analyze",
    response_model=AnalysisResponse,
    operation_id="analyzePublicInformation",
    summary="Analyze public information",
    description="Runs the public information search pipeline and returns a deterministic structured analysis report.",
    dependencies=[Depends(verify_api_key)],
)
async def analyze(request: AnalysisRequest) -> AnalysisResponse:
    pipeline = await run_search_pipeline(request)
    analysis = build_analysis_response(request, pipeline)
    return await maybe_enhance_analysis(analysis, request, pipeline)


@app.post(
    "/report",
    response_model=ReportResponse,
    operation_id="generateResearchReport",
    summary="Generate a Markdown research report",
    description="Runs public information search and deterministic analysis, then returns a Markdown report.",
    dependencies=[Depends(verify_api_key)],
)
async def report(request: AnalysisRequest) -> ReportResponse:
    pipeline = await run_search_pipeline(request)
    analysis = build_analysis_response(request, pipeline)
    analysis = await maybe_enhance_analysis(analysis, request, pipeline)
    export_path = save_markdown_report(analysis.markdown_report) if request.export_markdown else ""
    query_label = query_label_from_request(request)
    return ReportResponse(
        query=query_label,
        report_title=f"Research Report: {query_label}",
        markdown_report=analysis.markdown_report,
        results_count=len(analysis.top_results),
        warnings=analysis.warnings,
        export_path=export_path,
    )


@app.post(
    "/report/export",
    response_model=ReportExportResponse,
    operation_id="exportResearchReport",
    summary="Export an enterprise research report",
    description="Generates and exports a research report as Markdown, HTML, JSON, or PDF placeholder. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def report_export(request: ReportExportRequest) -> ReportExportResponse:
    pipeline = await run_search_pipeline(request)
    analysis = build_analysis_response(request, pipeline)
    analysis = await maybe_enhance_analysis(analysis, request, pipeline)
    payload = analysis.model_dump()
    export = export_report(analysis.markdown_report, payload, request.format)
    export["warnings"] = unique_strings(export.get("warnings", []) + analysis.warnings)
    return ReportExportResponse(**export)


@app.post(
    "/mcp/search",
    response_model=SearchResponse,
    operation_id="mcpSearch",
    summary="MCP search wrapper",
    description="MCP-compatible wrapper around /search. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def mcp_search(request: SearchRequest) -> SearchResponse:
    return await search(request)


@app.post(
    "/mcp/analyze",
    response_model=AnalysisResponse,
    operation_id="mcpAnalyze",
    summary="MCP analyze wrapper",
    description="MCP-compatible wrapper around /analyze. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def mcp_analyze(request: AnalysisRequest) -> AnalysisResponse:
    return await analyze(request)


@app.post(
    "/mcp/briefing",
    response_model=AgentBriefingResponse,
    operation_id="mcpBriefing",
    summary="MCP briefing wrapper",
    description="MCP-compatible wrapper around /agent/briefing. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def mcp_briefing(request: AgentBriefingRequest) -> AgentBriefingResponse:
    return await agent_briefing(request)


@app.post(
    "/report/daily",
    response_model=MonitoringReportResponse,
    operation_id="generateDailyReport",
    summary="Generate a daily monitoring report",
    description="Generates a daily public information monitoring report and stores JSON and Markdown files. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def daily_report(request: AnalysisRequest) -> MonitoringReportResponse:
    return await build_period_report(request, "daily")


@app.post(
    "/report/weekly",
    response_model=MonitoringReportResponse,
    operation_id="generateWeeklyReport",
    summary="Generate a weekly monitoring report",
    description="Generates a weekly public information monitoring report and stores JSON and Markdown files. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def weekly_report(request: AnalysisRequest) -> MonitoringReportResponse:
    return await build_period_report(request, "weekly")


@app.post(
    "/report/compare",
    response_model=CompareReportsResponse,
    operation_id="compareReports",
    summary="Compare two report dates",
    description="Compares stored JSON reports by date and returns topic, risk, and opportunity differences. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def compare_reports(request: CompareReportsRequest) -> CompareReportsResponse:
    report_a = load_report_json(request.report_a)
    report_b = load_report_json(request.report_b)
    warnings: List[str] = []
    if not report_a:
        warnings.append(f"No JSON report found for {request.report_a}.")
    if not report_b:
        warnings.append(f"No JSON report found for {request.report_b}.")
    comparison = compare_report_payloads(report_a or {}, report_b or {})
    return CompareReportsResponse(report_a=request.report_a, report_b=request.report_b, warnings=warnings, **comparison)


@app.post(
    "/notify/test",
    response_model=NotifyTestResponse,
    operation_id="testNotification",
    summary="Test notification framework",
    description="Returns placeholder status for email, Telegram, Discord, or webhook notification channels. Requires the X-API-Key header.",
    dependencies=[Depends(verify_api_key)],
)
async def notify_test(request: NotifyTestRequest) -> NotifyTestResponse:
    return NotifyTestResponse(**await send_test_notification(request.channel, request.target, request.message))


@app.post(
    "/batch",
    response_model=BatchResponse,
    operation_id="batchResearchTasks",
    summary="Run multiple research analysis tasks",
    description="Runs multiple public information research tasks and returns concise deterministic analysis summaries.",
    dependencies=[Depends(verify_api_key)],
)
async def batch(request: BatchRequest) -> BatchResponse:
    task_outputs: List[BatchTaskResponse] = []
    report_sections: List[str] = ["# Combined Research Report", ""]
    for task in request.tasks:
        analysis_request = AnalysisRequest(
            query=task.query,
            sources=task.sources,
            days=task.days,
            limit=task.limit,
            language=task.language,
            country=task.country,
            analysis_type=task.analysis_type,
            output_language=request.output_language,
        )
        pipeline = await run_search_pipeline(analysis_request)
        analysis = build_analysis_response(analysis_request, pipeline)
        task_outputs.append(
            BatchTaskResponse(
                query=task.query,
                analysis_type=task.analysis_type,
                executive_summary=analysis.executive_summary,
                key_findings=analysis.key_findings,
                warnings=analysis.warnings,
            )
        )
        report_sections.extend([f"## {task.query}", "", analysis.executive_summary, "", analysis.markdown_report, ""])
    return BatchResponse(tasks=task_outputs, combined_markdown_report="\n".join(report_sections))


async def run_monitor_job(monitor: Dict[str, Any]) -> Dict[str, Any]:
    analysis_request = AnalysisRequest(
        query=monitor["query"],
        sources=monitor.get("sources") or DEFAULT_SOURCES,
        days=monitor.get("days", 30),
        limit=monitor.get("limit", 50),
        language=monitor.get("language", "auto"),
        country=monitor.get("country", "any"),
        analysis_type=monitor.get("analysis_type", "trend"),
        export_csv=bool(monitor.get("export_csv", False)),
        export_markdown=True,
    )
    report_response = await build_period_report(analysis_request, "daily", monitor_name=monitor.get("name", "monitor"))
    csv_path = ""
    if monitor.get("export_csv"):
        csv_path = export_csv(report_response.json_report.get("top_results", []), f"reports/{datetime.utcnow().strftime('%Y-%m-%d')}/{monitor['id']}-results.csv")
        report_response.export_paths["csv"] = csv_path

    history = {
        "monitor_id": monitor["id"],
        "monitor_name": monitor.get("name", ""),
        "ran_at": datetime.utcnow().isoformat() + "Z",
        "report": report_response.json_report,
        "export_paths": report_response.export_paths,
        "warnings": report_response.warnings,
    }
    history_path = save_history(monitor["id"], history)
    alert_paths = evaluate_alert_rules(monitor, report_response.json_report)
    updated = update_monitor_after_run(monitor, "ok", len(report_response.warnings))
    return {
        "monitor_id": monitor["id"],
        "name": monitor.get("name", ""),
        "status": "ok",
        "history_path": history_path,
        "export_paths": report_response.export_paths,
        "alert_paths": alert_paths,
        "next_run": updated.get("next_run"),
        "warnings": report_response.warnings,
    }


async def build_period_report(
    request: AnalysisRequest,
    report_type: str,
    monitor_name: str = "",
) -> MonitoringReportResponse:
    pipeline = await run_search_pipeline(request)
    query_label = query_label_from_request(request)
    themes = extract_themes(pipeline["results"], limit=12)
    trends = analyze_trends(pipeline["results"], themes, limit=8)
    risks = analyze_risks(pipeline["results"], limit=8)
    opportunities = analyze_opportunities(pipeline["results"], themes, limit=8)
    story_clusters = cluster_similar_stories(pipeline["results"], limit=10)
    followups = recommended_followups(query_label, themes, request.analysis_type, resolve_output_language(request, pipeline["original_queries"]))
    executive_summary = build_executive_summary(query_label, pipeline["results"], themes, resolve_output_language(request, pipeline["original_queries"]))
    sources = sorted(set(str(result.get("source", "")) for result in pipeline["results"] if result.get("source")))

    json_report: Dict[str, Any] = {
        "report_type": report_type,
        "query": query_label,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "executive_summary": executive_summary,
        "top_stories": pipeline["results"][:10],
        "emerging_trends": trends,
        "risks": risks,
        "opportunities": opportunities,
        "most_discussed_topics": themes,
        "story_clusters": story_clusters,
        "recommended_follow_up_queries": followups,
        "sources_used": sources,
        "warnings": pipeline["warnings"],
    }

    if report_type == "weekly":
        previous = latest_report_before_today()
        comparison = compare_report_payloads(previous or {}, json_report)
        markdown = build_weekly_report(
            title=f"Weekly Monitoring Report: {monitor_name or query_label}",
            week_summary=executive_summary,
            trend_changes=[{"topic": topic, "status": "growing", "change": 1} for topic in comparison["growing_trends"]],
            new_topics=comparison["new_topics"],
            losing_topics=comparison["declining_trends"],
            risk_changes=comparison["risk_differences"],
            opportunity_changes=comparison["opportunity_differences"],
        )
    else:
        markdown = build_monitoring_report(
            title=f"Daily Monitoring Report: {monitor_name or query_label}",
            executive_summary=executive_summary,
            top_stories=pipeline["results"],
            trends=trends,
            risks=risks,
            opportunities=opportunities,
            topics=themes,
            followups=followups,
            sources=sources,
        )

    export_paths = save_report_files(f"{report_type}-{monitor_name or query_label}", json_report, markdown)
    return MonitoringReportResponse(
        report_type=report_type,
        query=query_label,
        markdown_report=markdown,
        json_report=json_report,
        export_paths=export_paths,
        warnings=pipeline["warnings"],
    )


def compare_report_payloads(report_a: Dict[str, Any], report_b: Dict[str, Any]) -> Dict[str, List[str]]:
    topics_a = topic_scores(report_a)
    topics_b = topic_scores(report_b)
    risks_a = named_items(report_a.get("risks", []), "risk")
    risks_b = named_items(report_b.get("risks", []), "risk")
    opportunities_a = named_items(report_a.get("opportunities", []), "opportunity")
    opportunities_b = named_items(report_b.get("opportunities", []), "opportunity")

    new_topics = sorted(set(topics_b) - set(topics_a))
    removed_topics = sorted(set(topics_a) - set(topics_b))
    growing = sorted([topic for topic in set(topics_a) & set(topics_b) if topics_b[topic] > topics_a[topic]], key=lambda item: topics_b[item], reverse=True)
    declining = sorted([topic for topic in set(topics_a) & set(topics_b) if topics_b[topic] < topics_a[topic]], key=lambda item: topics_a[item] - topics_b[item], reverse=True)
    return {
        "new_topics": new_topics[:20],
        "removed_topics": removed_topics[:20],
        "growing_trends": growing[:20],
        "declining_trends": declining[:20],
        "risk_differences": sorted(set(risks_b) ^ set(risks_a))[:20],
        "opportunity_differences": sorted(set(opportunities_b) ^ set(opportunities_a))[:20],
    }


def topic_scores(report: Dict[str, Any]) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for item in report.get("most_discussed_topics", []):
        topic = str(item.get("title", ""))
        if topic:
            scores[topic] = float(item.get("importance_score") or item.get("mention_count") or 1)
    for item in report.get("emerging_trends", []):
        topic = str(item.get("trend", ""))
        if topic:
            scores[topic] = max(scores.get(topic, 0.0), float(item.get("trend_score") or 1))
    return scores


def named_items(items: List[Dict[str, Any]], key: str) -> List[str]:
    return [str(item.get(key, "")) for item in items if item.get(key)]


def latest_report_before_today() -> Optional[Dict[str, Any]]:
    today = datetime.utcnow().date()
    for offset in range(1, 15):
        payload = load_report_json((today - timedelta(days=offset)).isoformat())
        if payload:
            return payload
    return None


def build_ui_page(title: str, sections: List[str]) -> str:
    style = (
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:32px;line-height:1.5;color:#111827;background:#f9fafb}"
        "main{max-width:1120px;margin:0 auto}nav a,.button{display:inline-block;margin:4px 8px 4px 0;padding:8px 10px;border:1px solid #d1d5db;border-radius:6px;background:#fff;color:#2563eb;text-decoration:none}"
        "section{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:18px;margin:16px 0}table{border-collapse:collapse;width:100%;margin:12px 0}td,th{border-bottom:1px solid #e5e7eb;padding:8px;text-align:left;font-size:14px}"
        ".ok{color:#047857;font-weight:600}.warn{color:#b45309;font-weight:600}.muted{color:#6b7280}"
    )
    nav = "<nav><a href='/ui'>Dashboard</a><a href='/ui/research'>Research</a><a href='/ui/workflows'>Workflows</a><a href='/ui/templates'>Templates</a><a href='/ui/automation'>Automation</a><a href='/ui/alerts'>Alerts</a><a href='/ui/status'>Status</a><a href='/ui/reports'>Reports</a><a href='/ui/monitors'>Monitors</a><a href='/openapi.json'>OpenAPI</a><a href='/privacy'>Privacy</a></nav>"
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{title} - Universal Research Assistant</title><style>{style}</style></head><body><main><h1>{title}</h1>{nav}{''.join(sections)}</main></body></html>"


def dashboard_sections() -> List[str]:
    reports = recent_reports(8)
    monitors = list_monitors()
    alerts_data = list_alerts(8)
    sections = [
        "<section><h2>Service Status</h2><p class='ok'>ok</p><p class='muted'>Universal Research Assistant V11 Automation and Notifications</p><p><a class='button' href='/ui/research'>Run research</a><a class='button' href='/ui/automation'>Automation</a><a class='button' href='/ui/workflows'>View workflows</a><a class='button' href='/ui/reports'>Browse reports</a></p></section>",
        source_status_table(),
        report_table(reports, "Recent Reports"),
        monitor_table(monitors[:10], "Monitors"),
        alert_table(alerts_data, "Recent Alerts"),
        workflow_table(list_workflows(8), "Recent Workflows"),
        scheduler_table(),
        "<section><h2>Quick API Links</h2><p><a class='button' href='/health'>Health JSON</a><a class='button' href='/sources'>Sources JSON</a><a class='button' href='/reports'>Reports JSON</a><a class='button' href='/mcp/manifest'>MCP Manifest</a></p></section>",
    ]
    return sections


def status_sections() -> List[str]:
    return [
        "<section><h2>Service</h2><table><tr><th>Status</th><td class='ok'>ok</td></tr><tr><th>Version</th><td>10.0.0</td></tr><tr><th>AI</th><td>optional; deterministic fallback enabled</td></tr></table></section>",
        scheduler_table(),
        source_status_table(),
    ]


def reports_sections() -> List[str]:
    sections = ["<section><h2>Report Dates</h2><p>" + " ".join(f"<a class='button' href='/reports/{date}'>{date}</a>" for date in list_report_dates()) + "</p></section>"]
    sections.append(report_table(recent_reports(100), "Recent Downloadable Reports"))
    return sections


def monitors_sections() -> List[str]:
    return [monitor_table(list_monitors(), "Saved Monitors")]


def research_sections() -> List[str]:
    return [
        "<section><h2>Unified Research Workflow</h2><p>Authenticated API clients can plan, search permitted public sources, normalize, deduplicate, filter, rank, analyze, report, save, and export a traceable workflow through <code>POST /research/run</code>.</p><p class='muted'>AI providers are optional. Deterministic analysis remains available when providers are unavailable.</p></section>",
        template_table(list_templates(), "Available Templates"),
        workflow_table(list_workflows(10), "Recent Workflows"),
        report_table(recent_reports(10), "Recent Downloads"),
    ]


def workflow_sections() -> List[str]:
    return [workflow_table(list_workflows(100), "Saved Workflows")]


def template_sections() -> List[str]:
    return [template_table(list_templates(), "Available Templates")]


def automation_sections() -> List[str]:
    return [
        "<section><h2>Automation Status</h2><p class='muted'>In-process scheduling runs while this service stays awake. Use the authenticated external tick endpoint for reliable Render Cron, GitHub Actions, or uptime scheduler execution.</p><p><a class='button' href='/ui/automation/jobs'>Jobs</a><a class='button' href='/ui/automation/runs'>Runs</a><a class='button' href='/ui/alerts'>Alerts</a></p></section>",
        automation_job_table(list_automation_jobs(), "Scheduled Jobs"),
        automation_run_table(list_automation_runs(12), "Recent Executions"),
        alert_table(list_alerts(12), "Recent Alerts"),
    ]


def source_status_table() -> str:
    rows = "".join(
        f"<tr><td>{item.name}</td><td>{item.available}</td><td>{item.configured}</td><td>{item.note}</td></tr>"
        for item in [source_status(source) for source in ALL_SOURCES]
    )
    return f"<section><h2>Sources</h2><table><tr><th>Source</th><th>Available</th><th>Configured</th><th>Note</th></tr>{rows}</table></section>"


def report_table(reports: List[Dict[str, Any]], title: str) -> str:
    if not reports:
        return f"<section><h2>{title}</h2><p class='muted'>No reports found.</p></section>"
    rows = "".join(
        f"<tr><td>{item.get('date','')}</td><td>{item.get('name','')}</td><td>{item.get('type','')}</td><td>{item.get('size_bytes',0)}</td><td><a href='{item.get('download_url','#')}'>Download</a></td></tr>"
        for item in reports
    )
    return f"<section><h2>{title}</h2><table><tr><th>Date</th><th>Name</th><th>Type</th><th>Bytes</th><th>Download</th></tr>{rows}</table></section>"


def monitor_table(monitors: List[Dict[str, Any]], title: str) -> str:
    if not monitors:
        return f"<section><h2>{title}</h2><p class='muted'>No monitors found.</p></section>"
    rows = "".join(
        f"<tr><td>{monitor.get('name','')}</td><td>{monitor.get('query','')}</td><td>{monitor.get('enabled')}</td><td>{monitor.get('frequency','')}</td><td>{monitor.get('last_run') or ''}</td><td>{monitor.get('next_run') or ''}</td></tr>"
        for monitor in monitors
    )
    return f"<section><h2>{title}</h2><table><tr><th>Name</th><th>Query</th><th>Enabled</th><th>Frequency</th><th>Last Run</th><th>Next Run</th></tr>{rows}</table></section>"


def alert_table(alerts_data: List[Dict[str, Any]], title: str) -> str:
    if not alerts_data:
        return f"<section><h2>{title}</h2><p class='muted'>No alerts found.</p></section>"
    rows = "".join(
        f"<tr><td>{item.get('created_at','')}</td><td>{item.get('monitor_name','')}</td><td>{item.get('rule','')}</td><td>{item.get('severity','')}</td><td>{item.get('message','')}</td></tr>"
        for item in alerts_data
    )
    return f"<section><h2>{title}</h2><table><tr><th>Created</th><th>Monitor</th><th>Rule</th><th>Severity</th><th>Message</th></tr>{rows}</table></section>"


def workflow_table(workflows: List[Dict[str, Any]], title: str) -> str:
    if not workflows:
        return f"<section><h2>{title}</h2><p class='muted'>No workflows found.</p></section>"
    rows = "".join(
        f"<tr><td>{item.get('started_at', '')}</td><td>{item.get('topic', '')}</td><td>{item.get('status', '')}</td><td>{item.get('result_count', 0)}</td><td>{len(item.get('warnings', []))}</td></tr>"
        for item in workflows
    )
    return f"<section><h2>{title}</h2><table><tr><th>Started</th><th>Topic</th><th>Status</th><th>Results</th><th>Warnings</th></tr>{rows}</table></section>"


def template_table(templates: List[Dict[str, Any]], title: str) -> str:
    rows = "".join(
        f"<tr><td>{item.get('id', '')}</td><td>{item.get('name', '')}</td><td>{item.get('description', '')}</td><td>{', '.join(item.get('sources', []))}</td></tr>"
        for item in templates
    )
    return f"<section><h2>{title}</h2><table><tr><th>ID</th><th>Name</th><th>Description</th><th>Sources</th></tr>{rows}</table></section>"


def automation_job_table(jobs: List[Dict[str, Any]], title: str) -> str:
    if not jobs: return f"<section><h2>{title}</h2><p class='muted'>No scheduled jobs found.</p></section>"
    rows = "".join(f"<tr><td>{item.get('name','')}</td><td>{item.get('template','')}</td><td>{item.get('enabled')}</td><td>{item.get('next_run_at') or ''}</td><td>{item.get('last_status','')}</td></tr>" for item in jobs)
    return f"<section><h2>{title}</h2><table><tr><th>Name</th><th>Template</th><th>Enabled</th><th>Next Run</th><th>Last Status</th></tr>{rows}</table></section>"


def automation_run_table(runs: List[Dict[str, Any]], title: str) -> str:
    if not runs: return f"<section><h2>{title}</h2><p class='muted'>No automation runs found.</p></section>"
    rows = "".join(f"<tr><td>{item.get('started_at','')}</td><td>{item.get('job_name','')}</td><td>{item.get('status','')}</td><td>{item.get('result_count',0)}</td><td>{len(item.get('alerts',[]))}</td></tr>" for item in runs)
    return f"<section><h2>{title}</h2><table><tr><th>Started</th><th>Job</th><th>Status</th><th>Results</th><th>Alerts</th></tr>{rows}</table></section>"


def scheduler_table() -> str:
    payload = scheduler_status_payload()
    rows = "".join(f"<tr><th>{key}</th><td>{value}</td></tr>" for key, value in payload.items() if key != "last_warnings")
    return f"<section><h2>Scheduler</h2><table>{rows}</table></section>"


def scheduler_status_payload() -> Dict[str, Any]:
    return {
        "running": bool(scheduler_instance and scheduler_instance.running),
        "interval_seconds": scheduler_instance.interval_seconds if scheduler_instance else 0,
        "supported_frequencies": ["hourly", "daily", "weekly"],
        "enabled_monitors": len([monitor for monitor in list_monitors() if monitor.get("enabled", True)]),
        "due_monitors": len(enabled_due_monitors()),
        "last_warnings": scheduler_instance.last_warnings[-10:] if scheduler_instance else [],
    }


def evaluate_alert_rules(monitor: Dict[str, Any], report: Dict[str, Any]) -> List[str]:
    rules = monitor.get("alert_rules") or {}
    if not rules:
        return []
    text = " ".join(
        [
            report.get("executive_summary", ""),
            " ".join(item.get("title", "") for item in report.get("most_discussed_topics", [])),
            " ".join(item.get("title", "") for item in report.get("top_stories", [])),
        ]
    ).lower()
    alert_paths: List[str] = []
    checks = {
        "new_keyword": rules.get("new_keyword") or rules.get("keywords") or [],
        "competitor_mentioned": rules.get("competitor_mentioned") or rules.get("competitors") or [],
    }
    for rule, terms in checks.items():
        for term in terms if isinstance(terms, list) else [terms]:
            if term and str(term).lower() in text:
                alert_paths.append(save_alert(build_alert(monitor, rule, f"Matched '{term}'.", [str(term)])))
    if rules.get("trend_spike") and len(report.get("emerging_trends", [])) >= int(rules.get("trend_spike_threshold", 3)):
        evidence = [item.get("trend", "") for item in report.get("emerging_trends", [])[:5]]
        alert_paths.append(save_alert(build_alert(monitor, "trend_spike", "Trend signal threshold was reached.", evidence, "warning")))
    if rules.get("source_updated") and report.get("top_stories"):
        evidence = [item.get("url", "") for item in report.get("top_stories", [])[:5]]
        alert_paths.append(save_alert(build_alert(monitor, "source_updated", "New source results were collected.", evidence)))
    return alert_paths


def build_alert(monitor: Dict[str, Any], rule: str, message: str, evidence: List[str], severity: str = "info") -> Dict[str, Any]:
    return {
        "monitor_id": monitor.get("id", ""),
        "monitor_name": monitor.get("name", ""),
        "rule": rule,
        "message": message,
        "severity": severity,
        "evidence": evidence,
    }


async def maybe_enhance_analysis(
    analysis: AnalysisResponse,
    request: AnalysisRequest,
    pipeline: Dict[str, Any],
) -> AnalysisResponse:
    if not request.use_ai or request.ai_provider == "none":
        return analysis
    try:
        language = resolve_output_language(request, pipeline["original_queries"])
        ai_result = await run_ai_analysis(query_label_from_request(request), pipeline["results"], language, request.ai_provider)
        if ai_result.get("warning"):
            analysis.warnings = unique_strings(analysis.warnings + [ai_result["warning"]])
        content = str(ai_result.get("content", "")).strip()
        if content:
            analysis.executive_summary = content
            analysis.markdown_report = f"# AI Enhanced Research Analysis: {query_label_from_request(request)}\n\n## Executive Summary\n\n{content}\n\n" + analysis.markdown_report
    except Exception as exc:
        analysis.warnings = unique_strings(analysis.warnings + [f"AI enhancement failed; deterministic analysis was used. {exc}"])
    return analysis


def build_change_summary(topic: str, changes: Dict[str, List[str]], has_prior: bool) -> str:
    if not has_prior:
        return f"No prior history was found for '{topic}'. Current public information has been saved as a baseline for future comparisons."
    return (
        f"Change detection for '{topic}' found {len(changes.get('new_topics', []))} new topic(s), "
        f"{len(changes.get('growing_topics', []))} growing topic(s), and "
        f"{len(changes.get('declining_topics', []))} declining topic(s)."
    )


async def collect_source(
    source: str,
    collector,
    query: str,
    days: int,
    limit: int,
    language: str,
    country: str,
) -> Tuple[List[SearchResult], List[str]]:
    try:
        return await collector(query, days, limit, language, country), []
    except Exception as exc:
        return [], [f"{source} failed for query '{query}': {exc}"]


async def run_search_pipeline(request: ResearchRequest) -> Dict[str, Any]:
    original_queries = request.queries or ([request.query] if request.query else [])
    search_queries = expand_search_queries(original_queries)
    selected_sources = request.sources or DEFAULT_SOURCES
    collectors = [
        (source, COLLECTORS[source])
        for source in selected_sources
        if source in COLLECTORS and (source != "reddit" or reddit_configuration_status()["available"])
    ]
    per_source_limit = max(10, min(request.limit, 100))
    warnings = source_warnings(selected_sources)

    batches = await asyncio.gather(
        *[
            collect_source(source, collector, query, request.days, per_source_limit, request.language, request.country)
            for query in search_queries
            for source, collector in collectors
        ],
        return_exceptions=True,
    )

    raw_results: List[Dict[str, Any]] = []
    for batch_result in batches:
        if isinstance(batch_result, Exception):
            warnings.append(f"A source request failed: {batch_result}")
            continue
        results, batch_warnings = batch_result
        warnings.extend(batch_warnings)
        raw_results.extend(result.model_dump() if hasattr(result, "model_dump") else result for result in results)

    ranking_query = " ".join(search_queries)
    filtered = remove_ads_spam_irrelevant(raw_results, ranking_query)
    deduped = dedupe_results(filtered)
    ranked = rank_results(deduped, ranking_query)[: request.limit]
    tagged = add_result_metadata(ranked, ranking_query)
    summarized = summarize_results(tagged, settings.get("processing", {}).get("max_summary_chars", 500))
    return {
        "original_queries": original_queries,
        "search_queries": search_queries,
        "ranking_query": ranking_query,
        "sources": selected_sources,
        "warnings": unique_strings(warnings),
        "results": summarized,
        "raw_result_count": len(raw_results),
        "filtered_result_count": len(filtered),
        "deduped_result_count": len(deduped),
    }


async def run_research_workflow(request: ResearchWorkflowRequest) -> Dict[str, Any]:
    """Run the V10 orchestration layer without changing V9 search semantics."""
    return await run_workflow(
        request.model_dump(),
        AnalysisRequest,
        run_search_pipeline,
        build_analysis_response,
        maybe_enhance_analysis,
    )


def read_workflow_report_by_id(workflow_id: str) -> Dict[str, Any]:
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow report not found.")
    try:
        return read_workflow_report(workflow)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved workflow report files were not found.")


def read_workflow_report(workflow: Dict[str, Any]) -> Dict[str, Any]:
    files: Dict[str, Path] = {}
    report_root = Path("reports").resolve()
    for item in workflow.get("downloads", []):
        output_format = str(item.get("format", ""))
        path = Path(str(item.get("path", "")))
        resolved = path.resolve()
        if output_format and report_root in resolved.parents and resolved.is_file():
            files[output_format] = resolved
    if not files:
        raise FileNotFoundError("No saved report files for workflow.")
    json_payload: Dict[str, Any] = {}
    if "json" in files:
        try:
            import json
            json_payload = json.loads(files["json"].read_text(encoding="utf-8"))
        except (OSError, ValueError):
            json_payload = {}
    markdown = files["markdown"].read_text(encoding="utf-8") if "markdown" in files else ""
    html = files["html"].read_text(encoding="utf-8") if "html" in files else ""
    request = workflow.get("request", {})
    return {
        "workflow_id": workflow["workflow_id"],
        "template": request.get("template_name", ""),
        "topic": workflow.get("topic", ""),
        "generated_at": workflow.get("report", {}).get("generated_at") or workflow.get("completed_at", ""),
        "markdown": markdown,
        "html": html,
        "json": json_payload,
        "download_urls": [str(item.get("download_url", "")) for item in workflow.get("downloads", []) if item.get("download_url") and str(item.get("format", "")) in files],
    }


def is_report_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


async def automation_workflow_runner(spec: Dict[str, Any]) -> Dict[str, Any]:
    try:
        payload = get_template(spec["template"])
    except KeyError:
        return {"workflow_id": "", "status": "failed", "result_count": 0, "warnings": ["Automation template was not found."], "analysis": {}, "downloads": []}
    allowed = set(ResearchWorkflowRequest.model_fields)
    payload.update({key: value for key, value in spec.get("overrides", {}).items() if key in allowed})
    payload["template_name"] = spec["template"]
    return await run_research_workflow(ResearchWorkflowRequest(**payload))


async def execute_automation_job(job: Dict[str, Any], scheduled_at: str = "") -> Dict[str, Any]:
    return await run_automation_job(job, automation_workflow_runner, get_workflow, save_alert, send_automation_notifications, scheduled_at)


async def automation_tick_once() -> List[Dict[str, Any]]:
    return [await execute_automation_job(job) for job in due_jobs()]


async def build_automation_digest(period: str, request: AutomationDigestRequest) -> AutomationDigestResponse:
    runs = list_automation_runs(200)
    window_hours = 24 if period == "daily" else 24 * 7
    cutoff = datetime.utcnow() - timedelta(hours=window_hours)
    recent = [item for item in runs if item.get("completed_at") and datetime.fromisoformat(item["completed_at"].replace("Z", "")) >= cutoff]
    alerts_data = [AlertItem(**item) for item in list_alerts(100) if item.get("created_at") and datetime.fromisoformat(str(item["created_at"]).replace("Z", "")) >= cutoff]
    reports = [ReportFileItem(**item) for item in recent_reports(20)]
    top_changes = [f"{item.get('job_name', '')}: {item.get('result_count', 0)} results" for item in recent[:10]]
    warnings: List[str] = []
    if request.send_notifications:
        warnings.extend(await send_automation_notifications(request.notification_channels, {"job_name": f"{period.title()} automation digest", "run_status": "completed", "workflow_id": "", "result_count": sum(item.get("result_count", 0) for item in recent), "warning_count": sum(len(item.get("warnings", [])) for item in recent), "alert_count": len(alerts_data), "summary": "; ".join(top_changes[:3]), "downloads": [{"download_url": item.download_url} for item in reports[:5]], "dashboard_url": "/ui/automation"}))
    return AutomationDigestResponse(period=period, completed_jobs=len([item for item in recent if item.get("status") == "completed"]), failed_jobs=len([item for item in recent if item.get("status") == "failed"]), new_alerts=alerts_data, top_changes=top_changes, latest_reports=reports, download_links=[item.download_url for item in reports], warnings=warnings)


def build_analysis_response(request: AnalysisRequest, pipeline: Dict[str, Any]) -> AnalysisResponse:
    results = pipeline["results"]
    output_language = resolve_output_language(request, pipeline["original_queries"])
    query_label = query_label_from_request(request)
    themes = extract_themes(results)
    trends = analyze_trends(results, themes)
    risks = analyze_risks(results)
    opportunities = analyze_opportunities(results, themes)
    breakdown = source_breakdown(results, themes)
    executive_summary = build_executive_summary(query_label, results, themes, output_language)
    markdown_report = build_markdown_report(
        title=f"Research Analysis: {query_label}",
        executive_summary=executive_summary,
        key_findings=themes,
        trends=trends,
        risks=risks,
        opportunities=opportunities,
        source_breakdown=breakdown,
        top_results=results,
    )
    followups = recommended_followups(query_label, themes, request.analysis_type, output_language)
    markdown_report += "\n## Recommended Follow-up Queries\n\n" + "\n".join(f"- {item}" for item in followups) + "\n"
    return AnalysisResponse(
        query=request.query or "",
        queries=request.queries,
        analysis_type=request.analysis_type,
        sources=pipeline["sources"],
        warnings=pipeline["warnings"],
        executive_summary=executive_summary,
        key_findings=[Finding(**item) for item in themes],
        trends=[TrendItem(**item) for item in trends],
        risks=[RiskItem(**item) for item in risks],
        opportunities=[OpportunityItem(**item) for item in opportunities],
        source_breakdown=[SourceBreakdownItem(**item) for item in breakdown],
        top_results=[SearchResult(**item) if isinstance(item, dict) else item for item in results[:10]],
        recommended_follow_up_queries=followups,
        markdown_report=markdown_report,
    )


def lightweight_analysis(pipeline: Dict[str, Any]) -> Dict[str, Any]:
    themes = extract_themes(pipeline["results"], limit=5)
    return {
        "executive_summary": build_executive_summary(
            ", ".join(pipeline["original_queries"]),
            pipeline["results"],
            themes,
            "English",
        ),
        "key_themes": [item["title"] for item in themes],
        "source_breakdown": source_breakdown(pipeline["results"], themes),
    }


def source_status(source: SourceName) -> SourceStatus:
    if source == "youtube":
        configured = bool(os.getenv("YOUTUBE_API_KEY"))
        return SourceStatus(name=source, available=configured, requires_api_key=True, configured=configured)
    if source == "x":
        configured = bool(os.getenv("X_BEARER_TOKEN"))
        return SourceStatus(name=source, available=configured, requires_api_key=True, configured=configured)
    if source == "reddit":
        reddit = reddit_configuration_status()
        if not reddit["enabled"]:
            note = "Disabled: set REDDIT_ENABLED=true and configure Reddit OAuth credentials to enable collection."
        elif not reddit["oauth_configured"]:
            note = "Disabled: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, and REDDIT_USER_AGENT are all required."
        else:
            note = "Enabled with Reddit app-only OAuth."
        return SourceStatus(
            name=source,
            available=reddit["available"],
            requires_api_key=True,
            configured=reddit["oauth_configured"],
            note=note,
        )
    if source == "tiktok":
        return SourceStatus(
            name=source,
            available=False,
            requires_api_key=False,
            configured=False,
            note="No legal public TikTok search provider is configured; collector returns warnings only.",
        )
    if source == "rss":
        return SourceStatus(
            name=source,
            available=True,
            requires_api_key=False,
            configured=True,
            note="Collects configured verified public feeds and direct public RSS/Atom feed URLs.",
        )
    return SourceStatus(name=source, available=True, requires_api_key=False, configured=True)


def source_warnings(sources_to_check: List[SourceName]) -> List[str]:
    warnings: List[str] = []
    for source in sources_to_check:
        status_item = source_status(source)
        if source == "youtube" and not status_item.configured:
            warnings.append("YouTube source unavailable: YOUTUBE_API_KEY is not configured.")
        elif source == "x" and not status_item.configured:
            warnings.append("X source unavailable: X_BEARER_TOKEN is not configured.")
        elif source == "tiktok" and not status_item.available:
            warnings.append("TikTok source unavailable: no legal public TikTok search provider is configured.")
    return warnings


def expand_search_queries(queries: List[str]) -> List[str]:
    expanded: List[str] = []
    for query in queries:
        expanded.append(query)
        english_terms = chinese_to_english_terms(query)
        if english_terms:
            expanded.append(english_terms)
    return unique_strings(expanded)


def chinese_to_english_terms(query: str) -> str:
    if not any("\u4e00" <= char <= "\u9fff" for char in query):
        return ""
    mapping = {
        "人工智能": "AI",
        "视频": "video",
        "工具": "tools",
        "新闻": "news",
        "宠物": "pet",
        "猫": "cat",
        "狗": "dog",
        "背包": "backpack",
        "投诉": "complaints",
        "评价": "reviews",
        "趋势": "trends",
        "泰国": "Thailand",
        "跨境": "cross-border",
    }
    terms = [english for chinese, english in mapping.items() if chinese in query]
    return " ".join(terms)


def add_result_metadata(results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    from processors.filter import normalize_text, relevance_score
    from processors.ranker import parsed_timestamp

    query_terms = normalize_text(query).split()
    for result in results:
        recency_score = min(parsed_timestamp(result.get("date")) / 2_000_000_000, 1) if result.get("date") else 0
        result["score"] = round(relevance_score(query, result) * 10 + recency_score, 3)
        tags = [str(result.get("source", ""))]
        tags.extend(term for term in query_terms[:5] if term not in tags)
        result["tags"] = tags
    return results


def query_label_from_request(request: ResearchRequest) -> str:
    queries = request.queries or ([request.query] if request.query else [])
    return ", ".join(queries)


def resolve_output_language(request: AnalysisRequest, queries: List[str]) -> str:
    if request.output_language.lower() != "auto":
        return request.output_language
    joined = " ".join(queries)
    return "Chinese" if any("\u4e00" <= char <= "\u9fff" for char in joined) else "English"


def recommended_followups(query_label: str, themes: List[Dict[str, Any]], analysis_type: str, language: str) -> List[str]:
    theme_terms = [item["title"] for item in themes[:3]]
    if language.lower().startswith("chinese") or language.lower() in {"zh", "zh-cn"}:
        base = [f"{query_label} 最新趋势", f"{query_label} 用户反馈", f"{query_label} 风险"]
        return base + [f"{term} 深度分析" for term in theme_terms]
    base = [
        f"{query_label} latest trends",
        f"{query_label} user feedback",
        f"{query_label} risks and concerns",
    ]
    if analysis_type != "general":
        base.append(f"{query_label} {analysis_type} analysis")
    return base + [f"{term} deep dive" for term in theme_terms]


def unique_strings(values: List[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def unique_source_names(values: List[str]) -> List[SourceName]:
    output: List[SourceName] = []
    for value in values:
        if value in ALL_SOURCES and value not in output:
            output.append(value)  # type: ignore[arg-type]
    return output
