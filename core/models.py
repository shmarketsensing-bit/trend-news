"""파이프라인 단계별 데이터 모델."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Scores(BaseModel):
    trend: int = Field(default=0, ge=0, le=5)
    business: int = Field(default=0, ge=0, le=5)
    novelty: int = Field(default=0, ge=0, le=5)
    spread: int = Field(default=0, ge=0, le=5)

    @property
    def total(self) -> int:
        return self.trend + self.business + self.novelty + self.spread


class RawArticle(BaseModel):
    """네이버 검색 API 원천."""
    title: str
    press: Optional[str] = None
    published_at: Optional[datetime] = None
    naver_url: str = ""
    origin_url: str = ""
    naver_summary: str = ""
    keyword: str = ""
    category_hint: str = ""


class DedupedArticle(RawArticle):
    """중복 제거 후 대표기사."""
    cluster_id: str = ""
    duplicate_count: int = 1
    body: Optional[str] = None
    body_source: str = "naver"          # "origin" | "naver"


class AnalyzedArticle(DedupedArticle):
    """Claude 분석 결과 결합."""
    category: str = ""
    suggested_category: Optional[str] = None
    summary: str = ""
    comment: str = ""
    implication: str = ""
    hashtags: list[str] = Field(default_factory=list)
    scores: Scores = Field(default_factory=Scores)
    total: int = 0
    reason: str = ""


class NotionPayload(BaseModel):
    """Notion 업로드용 정규화 페이로드."""
    category: str
    title: str
    comment: str
    url: str
    hashtags: list[str] = Field(default_factory=list)
    author: str = "Claude"
    press: Optional[str] = None
    published_at: Optional[datetime] = None
    collected_at: Optional[datetime] = None
    total_score: Optional[int] = None
    reason: Optional[str] = None
    memo: Optional[str] = None
    upload_status: str = "업로드완료"
