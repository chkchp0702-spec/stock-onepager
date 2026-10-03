"""오프라인 데모/테스트용 예시 데이터 (파이브 빌로우, 2026-09 원 페이지 참고 · 수치 근사)."""
from __future__ import annotations

import datetime as dt
import math

from .models import AnalystView, FinancialYear, NewsItem, StockData, Ticker


def _history() -> list[tuple[str, float]]:
    start = dt.date(2025, 9, 3)
    out = []
    for i in range(0, 365, 3):
        day = start + dt.timedelta(days=i)
        base = 140 + 120 * (i / 364) ** 1.4
        out.append((day.isoformat(), round(base + 6 * math.sin(i / 11), 2)))
    out[-1] = (out[-1][0], 260.0)
    return out


def sample_data() -> StockData:
    return StockData(
        ticker=Ticker("FIVE", "파이브 빌로우", "US", "NASDAQ"),
        currency="USD",
        price=260.0,
        change_pct=0.07,
        market_cap=260.0 * 55.3e6,
        pe=30.6,
        pb=6.4,
        dividend_yield=None,
        week52_low=137.77,
        week52_high=263.88,
        sector="Consumer Cyclical",
        industry="Specialty Retail",
        country="United States",
        city="Philadelphia",
        employees=16200,
        business_summary=("Five Below, Inc. operates as a specialty value retailer offering a range of "
                          "merchandise targeted at the tween and teen demographic, with most items priced at $5 "
                          "or below. It operates about 1,970 stores in 46 states."),
        financials=[
            FinancialYear("2022", 3.08e9, 3.4e8, 2.61e8, 4.69),
            FinancialYear("2023", 3.56e9, 3.8e8, 3.02e8, 5.41),
            FinancialYear("2024", 3.88e9, 3.3e8, 2.53e8, 4.60),
            FinancialYear("2025", 4.76e9, 5.6e8, 4.4e8, 7.93),
        ],
        price_history=_history(),
        analyst=AnalystView(
            n_analysts=17, rating="매수", strong_buy=4, buy=9, hold=4, sell=0,
            target_mean=273.43, target_high=350.0, target_low=210.0,
            recent_actions=["2026-09-03 Jefferies: Hold→Buy 상향, 목표 210→350",
                            "2026-09-03 Deutsche Bank: Buy 유지, 목표 318→334",
                            "2026-09-03 Telsey Advisory: Outperform 유지, 목표 260→280",
                            "2026-09-02 Loop Capital: Buy→Hold 하향, 목표 250"],
        ),
        news=[
            NewsItem("파이브 빌로우, 2분기 EPS 1.68달러로 예상 상회…연간 가이던스 상향", "예시", "", "2026-09-02"),
            NewsItem("6억 달러 자사주 매입 프로그램 발표", "예시", "", "2026-09-02"),
            NewsItem("동일매장 매출 22.7% 증가, 저가 소매 수요 지속", "예시", "", "2026-06-03"),
        ],
        as_of="2026-09-03 (예시 데이터)",
    )
