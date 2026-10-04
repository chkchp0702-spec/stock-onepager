"""시세·재무·애널리스트·뉴스 수집 (야후 파이낸스 + 구글 뉴스 RSS)."""
from __future__ import annotations

import json

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
    d.estimates, d.ltg = fetch_estimates(t, d.financials[-1].period if d.financials else None)

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


def parse_estimates(rev_df, eps_df, last_fy: Optional[str]) -> list[dict]:
    """야후 revenue_estimate / earnings_estimate → 올해·내년 회계연도 추정치.
    0y = 진행 중인 회계연도, +1y = 그다음 해. 연도 이름은 마지막 실적 연도 + 1, + 2."""
    out = []
    try:
        base = int(str(last_fy)[:4]) if last_fy else dt.date.today().year - 1
    except ValueError:
        base = dt.date.today().year - 1
    for k, add in (("0y", 1), ("+1y", 2)):
        row = {"period": str(base + add)}
        for df, pre in ((rev_df, "rev"), (eps_df, "eps")):
            if df is None or getattr(df, "empty", True) or k not in df.index:
                continue
            r = df.loc[k]
            row[pre] = _num(r.get("avg"))
            row[pre + "_lo"] = _num(r.get("low"))
            row[pre + "_hi"] = _num(r.get("high"))
            row[pre + "_g"] = _num(r.get("growth"))
            n = _num(r.get("numberOfAnalysts"))
            if n:
                row["n"] = max(int(n), row.get("n", 0))
        if row.get("rev") is not None or row.get("eps") is not None:
            out.append(row)
    return out


def parse_ltg(df) -> Optional[float]:
    if df is None or getattr(df, "empty", True) or "+5y" not in df.index:
        return None
    r = df.loc["+5y"]
    for c in ("stockTrend", "stock"):
        if c in r.index:
            return _num(r[c])
    return _num(r.iloc[0])


def fetch_calendar(t) -> dict:
    """다가오는 실적 발표일 · 배당락일 · 배당 지급일 (야후 calendar)"""
    c = _safe(lambda: t.calendar, None) or {}
    if not isinstance(c, dict):
        return {}
    iso = lambda v: v.isoformat()[:10] if hasattr(v, "isoformat") else (str(v)[:10] if v else "")
    out = {}
    e = c.get("Earnings Date")
    if e:
        out["earn"] = [iso(x) for x in (e if isinstance(e, (list, tuple)) else [e]) if x]
    if c.get("Ex-Dividend Date"):
        out["exdiv"] = iso(c["Ex-Dividend Date"])
    if c.get("Dividend Date"):
        out["div"] = iso(c["Dividend Date"])
    return out


def fetch_estimates(t, last_fy: Optional[str]):
    est = _safe(lambda: parse_estimates(_safe(lambda: t.revenue_estimate, None), _safe(lambda: t.earnings_estimate, None), last_fy), [])
    ltg = _safe(lambda: parse_ltg(t.growth_estimates), None)
    return est, ltg


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


_TR_CACHE: dict[str, str] = {}

# 야후 업종명 → 한국어 (자주 나오는 것만; 없으면 자동 번역)
INDUSTRY_KO = {
    "Semiconductors": "반도체", "Semiconductor Equipment & Materials": "반도체 장비·소재",
    "Software - Application": "응용 소프트웨어", "Software - Infrastructure": "인프라 소프트웨어",
    "Information Technology Services": "IT 서비스", "Consumer Electronics": "가전·전자기기",
    "Electronic Components": "전자부품", "Communication Equipment": "통신장비", "Computer Hardware": "컴퓨터 하드웨어",
    "Internet Content & Information": "인터넷 콘텐츠·정보", "Internet Retail": "온라인 유통", "Electronic Gaming & Multimedia": "게임·멀티미디어",
    "Entertainment": "엔터테인먼트", "Telecom Services": "통신 서비스", "Advertising Agencies": "광고",
    "Drug Manufacturers - General": "제약 (대형)", "Drug Manufacturers - Specialty & Generic": "제약 (스페셜티·제네릭)",
    "Biotechnology": "바이오", "Medical Devices": "의료기기", "Medical Instruments & Supplies": "의료 기구·소모품",
    "Diagnostics & Research": "진단·연구", "Healthcare Plans": "건강보험", "Medical Care Facilities": "의료기관",
    "Banks - Regional": "지역은행", "Banks - Diversified": "대형은행", "Asset Management": "자산운용",
    "Capital Markets": "증권·자본시장", "Insurance - Life": "생명보험", "Insurance - Property & Casualty": "손해보험",
    "Insurance - Diversified": "종합보험", "Credit Services": "신용·결제", "Financial Data & Stock Exchanges": "금융정보·거래소",
    "Specialty Retail": "전문 소매", "Discount Stores": "할인점", "Department Stores": "백화점", "Grocery Stores": "식료품점",
    "Restaurants": "외식", "Apparel Retail": "의류 유통", "Apparel Manufacturing": "의류 제조", "Footwear & Accessories": "신발·잡화",
    "Auto Manufacturers": "자동차", "Auto Parts": "자동차 부품", "Auto & Truck Dealerships": "자동차 판매",
    "Packaged Foods": "가공식품", "Beverages - Non-Alcoholic": "음료", "Beverages - Brewers": "맥주", "Beverages - Wineries & Distilleries": "주류",
    "Household & Personal Products": "생활용품", "Tobacco": "담배", "Confectioners": "제과",
    "Oil & Gas E&P": "석유·가스 탐사생산", "Oil & Gas Integrated": "종합 석유", "Oil & Gas Midstream": "석유·가스 수송",
    "Oil & Gas Refining & Marketing": "정유", "Oil & Gas Equipment & Services": "유전 장비·서비스", "Uranium": "우라늄", "Solar": "태양광",
    "Chemicals": "화학", "Specialty Chemicals": "특수화학", "Steel": "철강", "Aluminum": "알루미늄", "Copper": "구리",
    "Gold": "금광", "Silver": "은광", "Other Industrial Metals & Mining": "산업금속·광업", "Building Materials": "건축자재",
    "Paper & Paper Products": "제지", "Agricultural Inputs": "농업자재",
    "Aerospace & Defense": "항공우주·방산", "Specialty Industrial Machinery": "산업기계", "Electrical Equipment & Parts": "전기장비·부품",
    "Engineering & Construction": "건설·엔지니어링", "Railroads": "철도", "Airlines": "항공사", "Marine Shipping": "해운", "Trucking": "육상운송",
    "Integrated Freight & Logistics": "물류", "Farm & Heavy Construction Machinery": "농기계·중장비", "Industrial Distribution": "산업재 유통",
    "Staffing & Employment Services": "인력·채용 서비스", "Consulting Services": "컨설팅", "Security & Protection Services": "보안 서비스",
    "Waste Management": "폐기물 처리", "Pollution & Treatment Controls": "환경설비", "Conglomerates": "지주·복합기업",
    "Utilities - Regulated Electric": "전력", "Utilities - Renewable": "신재생 에너지", "Utilities - Regulated Gas": "가스",
    "REIT - Residential": "주거 리츠", "REIT - Retail": "상업 리츠", "REIT - Office": "오피스 리츠", "REIT - Industrial": "산업 리츠",
    "Real Estate Services": "부동산 서비스", "Real Estate - Development": "부동산 개발",
    "Shell Companies": "스팩(SPAC)", "Leisure": "레저", "Lodging": "숙박", "Resorts & Casinos": "리조트·카지노", "Gambling": "게임·도박",
    "Education & Training Services": "교육", "Scientific & Technical Instruments": "과학·계측기기", "Tools & Accessories": "공구",
    "Packaging & Containers": "포장", "Furnishings, Fixtures & Appliances": "가구·가전", "Luxury Goods": "명품",
}


def translate_ko(text: str, timeout: float = 8.0) -> str:
    """영어 → 한국어 (구글 번역 비공식 엔드포인트). 실패하면 빈 문자열."""
    text = (text or "").strip()
    if not text:
        return ""
    if text in INDUSTRY_KO:
        return INDUSTRY_KO[text]
    if text in _TR_CACHE:
        return _TR_CACHE[text]
    url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(
        {"client": "gtx", "sl": "auto", "tl": "ko", "dt": "t", "q": text[:1500]})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        out = "".join(seg[0] for seg in data[0] if seg and seg[0]).strip()
    except Exception:
        out = ""
    _TR_CACHE[text] = out
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
