"""한국어 문장 생성.

ANTHROPIC_API_KEY 환경변수가 있으면 Claude API로 한 줄 설명·개요·사업 구조·애널리스트 요약·뉴스
번역을 만들고, 없거나 실패하면 규칙 기반 문장으로 대체한다.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Optional

from .models import Narrative, StockData
from .fmt import money, pct

SECTOR_KO = {
    "Technology": "기술", "Communication Services": "커뮤니케이션 서비스",
    "Consumer Cyclical": "경기소비재", "Consumer Defensive": "필수소비재",
    "Healthcare": "헬스케어", "Financial Services": "금융", "Industrials": "산업재",
    "Energy": "에너지", "Basic Materials": "소재", "Real Estate": "부동산",
    "Utilities": "유틸리티",
}

COUNTRY_KO = {
    "United States": "미국", "South Korea": "한국", "Korea, Republic of": "한국",
    "Japan": "일본", "China": "중국", "Hong Kong": "홍콩", "Taiwan": "대만",
    "Netherlands": "네덜란드", "United Kingdom": "영국", "Cayman Islands": "케이맨 제도",
}

# 섹터별 기본 사업 흐름 (단계 제목, 설명)
SECTOR_FLOW = {
    "Technology": [("연구개발", "기술·제품 설계"), ("제품/서비스", "하드웨어·소프트웨어"),
                   ("판매", "기업·소비자 직판 및 파트너"), ("매출", "제품 판매·구독료")],
    "Communication Services": [("콘텐츠/플랫폼", "서비스 운영"), ("이용자", "트래픽·가입자 확보"),
                               ("수익화", "광고·구독·결제"), ("매출", "광고비·이용료")],
    "Consumer Cyclical": [("조달/생산", "상품 기획·제조"), ("유통", "매장·온라인"),
                          ("소비자", "구매"), ("매출", "판매 대금")],
    "Consumer Defensive": [("원재료", "농산물·원료 조달"), ("생산/조달", "필수품 제조"),
                           ("유통", "마트·편의점·온라인"), ("매출", "반복 구매")],
    "Healthcare": [("연구개발", "신약·기기 개발"), ("임상/허가", "규제 승인"),
                   ("공급", "병원·약국"), ("매출", "처방·판매·로열티")],
    "Financial Services": [("자금 조달", "예금·보험료·투자금"), ("운용", "대출·투자"),
                           ("서비스", "결제·자문·보험"), ("수익", "이자·수수료·운용수익")],
    "Industrials": [("수주", "기업·정부 발주"), ("생산", "설계·제조·시공"),
                    ("납품/서비스", "인도·유지보수"), ("매출", "계약 대금")],
    "Energy": [("탐사/생산", "원유·가스 확보"), ("정제/가공", "연료·화학제품"),
               ("공급", "산업·소비자"), ("매출", "에너지 판매")],
    "Basic Materials": [("원료", "광산·원자재"), ("가공", "소재 생산"),
                        ("고객사", "제조업체 공급"), ("매출", "소재 판매")],
    "Real Estate": [("자산 확보", "토지·건물 매입"), ("개발/운영", "임대·관리"),
                    ("임차인", "기업·개인"), ("수익", "임대료·매각 차익")],
    "Utilities": [("발전/공급망", "전력·가스 설비"), ("공급", "송배전"),
                  ("고객", "가정·산업"), ("매출", "요금")],
}
DEFAULT_FLOW = [("핵심 역량", "제품·서비스"), ("고객", "기업·소비자"),
                ("판매", "판매 채널"), ("매출", "수익 창출")]

MARKET_KO = {"US": "미국", "KR": "한국", "JP": "일본", "CN": "중국", "HK": "홍콩"}


# ── 규칙 기반 ────────────────────────────────────────────────────

def rule_based(d: StockData) -> Narrative:
    sector = SECTOR_KO.get(d.sector, d.sector)
    country = COUNTRY_KO.get(d.country, d.country) or MARKET_KO.get(d.ticker.market, "")
    industry = d.industry_ko or d.industry
    desc = d.business_summary_ko or d.business_summary
    first = _first_sentence(desc)

    one = f"{country} {sector} 기업".strip()
    if industry:
        one += f" · {industry}"
    if d.market_cap:
        one += f" · 시가총액 {money(d.market_cap, d.currency)}"

    overview = []
    if country or d.city:
        overview.append(f"본사: {' '.join(x for x in (country, d.city) if x)}")
    if sector:
        overview.append(f"업종: {sector}{' / ' + industry if industry else ''}")
    if d.employees:
        overview.append(f"직원: {d.employees:,}명")
    if desc:
        # 한국어 설명은 세 문장까지, 영어 원문은 첫 문장만
        if d.business_summary_ko:
            sents = re.split(r"(?<=[.다요])\s+", desc.strip())
            overview.append(" ".join(sents[:3])[:420])
        else:
            overview.append(first)

    return Narrative(
        one_liner=one,
        overview=overview,
        flow=SECTOR_FLOW.get(d.sector, DEFAULT_FLOW),
        financial_comment=financial_comment(d),
        analyst_summary=analyst_summary(d),
        news_ko=[n.title for n in d.news],
        source="rule",
        summary3=summary3(d, country, sector, first),
        badges=badges(d),
    )


def _rev_growth(d: StockData):
    f = d.financials
    if len(f) >= 2 and f[-1].revenue and f[-2].revenue:
        return f[-1].revenue / f[-2].revenue - 1
    return None


def _w52_pos(d: StockData):
    if d.price and d.week52_low and d.week52_high and d.week52_high > d.week52_low:
        return (d.price - d.week52_low) / (d.week52_high - d.week52_low)
    return None


def summary3(d: StockData, country: str, sector: str, first: str) -> list[str]:
    """맨 위 3줄: ① 무엇을 하는 회사 ② 돈은 잘 버나 ③ 시장은 어떻게 보나"""
    out = []
    what = f"{country} {sector} 기업".strip()
    if first:
        what += " — " + (first if len(first) <= 90 else first[:89] + "…")
    out.append(what)

    f = d.financials
    if f and f[-1].revenue:
        g = _rev_growth(d)
        line = f"{f[-1].period}년 매출 {money(f[-1].revenue, d.currency)}"
        if g is not None:
            line += f", 전년보다 {pct(g, sign=True)}"
        if f[-1].op_margin is not None:
            line += f" · 영업이익률 {pct(f[-1].op_margin, digits=0)}"
            line += " (적자)" if f[-1].op_margin < 0 else ""
        out.append(line)
    else:
        out.append("재무 자료가 아직 없습니다 (신규 상장이거나 공시 지연)")

    a = d.analyst
    buys, sells = a.strong_buy + a.buy, a.sell + a.strong_sell
    if a.target_mean and d.price:
        up = a.target_mean / d.price - 1
        line = f"애널리스트 {a.n_analysts or '다수'}명 평균 '{a.rating or '의견'}' · 목표가는 현재가보다 {pct(up, sign=True)}"
        out.append(line)
    else:
        pos = _w52_pos(d)
        if pos is not None:
            where = "고점 근처" if pos >= 0.8 else "저점 근처" if pos <= 0.2 else "중간"
            out.append(f"애널리스트 의견 없음 · 주가는 52주 범위의 {pos * 100:.0f}% 위치 ({where})")
        else:
            out.append("애널리스트 의견 없음")
    return out


def badges(d: StockData) -> list[tuple[str, str]]:
    """좋음(good)·주의(warn)·중립(neutral) 배지 4개"""
    b = []
    g = _rev_growth(d)
    if g is None:
        b.append(("매출 자료 없음", "neutral"))
    elif g >= 0.15:
        b.append((f"매출 급성장 {pct(g, sign=True)}", "good"))
    elif g >= 0.03:
        b.append((f"매출 성장 {pct(g, sign=True)}", "good"))
    elif g >= -0.03:
        b.append((f"매출 제자리 {pct(g, sign=True)}", "neutral"))
    else:
        b.append((f"매출 감소 {pct(g, sign=True)}", "warn"))

    f = d.financials
    m = f[-1].op_margin if f else None
    if m is None:
        b.append(("이익 자료 없음", "neutral"))
    elif m >= 0.15:
        b.append((f"고마진 {pct(m, digits=0)}", "good"))
    elif m >= 0:
        b.append((f"흑자 {pct(m, digits=0)}", "neutral"))
    else:
        b.append((f"적자 {pct(m, digits=0)}", "warn"))

    a = d.analyst
    buys, holds, sells = a.strong_buy + a.buy, a.hold, a.sell + a.strong_sell
    tot = buys + holds + sells
    if not tot:
        b.append(("애널리스트 없음", "neutral"))
    elif sells / tot >= 0.3:
        b.append(("매도 의견 있음", "warn"))
    elif buys / tot >= 0.6:
        b.append((f"매수 우세 {buys}/{tot}", "good"))
    else:
        b.append((f"의견 엇갈림 {buys}/{tot}", "neutral"))

    pos = _w52_pos(d)
    if pos is None:
        b.append(("52주 자료 없음", "neutral"))
    elif pos >= 0.8:
        b.append(("52주 고점 근처", "neutral"))
    elif pos <= 0.2:
        b.append(("52주 저점 근처", "warn"))
    else:
        b.append((f"52주 범위 {pos * 100:.0f}%", "neutral"))
    return b


def _first_sentence(text: str, max_len: int = 220) -> str:
    if not text:
        return ""
    # Inc. / Co. / Ltd. / Corp. / U.S. 같은 약어에서는 끊지 않음
    s = re.split(r"(?<!\bInc\.)(?<!\bCo\.)(?<!\bLtd\.)(?<!\bCorp\.)(?<!\bU\.S\.)(?<!\bNo\.)(?<=[.!?。])\s+",
                 text.strip())[0]
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def financial_comment(d: StockData) -> list[str]:
    f = d.financials
    out = []
    if len(f) >= 2 and f[-1].revenue and f[-2].revenue:
        g = f[-1].revenue / f[-2].revenue - 1
        out.append(f"{f[-1].period}년 매출 {money(f[-1].revenue, d.currency)} (전년 대비 {pct(g, sign=True)})")
    if len(f) >= 3 and f[0].revenue and f[-1].revenue and f[-1].revenue > 0 and f[0].revenue > 0:
        n = len(f) - 1
        cagr = (f[-1].revenue / f[0].revenue) ** (1 / n) - 1
        out.append(f"최근 {n}년 매출 연평균 성장률 {pct(cagr, sign=True)}")
    if f and f[-1].op_margin is not None:
        line = f"영업이익률 {pct(f[-1].op_margin)}"
        if len(f) >= 2 and f[-2].op_margin is not None:
            diff = (f[-1].op_margin - f[-2].op_margin) * 100
            line += f" (전년 {pct(f[-2].op_margin)}, {diff:+.1f}%p)"
        out.append(line)
    if f and f[-1].net_income is not None and f[-1].net_income < 0:
        out.append("최근 연도 순손실 기록 — 흑자 전환 여부 확인 필요")
    if d.pe:
        out.append(f"주가수익배수(PER) {d.pe:.1f}배" + (f" · PBR {d.pb:.1f}배" if d.pb else ""))
    if d.dividend_yield:
        out.append(f"배당수익률 약 {pct(d.dividend_yield)}")
    elif d.dividend_yield is None and d.pe:
        out.append("배당 없음 또는 정보 없음")
    return out


def analyst_summary(d: StockData) -> str:
    a = d.analyst
    parts = []
    if a.n_analysts:
        parts.append(f"애널리스트 {a.n_analysts}명")
    if a.rating:
        parts.append(f"평균 의견 '{a.rating}'")
    buys, holds, sells = a.strong_buy + a.buy, a.hold, a.sell + a.strong_sell
    if buys + holds + sells:
        parts.append(f"매수 {buys} · 보유 {holds} · 매도 {sells}")
    s = ", ".join(parts)
    if a.target_mean and d.price:
        up = a.target_mean / d.price - 1
        s += (". " if s else "") + (
            f"평균 목표주가 {money(a.target_mean, d.currency, compact=False)}로 현재가 대비 {pct(up, sign=True)}")
    return (s + ".") if s else "애널리스트 커버리지 정보가 없습니다."


# ── Claude API ───────────────────────────────────────────────────

PROMPT = """너는 한국 개인투자자용 원 페이지 종목 리포트를 쓰는 애널리스트다.
아래 JSON 데이터만 근거로, 데이터에 없는 사실은 지어내지 말고 한국어로 간결하게 작성하라.
숫자는 데이터에 있는 것만 쓰고, 투자 권유 표현은 쓰지 마라.

반드시 아래 형식의 JSON 하나만 출력하라 (코드블록 없이):
{{
  "one_liner": "회사가 무엇을 하는지 40자 이내 한 문장",
  "overview": ["회사 개요 bullet 3~4개, 각 60자 이내 (본사, 주력 사업, 고객, 특징)"],
  "flow": [["단계 제목 8자 이내", "설명 16자 이내"], ...  3~4개, 원재료/고객 → 제품 → 채널 → 수익 순으로 이 회사가 돈 버는 구조],
  "financial_comment": ["재무 해석 bullet 3~4개, 각 50자 이내"],
  "analyst_summary": "애널리스트 의견·목표주가·최근 의견 변경을 2~3문장으로 요약",
  "news_ko": ["뉴스 제목을 순서대로 한국어 한 줄로 번역/요약 (입력 뉴스 개수와 동일)"]
}}

데이터:
{data}
"""


def llm_narrative(d: StockData, api_key: Optional[str] = None,
                  model: Optional[str] = None, timeout: float = 60.0) -> Narrative:
    api_key = api_key or os.environ["ANTHROPIC_API_KEY"]
    model = model or os.environ.get("ONEPAGER_MODEL", "claude-sonnet-5-5")
    payload = {
        "name": d.ticker.name, "symbol": d.ticker.symbol, "currency": d.currency,
        "price": d.price, "market_cap": d.market_cap, "pe": d.pe, "pb": d.pb,
        "dividend_yield": d.dividend_yield, "sector": d.sector, "industry": d.industry,
        "country": d.country, "city": d.city, "employees": d.employees,
        "business_summary": d.business_summary[:2500],
        "financials": [f.__dict__ for f in d.financials],
        "analyst": {k: v for k, v in d.analyst.__dict__.items() if k != "summary"},
        "news": [n.title for n in d.news],
        "rule_based_financial_notes": financial_comment(d),
    }
    body = json.dumps({
        "model": model,
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": PROMPT.format(data=json.dumps(payload, ensure_ascii=False))}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body, method="POST",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read())
    text = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
    return parse_llm_json(text, d)


def parse_llm_json(text: str, d: StockData) -> Narrative:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("LLM 응답에서 JSON을 찾지 못함")
    j = json.loads(m.group(0))
    fallback = rule_based(d)
    flow = [tuple(x[:2]) for x in j.get("flow", []) if isinstance(x, (list, tuple)) and len(x) >= 2]
    news_ko = j.get("news_ko") or []
    if len(news_ko) != len(d.news):
        news_ko = fallback.news_ko
    return Narrative(
        one_liner=j.get("one_liner") or fallback.one_liner,
        overview=j.get("overview") or fallback.overview,
        flow=flow[:4] if len(flow) >= 3 else fallback.flow,
        financial_comment=j.get("financial_comment") or fallback.financial_comment,
        analyst_summary=j.get("analyst_summary") or fallback.analyst_summary,
        news_ko=news_ko,
        source="llm",
    )


def build(d: StockData, use_llm: Optional[bool] = None) -> Narrative:
    if use_llm is None:
        use_llm = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if use_llm:
        try:
            return llm_narrative(d)
        except Exception as e:  # 네트워크/키 오류 시 규칙 기반으로
            n = rule_based(d)
            n.source = f"rule (LLM 실패: {type(e).__name__})"
            return n
    return rule_based(d)
