"""종목명/코드 → 야후 파이낸스 심볼 변환.

지원 시장: 미국(US), 한국(KR), 일본(JP), 중국 본토(CN), 홍콩(HK)

입력 예시
  - "삼성전자", "애플", "텐센트", "토요타"      → 내장 별칭 사전
  - "AAPL", "FIVE"                              → 미국
  - "005930" / "005930.KS" / "247540.KQ"        → 한국 (6자리 숫자는 기본 한국)
  - "7203" / "7203.T"                           → 일본 (4자리 숫자는 기본 일본)
  - "0700.HK" / "HK:700"                        → 홍콩
  - "600519.SS" / "CN:600519" / "000858.SZ"     → 중국
  - 그 외 이름은 야후 파이낸스 검색 API로 찾음
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, Optional

from .models import Ticker

SUFFIX_MARKET = {
    "KS": "KR", "KQ": "KR",
    "T": "JP",
    "HK": "HK",
    "SS": "CN", "SZ": "CN",
}

# 자주 찾는 종목의 한국어/영어 별칭. 키는 normalize() 결과(소문자, 공백 제거).
ALIASES: dict[str, tuple[str, str, str]] = {}


def _add(names: list[str], symbol: str, display: str, market: str) -> None:
    for n in names:
        ALIASES[normalize(n)] = (symbol, display, market)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).strip().lower()
    return re.sub(r"[\s\-_.,·()]+", "", text)


# ── 미국 ────────────────────────────────────────────
_add(["애플", "apple"], "AAPL", "애플", "US")
_add(["마이크로소프트", "마소", "microsoft"], "MSFT", "마이크로소프트", "US")
_add(["엔비디아", "nvidia"], "NVDA", "엔비디아", "US")
_add(["알파벳", "구글", "google", "alphabet"], "GOOGL", "알파벳", "US")
_add(["아마존", "amazon"], "AMZN", "아마존", "US")
_add(["메타", "페이스북", "meta"], "META", "메타 플랫폼스", "US")
_add(["테슬라", "tesla"], "TSLA", "테슬라", "US")
_add(["브로드컴", "broadcom"], "AVGO", "브로드컴", "US")
_add(["넷플릭스", "netflix"], "NFLX", "넷플릭스", "US")
_add(["코스트코", "costco"], "COST", "코스트코", "US")
_add(["파이브빌로우", "파이브 빌로우", "five below"], "FIVE", "파이브 빌로우", "US")
_add(["팔란티어", "palantir"], "PLTR", "팔란티어", "US")
_add(["버크셔해서웨이", "버크셔", "berkshire"], "BRK-B", "버크셔 해서웨이", "US")
_add(["일라이릴리", "릴리", "eli lilly"], "LLY", "일라이 릴리", "US")
_add(["코카콜라", "coca cola"], "KO", "코카콜라", "US")
_add(["amd", "에이엠디"], "AMD", "AMD", "US")
_add(["인텔", "intel"], "INTC", "인텔", "US")
_add(["마이크론", "micron"], "MU", "마이크론", "US")
_add(["tsmc", "티에스엠씨"], "TSM", "TSMC (ADR)", "US")
# ── 한국 ────────────────────────────────────────────
_add(["삼성전자", "삼전", "samsung electronics"], "005930.KS", "삼성전자", "KR")
_add(["sk하이닉스", "하이닉스", "sk hynix"], "000660.KS", "SK하이닉스", "KR")
_add(["lg에너지솔루션", "엘지에너지솔루션", "엔솔"], "373220.KS", "LG에너지솔루션", "KR")
_add(["삼성바이오로직스", "삼바"], "207940.KS", "삼성바이오로직스", "KR")
_add(["현대차", "현대자동차", "hyundai motor"], "005380.KS", "현대차", "KR")
_add(["기아"], "000270.KS", "기아", "KR")
_add(["네이버", "naver"], "035420.KS", "NAVER", "KR")
_add(["카카오", "kakao"], "035720.KS", "카카오", "KR")
_add(["셀트리온", "celltrion"], "068270.KS", "셀트리온", "KR")
_add(["포스코홀딩스", "posco홀딩스", "포스코"], "005490.KS", "POSCO홀딩스", "KR")
_add(["한화에어로스페이스", "한화에어로"], "012450.KS", "한화에어로스페이스", "KR")
_add(["hd현대중공업", "현대중공업"], "329180.KS", "HD현대중공업", "KR")
_add(["kb금융"], "105560.KS", "KB금융", "KR")
_add(["에코프로비엠"], "247540.KQ", "에코프로비엠", "KR")
_add(["알테오젠"], "196170.KQ", "알테오젠", "KR")
# ── 일본 ────────────────────────────────────────────
_add(["토요타", "도요타", "toyota"], "7203.T", "도요타자동차", "JP")
_add(["소니", "sony"], "6758.T", "소니그룹", "JP")
_add(["닌텐도", "nintendo"], "7974.T", "닌텐도", "JP")
_add(["소프트뱅크그룹", "소프트뱅크", "softbank"], "9984.T", "소프트뱅크그룹", "JP")
_add(["키엔스", "keyence"], "6861.T", "키엔스", "JP")
_add(["도쿄일렉트론", "tokyo electron"], "8035.T", "도쿄일렉트론", "JP")
_add(["미쓰비시ufj", "mufg"], "8306.T", "미쓰비시UFJ파이낸셜그룹", "JP")
_add(["패스트리테일링", "유니클로", "fast retailing"], "9983.T", "패스트리테일링", "JP")
_add(["어드밴테스트", "advantest"], "6857.T", "어드밴테스트", "JP")
# ── 홍콩 ────────────────────────────────────────────
_add(["텐센트", "tencent"], "0700.HK", "텐센트", "HK")
_add(["알리바바", "alibaba"], "9988.HK", "알리바바 (홍콩)", "HK")
_add(["메이투안", "meituan"], "3690.HK", "메이투안", "HK")
_add(["샤오미", "xiaomi"], "1810.HK", "샤오미", "HK")
_add(["byd", "비야디"], "1211.HK", "BYD (홍콩)", "HK")
_add(["hsbc"], "0005.HK", "HSBC 홀딩스", "HK")
_add(["팝마트", "pop mart"], "9992.HK", "팝마트", "HK")
# ── 중국 본토 ───────────────────────────────────────
_add(["귀주모태", "구이저우마오타이", "마오타이", "moutai"], "600519.SS", "구이저우 마오타이", "CN")
_add(["catl", "닝더스다이"], "300750.SZ", "CATL", "CN")
_add(["오량액", "우량예"], "000858.SZ", "우량예", "CN")
_add(["중국평안", "핑안보험"], "601318.SS", "중국평안보험", "CN")


class ResolveError(ValueError):
    pass


def _from_code(q: str) -> Optional[Ticker]:
    raw = q.strip().upper().replace(" ", "")

    # "HK:700", "CN:600519", "JP:7203", "KR:005930", "US:AAPL"
    m = re.fullmatch(r"(US|KR|JP|CN|HK):(.+)", raw)
    if m:
        market, code = m.groups()
        if market == "US":
            return Ticker(code, code, "US")
        if market == "KR":
            return Ticker(f"{code.zfill(6)}.KS", code, "KR")
        if market == "JP":
            return Ticker(f"{code}.T", code, "JP")
        if market == "HK":
            return Ticker(f"{code.zfill(4)}.HK", code, "HK")
        if market == "CN":
            sfx = "SS" if code.startswith(("6", "9")) else "SZ"
            return Ticker(f"{code}.{sfx}", code, "CN")

    # 접미사 포함 심볼
    m = re.fullmatch(r"([0-9A-Z]+)\.(KS|KQ|T|HK|SS|SZ)", raw)
    if m:
        code, sfx = m.groups()
        if sfx == "HK":
            code = code.zfill(4)
        return Ticker(f"{code}.{sfx}", code, SUFFIX_MARKET[sfx])

    if re.fullmatch(r"\d{6}", raw):          # 6자리 → 한국 (중국은 CN: 접두사 사용)
        return Ticker(f"{raw}.KS", raw, "KR")
    if re.fullmatch(r"\d{4}", raw):          # 4자리 → 일본
        return Ticker(f"{raw}.T", raw, "JP")
    if re.fullmatch(r"\d{1,5}", raw):        # 1~5자리 → 홍콩
        return Ticker(f"{raw.zfill(4)}.HK", raw, "HK")
    if re.fullmatch(r"[A-Z]{1,5}([.-][A-Z])?", raw) and q.strip().isupper():
        return Ticker(raw.replace(".", "-"), raw, "US")
    return None


def market_of(symbol: str) -> str:
    if "." in symbol:
        return SUFFIX_MARKET.get(symbol.rsplit(".", 1)[1].upper(), "US")
    return "US"


def resolve(query: str, search: Optional[Callable[[str], list[dict]]] = None) -> Ticker:
    """종목명 또는 코드를 Ticker로 변환. search는 야후 검색 함수(테스트에서 교체 가능)."""
    if not query or not query.strip():
        raise ResolveError("종목명을 입력하세요.")

    hit = ALIASES.get(normalize(query))
    if hit:
        symbol, display, market = hit
        return Ticker(symbol, display, market)

    t = _from_code(query)
    if t:
        return t

    search = search or yahoo_search
    for q in [query.strip()]:
        for item in search(q):
            sym = item.get("symbol", "")
            if not sym or item.get("quoteType", "EQUITY") not in ("EQUITY", "ETF"):
                continue
            mkt = market_of(sym)
            if "." in sym and sym.rsplit(".", 1)[1].upper() not in SUFFIX_MARKET:
                continue  # 지원하지 않는 거래소(런던, 프랑크푸르트 등) 제외
            name = item.get("longname") or item.get("shortname") or sym
            return Ticker(sym, name, mkt, item.get("exchange", ""))
    raise ResolveError(f"'{query}' 종목을 찾지 못했습니다. 종목코드(예: AAPL, 005930, 7203.T, 0700.HK)로 입력해 보세요.")


def yahoo_search(query: str) -> list[dict]:
    try:
        import yfinance as yf
        return list(yf.Search(query, max_results=10, news_count=0).quotes)
    except Exception:
        return []
