from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    source: str = Field(default="", description="Source that produced the result.")
    title: str = Field(default="", description="Result title.")
    url: str = Field(default="", description="Canonical result URL.")
    author: str = Field(default="", description="Public author, channel, source, or publisher when available.")
    date: Optional[str] = Field(default=None, description="Published date or indexed date when available.")
    summary: str = Field(default="", description="Short result summary.")
    full_text: str = Field(default="", description="Full public text when available from the source.")
    image_url: str = Field(default="", description="Image or thumbnail URL when available.")
    video_url: str = Field(default="", description="Video URL when available.")
    likes: Optional[int] = Field(default=None, description="Public like/upvote count when available.")
    comments: Optional[int] = Field(default=None, description="Public comment/reply count when available.")
    shares: Optional[int] = Field(default=None, description="Public share/repost count when available.")
    views: Optional[int] = Field(default=None, description="Public view count when available.")
    reason_selected: str = Field(default="", description="Why the result was selected for the query.")
    score: float = Field(default=0, description="Internal relevance and recency score used for ranking.")
    tags: List[str] = Field(default_factory=list, description="Simple tags inferred from source and query terms.")
