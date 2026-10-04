"""원 페이지 리포트에 쓰이는 데이터 구조."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Ticker:
    symbol: str          # 야후 파이낸스 심볼 (예: 005930.KS, 7203.T, 0700.HK, FIVE)
    name: str            # 표시용 종목명
    market: str          # US / KR / JP / CN / HK
    exchange: str = ""


@dataclass
class FinancialYear:
    period: str                      # 예: "2025"
    revenue: Optional[float] = None
    operating_income: Optional[float] = None
    net_income: Optional[float] = None
    eps: Optional[float] = None

    @property
    def op_margin(self) -> Optional[float]:
        if self.revenue and self.operating_income is not None:
            return self.operating_income / self.revenue
        return None


@dataclass
class NewsItem:
    title: str
    publisher: str = ""
    link: str = ""
    date: str = ""               # YYYY-MM-DD


@dataclass
class AnalystView:
    n_analysts: Optional[int] = None
    rating: str = ""             # 예: "매수", "보유"
    strong_buy: int = 0
    buy: int = 0
    hold: int = 0
    sell: int = 0
    strong_sell: int = 0
    target_mean: Optional[float] = None
    target_high: Optional[float] = None
    target_low: Optional[float] = None
    recent_actions: list[str] = field(default_factory=list)   # "2026-09-02 제프리스: 보유→매수, 목표 350"
    summary: str = ""            # 한국어 요약 문장


@dataclass
class StockData:
    ticker: Ticker
    currency: str = "USD"
    price: Optional[float] = None
    change_pct: Optional[float] = None
    market_cap: Optional[float] = None
    pe: Optional[float] = None
    pb: Optional[float] = None
    dividend_yield: Optional[float] = None
    week52_low: Optional[float] = None
    week52_high: Optional[float] = None
    sector: str = ""
    industry: str = ""
    country: str = ""
    city: str = ""
    employees: Optional[int] = None
    website: str = ""
    business_summary: str = ""          # 원문(대개 영어)
    business_summary_ko: str = ""       # 한국어 번역 (있으면 우선 사용)
    estimates: list = field(default_factory=list)   # 애널리스트 추정치 [{"period","rev","rev_lo","rev_hi","rev_g","eps","eps_lo","eps_hi","eps_g","n"}]
    ltg: Optional[float] = None          # 향후 5년 연평균 EPS 성장률 추정
    industry_ko: str = ""               # 업종 한국어
    financials: list[FinancialYear] = field(default_factory=list)
    price_history: list[tuple[str, float]] = field(default_factory=list)  # (YYYY-MM-DD, close)
    analyst: AnalystView = field(default_factory=AnalystView)
    news: list[NewsItem] = field(default_factory=list)
    as_of: str = ""


@dataclass
class Narrative:
    """사람이 읽는 한국어 문장들 (LLM 또는 규칙 기반으로 생성)."""
    one_liner: str
    overview: list[str]                  # 회사 개요 bullet
    flow: list[tuple[str, str]]          # 사업 구조 그림: (단계 제목, 설명) 3~4개
    financial_comment: list[str]
    analyst_summary: str
    news_ko: list[str] = field(default_factory=list)   # 뉴스 제목 한국어 요약(없으면 원문)
    source: str = "rule"                 # "llm" 또는 "rule"
    summary3: list[str] = field(default_factory=list)  # 맨 위 3줄 요약
    badges: list[tuple[str, str]] = field(default_factory=list)  # (문구, good|warn|neutral)
