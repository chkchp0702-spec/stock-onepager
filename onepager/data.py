"""시세·재무·애널리스트·뉴스 수집 (야후 파이낸스 + 구글 뉴스 RSS)."""
from __future__ import annotations

import datetime as dt
import math
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Optional

from .models import AnalystView, FinancialYear, NewsItem, StockData, Ticker

RATING_KO = {
    "strong_buy": "적극 매수", "buy": "매수", "hold": "보유",
    "underperform": "비중 축소", "sell": "매도", "strong_sell": "적극 매도", "none": "",
}

ACTION_KO = {"up": "상향", "down": "하향", "init": "신규", "main": "유지", "reit": "재확인"}


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return None


def fetch(ticker: Ticker, news_limit: int = 6) -> StockData:
    import yfinance as yf

    t = yf.Ticker(ticker.symbol)
    info: dict = {}
    try:
        info = t.info or {}
    except Exception:
        pass

    # 국내 6자리 코드를 .KS로 가정했는데 데이터가 없으면 코스닥(.KQ)으로 재시도
    if ticker.symbol.endswith(".KS") and not _has_price(info):
        alt = ticker.symbol[:-3] + ".KQ"
        t2 = yf.Ticker(alt)
        try:
            info2 = t2.info or {}
        except Exception:
            info2 = {}
        if _has_price(info2):
            ticker.symbol, t, info = alt, t2, info2

    if not _has_price(info):
        raise LookupError(f"{ticker.symbol} 시세 데이터를 가져오지 못했습니다.")

    if ticker.name in (ticker.symbol, ticker.symbol.split(".")[0]) or ticker.name.isdigit():
        ticker.name = info.get("longName") or info.get("shortName") or ticker.name

    d = parse_info(ticker, info)
    d.financials = _safe(lambda: parse_income_stmt(t.income_stmt), [])
    d.price_history = _safe(lambda: parse_history(t.history(period="1y", interval="1d")), [])
    if d.price_history and d.price is None:
        d.price = d.price_history[-1][1]
    _safe(lambda: parse_recommendations(t.recommendations, d.analyst), None)
    _safe(lambda: parse_upgrades(t.upgrades_downgrades, d.analyst), None)

    news = _safe(lambda: google_news(_news_query(ticker, info), limit=news_limit), [])
    if len(news) < news_limit:
        news += _safe(lambda: parse_yf_news(t.news), [])
    d.news = _dedupe(news)[:news_limit]
    d.as_of = dt.date.today().isoformat()
    return d


def _has_price(info: dict) -> bool:
    return any(_num(info.get(k)) for k in ("currentPrice", "regularMarketPrice", "previousClose"))


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def parse_info(ticker: Ticker, info: dict) -> StockData:
    price = _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice"))
    prev = _num(info.get("regularMarketPreviousClose")) or _num(info.get("previousClose"))
    change = (price / prev - 1) if price and prev else None

    div_rate = _num(info.get("dividendRate")) or _num(info.get("trailingAnnualDividendRate"))
    div_yield = (div_rate / price) if div_rate and price else None

    rec = (info.get("recommendationKey") or "none").lower()
    analyst = AnalystView(
        n_analysts=int(info["numberOfAnalystOpinions"]) if _num(info.get("numberOfAnalystOpinions")) else None,
        rating=RATING_KO.get(rec, rec),
        target_mean=_num(info.get("targetMeanPrice")),
        target_high=_num(info.get("targetHighPrice")),
        target_low=_num(info.get("targetLowPrice")),
    )
    return StockData(
        ticker=ticker,
        currency=info.get("currency") or "USD",
        price=price,
        change_pct=change,
        market_cap=_num(info.get("marketCap")),
        pe=_num(info.get("trailingPE")) or _num(info.get("forwardPE")),
        pb=_num(info.get("priceToBook")),
        dividend_yield=div_yield,
        week52_low=_num(info.get("fiftyTwoWeekLow")),
        week52_high=_num(info.get("fiftyTwoWeekHigh")),
        sector=info.get("sector", "") or "",
        industry=info.get("industry", "") or "",
        country=info.get("country", "") or "",
        city=info.get("city", "") or "",
        employees=int(info["fullTimeEmployees"]) if _num(info.get("fullTimeEmployees")) else None,
        website=info.get("website", "") or "",
        business_summary=info.get("longBusinessSummary", "") or "",
        analyst=analyst,
    )


def _row(df, *names):
    for n in names:
        if n in df.index:
            return df.loc[n]
    return None


def parse_income_stmt(df, years: int = 4) -> list[FinancialYear]:
    if df is None or getattr(df, "empty", True):
        return []
    rev = _row(df, "Total Revenue", "Operating Revenue")
    op = _row(df, "Operating Income", "Total Operating Income As Reported")
    ni = _row(df, "Net Income Common Stockholders", "Net Income")
    eps = _row(df, "Diluted EPS", "Basic EPS")
    out = []
    for col in list(df.columns)[:years]:
        fy = FinancialYear(
            period=str(getattr(col, "year", col)),
            revenue=_num(rev[col]) if rev is not None else None,
            operating_income=_num(op[col]) if op is not None else None,
            net_income=_num(ni[col]) if ni is not None else None,
            eps=_num(eps[col]) if eps is not None else None,
        )
        if fy.revenue is not None or fy.net_income is not None:
            out.append(fy)
    return list(reversed(out))   # 오래된 연도 → 최근 연도


def parse_history(df) -> list[tuple[str, float]]:
    if df is None or getattr(df, "empty", True):
        return []
    out = []
    for idx, close in df["Close"].items():
        v = _num(close)
        if v is not None:
            out.append((idx.strftime("%Y-%m-%d"), v))
    return out


def parse_recommendations(df, a: AnalystView) -> None:
    if df is None or getattr(df, "empty", True):
        return
    row = df.iloc[0]
    for k_src, k_dst in (("strongBuy", "strong_buy"), ("buy", "buy"), ("hold", "hold"),
                         ("sell", "sell"), ("strongSell", "strong_sell")):
        if k_src in row:
            setattr(a, k_dst, int(_num(row[k_src]) or 0))
    total = a.strong_buy + a.buy + a.hold + a.sell + a.strong_sell
    if total and not a.n_analysts:
        a.n_analysts = total


def parse_upgrades(df, a: AnalystView, limit: int = 4, days: int = 120) -> None:
    if df is None or getattr(df, "empty", True):
        return
    df = df.sort_index(ascending=False)
    cutoff = dt.date.today() - dt.timedelta(days=days)
    for idx, r in df.iterrows():
        d = idx.date() if hasattr(idx, "date") else None
        if d and d < cutoff:
            break
        firm = r.get("Firm", "")
        to_g, from_g = r.get("ToGrade", ""), r.get("FromGrade", "")
        action = ACTION_KO.get(str(r.get("Action", "")).lower(), "")
        grade = f"{from_g}→{to_g}" if from_g and from_g != to_g else to_g
        pt = _num(r.get("currentPriceTarget"))
        prior = _num(r.get("priorPriceTarget"))
        tgt = ""
        if pt:
            tgt = f", 목표 {prior:,.0f}→{pt:,.0f}" if prior and prior != pt else f", 목표 {pt:,.0f}"
        a.recent_actions.append(f"{d or ''} {firm}: {grade} {action}{tgt}".strip())
        if len(a.recent_actions) >= limit:
            break


def parse_yf_news(items) -> list[NewsItem]:
    out = []
    for it in items or []:
        c = it.get("content", it)
        title = c.get("title", "")
        if not title:
            continue
        prov = c.get("provider")
        publisher = prov.get("displayName", "") if isinstance(prov, dict) else it.get("publisher", "")
        url = c.get("canonicalUrl")
        link = url.get("url", "") if isinstance(url, dict) else it.get("link", "")
        date = (c.get("pubDate") or "")[:10]
        if not date and it.get("providerPublishTime"):
            date = dt.datetime.fromtimestamp(it["providerPublishTime"]).date().isoformat()
        out.append(NewsItem(title=title, publisher=publisher, link=link, date=date))
    return out


def _news_query(ticker: Ticker, info: dict) -> str:
    if ticker.market == "US":
        return f"{info.get('shortName') or ticker.name} 주가"
    return f"{ticker.name} 주가"


def google_news(query: str, limit: int = 6, timeout: float = 8.0) -> list[NewsItem]:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query + " when:30d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return parse_google_rss(r.read(), limit)


def parse_google_rss(xml_bytes: bytes, limit: int = 6) -> list[NewsItem]:
    from email.utils import parsedate_to_datetime

    root = ET.fromstring(xml_bytes)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        src = (item.findtext("source") or "").strip()
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        date = ""
        try:
            date = parsedate_to_datetime(item.findtext("pubDate") or "").date().isoformat()
        except Exception:
            pass
        out.append(NewsItem(title=title, publisher=src, link=item.findtext("link") or "", date=date))
    out.sort(key=lambda n: n.date, reverse=True)
    return out[:limit]


def _dedupe(items: list[NewsItem]) -> list[NewsItem]:
    seen, out = set(), []
    for n in items:
        key = n.title[:40]
        if key not in seen:
            seen.add(key)
            out.append(n)
    return out
