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

# 그림용 이모티콘 (섹터 기본 흐름과 같은 순서)
SECTOR_ICONS = {
    "Technology": ["🔬", "💻", "🤝", "💰"], "Communication Services": ["📺", "👥", "📣", "💰"],
    "Consumer Cyclical": ["🏭", "🏬", "🛍️", "💰"], "Consumer Defensive": ["🌾", "🏭", "🛒", "💰"],
    "Healthcare": ["🔬", "📋", "🏥", "💰"], "Financial Services": ["🏦", "📊", "🤝", "💰"],
    "Industrials": ["📝", "🏗️", "🚚", "💰"], "Energy": ["🛢️", "🏭", "⛽", "💰"],
    "Basic Materials": ["⛏️", "🏭", "🔩", "💰"], "Real Estate": ["🏢", "🔑", "👥", "💰"],
    "Utilities": ["⚡", "🔌", "🏠", "💰"],
}
DEFAULT_ICONS = ["⭐", "👥", "🛒", "💰"]

# 업종별 쉬운 흐름 (이모티콘, 제목, 설명) — 자주 나오는 업종만, 나머지는 섹터 기본
INDUSTRY_FLOW = {
    "Semiconductors": [("✏️", "칩 설계", "반도체 설계·개발"), ("🏭", "생산", "자체 공장 또는 위탁"), ("📱", "고객사", "스마트폰·서버·자동차"), ("💰", "칩 판매", "개당 판매 대금")],
    "Semiconductor Equipment & Materials": [("🔧", "장비·소재 개발", "공정용 장비·소재"), ("🏭", "칩 공장", "삼성·TSMC 같은 제조사"), ("🔁", "설치·소모", "장비 설치·소재 반복 구매"), ("💰", "매출", "장비 판매 + 유지보수")],
    "Software - Application": [("💻", "앱 개발", "업무·소비자용 소프트웨어"), ("☁️", "클라우드 제공", "인터넷으로 사용"), ("👥", "기업·개인 가입", "월·연 구독"), ("💰", "구독료", "매달 반복 매출")],
    "Software - Infrastructure": [("🧱", "기반 소프트웨어", "보안·DB·클라우드 도구"), ("🏢", "기업 IT 부서", "시스템에 설치"), ("🔁", "계약 갱신", "매년 재계약"), ("💰", "라이선스·구독", "반복 매출")],
    "Internet Content & Information": [("🔍", "검색·SNS·콘텐츠", "무료 서비스"), ("👥", "이용자 모으기", "매일 쓰는 사람"), ("📣", "광고주", "이용자에게 광고"), ("💰", "광고비", "클릭·노출당 수입")],
    "Internet Retail": [("🛍️", "온라인 쇼핑몰", "상품 진열"), ("📦", "물류", "창고·배송"), ("🏠", "소비자 주문", "앱·웹 결제"), ("💰", "판매·수수료", "상품값 + 입점 수수료")],
    "Consumer Electronics": [("✏️", "제품 설계", "스마트폰·PC·가전"), ("🏭", "생산", "공장·위탁 생산"), ("🏬", "판매", "매장·온라인·통신사"), ("💰", "기기 + 서비스", "판매 대금·구독")],
    "Auto Manufacturers": [("🔩", "부품 조달", "배터리·반도체·철강"), ("🏭", "조립 공장", "자동차 생산"), ("🚗", "판매", "대리점·직판"), ("💰", "차값 + 금융", "판매·할부·서비스")],
    "Auto Parts": [("🔩", "부품 개발", "엔진·전장·차체 부품"), ("🏭", "생산", "공장에서 대량 생산"), ("🚗", "완성차 회사", "현대·토요타 등에 납품"), ("💰", "납품 대금", "계약 단가 × 물량")],
    "Biotechnology": [("🧪", "신약 연구", "후보 물질 발굴"), ("📋", "임상 시험", "1·2·3상 + 허가"), ("🏥", "출시·기술 수출", "병원 판매·라이선스"), ("💰", "약값·로열티", "성공하면 큰 매출")],
    "Drug Manufacturers - General": [("🧪", "신약 개발", "연구·임상"), ("🏭", "생산", "대량 제조"), ("🏥", "병원·약국", "처방"), ("💰", "약 판매", "특허 기간 독점")],
    "Drug Manufacturers - Specialty & Generic": [("🧪", "의약품 개발", "복제약·전문의약품"), ("🏭", "생산", "대량 제조"), ("🏥", "병원·약국", "처방·판매"), ("💰", "약 판매", "낮은 단가 × 많은 물량")],
    "Medical Devices": [("🔬", "기기 개발", "진단·수술·치료 장비"), ("📋", "허가", "FDA·식약처"), ("🏥", "병원 판매", "장비 + 소모품"), ("💰", "장비·소모품", "소모품 반복 매출")],
    "Banks - Regional": [("💵", "예금 받기", "낮은 이자로 조달"), ("🏦", "대출", "기업·가계에 빌려줌"), ("📈", "이자 차이", "대출이자 − 예금이자"), ("💰", "이자·수수료", "순이자마진")],
    "Banks - Diversified": [("💵", "예금·채권", "자금 조달"), ("🏦", "대출·투자", "기업·가계·시장"), ("💳", "카드·IB·자산관리", "수수료 사업"), ("💰", "이자 + 수수료", "두 축의 수익")],
    "Insurance - Life": [("📝", "보험 판매", "설계사·온라인"), ("💵", "보험료 받기", "매달 납입"), ("📈", "운용", "채권·주식에 투자"), ("💰", "운용수익 + 보험이익", "지급보다 많이 벌기")],
    "Insurance - Property & Casualty": [("📝", "보험 판매", "자동차·화재·배상"), ("💵", "보험료", "선불로 받음"), ("🚑", "사고 보상", "손해율 관리"), ("💰", "보험이익 + 운용", "남는 돈 투자")],
    "Asset Management": [("👥", "투자자 돈 모으기", "펀드·ETF"), ("📊", "운용", "주식·채권·대체투자"), ("📈", "운용자산 증가", "시장 상승 + 자금 유입"), ("💰", "운용 보수", "자산의 일정 %")],
    "Capital Markets": [("📊", "중개·IB", "주식 매매·상장·인수합병"), ("👥", "고객", "개인·기관·기업"), ("🔁", "거래량", "시장이 활발할수록"), ("💰", "수수료", "거래·자문 수수료")],
    "Credit Services": [("💳", "카드·결제망", "결제 서비스"), ("🏬", "가맹점", "카드 결제 받음"), ("🔁", "결제 건수", "쓸수록 늘어남"), ("💰", "수수료", "건당·금액당 수수료")],
    "Oil & Gas E&P": [("🔍", "탐사", "유전·가스전 찾기"), ("🛢️", "생산", "원유·가스 퍼올리기"), ("🚢", "판매", "정유사·발전소"), ("💰", "유가 × 생산량", "유가에 크게 좌우")],
    "Oil & Gas Refining & Marketing": [("🛢️", "원유 구매", "수입·매입"), ("🏭", "정제", "휘발유·경유·화학원료"), ("⛽", "판매", "주유소·산업체"), ("💰", "정제마진", "제품값 − 원유값")],
    "Utilities - Regulated Electric": [("⚡", "발전", "화력·원전·신재생"), ("🔌", "송전·배전", "전력망"), ("🏠", "가정·공장", "전기 사용"), ("💰", "전기요금", "정부 승인 요금")],
    "Aerospace & Defense": [("📝", "정부 수주", "국방부·항공사 계약"), ("✏️", "개발", "전투기·미사일·엔진"), ("🏭", "생산·납품", "수년간 인도"), ("💰", "계약 대금 + 정비", "장기 안정 매출")],
    "Specialty Industrial Machinery": [("📝", "수주", "공장·플랜트 주문"), ("🏭", "제작", "기계·설비 생산"), ("🔧", "설치·정비", "부품·서비스"), ("💰", "장비 + 서비스", "판매 대금·유지보수")],
    "Electrical Equipment & Parts": [("📝", "수주", "전력회사·공장·데이터센터"), ("🏭", "제작", "변압기·전선·배전반"), ("🔌", "설치", "전력망·건물"), ("💰", "납품 대금", "수주 잔고가 핵심")],
    "Engineering & Construction": [("📝", "수주", "건물·도로·플랜트"), ("🏗️", "시공", "몇 년에 걸쳐 공사"), ("🔑", "준공·인도", "발주처에 넘김"), ("💰", "공사 대금", "진행률만큼 매출")],
    "Marine Shipping": [("🚢", "선박 보유", "컨테이너·벌크·유조선"), ("📦", "화물 운송", "바다 건너 운반"), ("🌏", "화주", "수출입 기업"), ("💰", "운임", "운임 지수에 좌우")],
    "Airlines": [("✈️", "항공기", "구매·리스"), ("🎫", "항공권 판매", "여객·화물"), ("🌏", "운항", "노선 운영"), ("💰", "운임", "탑승률·유가가 핵심")],
    "Restaurants": [("🥩", "식자재 구매", "원재료 조달"), ("🍔", "조리·매장", "직영·가맹점"), ("🧑‍🤝‍🧑", "손님", "방문·배달"), ("💰", "음식값·가맹비", "매장 수 × 매장당 매출")],
    "Specialty Retail": [("📦", "상품 기획·매입", "특정 분야 상품"), ("🏬", "매장·온라인", "판매 채널"), ("🛍️", "소비자", "구매"), ("💰", "판매 대금", "매장 수 × 매장당 매출")],
    "Discount Stores": [("📦", "대량 매입", "싸게 많이 사기"), ("🏬", "대형 매장", "창고형·할인점"), ("🛒", "소비자", "생필품 구매"), ("💰", "판매 + 회비", "박리다매")],
    "Packaged Foods": [("🌾", "원재료", "곡물·고기·설탕"), ("🏭", "가공", "식품 공장"), ("🛒", "유통", "마트·편의점"), ("💰", "판매 대금", "브랜드 힘으로 가격 유지")],
    "Beverages - Non-Alcoholic": [("🌱", "원액·원료", "브랜드 원액"), ("🏭", "병입", "공장·제휴 병입사"), ("🛒", "유통", "마트·식당·자판기"), ("💰", "음료 판매", "전 세계 반복 구매")],
    "Household & Personal Products": [("🧴", "제품 개발", "세제·화장품·위생용품"), ("🏭", "생산", "대량 제조"), ("🛒", "유통", "마트·온라인"), ("💰", "판매 대금", "매일 쓰는 반복 구매")],
    "Electronic Gaming & Multimedia": [("🎮", "게임 개발", "모바일·PC·콘솔"), ("🌏", "출시", "앱스토어·스팀"), ("👥", "이용자", "다운로드·접속"), ("💰", "아이템·판매", "과금·패키지 판매")],
    "Entertainment": [("🎬", "콘텐츠 제작", "영화·드라마·음악"), ("📺", "배급", "극장·OTT·방송"), ("👥", "관객·구독자", "시청"), ("💰", "관람료·판권·구독", "흥행에 좌우")],
    "Telecom Services": [("📡", "통신망 구축", "5G·광케이블"), ("📱", "가입자", "휴대폰·인터넷"), ("🔁", "매달 요금", "약정·결합"), ("💰", "통신 요금", "안정적 반복 매출")],
    "Information Technology Services": [("🧑‍💻", "IT 인력", "개발자·컨설턴트"), ("🏢", "기업 고객", "시스템 구축 의뢰"), ("🔧", "구축·운영", "프로젝트·유지보수"), ("💰", "용역 대금", "인력 × 시간")],
    "Communication Equipment": [("✏️", "장비 개발", "통신·네트워크 장비"), ("🏭", "생산", "제조"), ("📡", "통신사·기업", "망 구축에 사용"), ("💰", "장비 판매", "투자 주기에 좌우")],
    "Electronic Components": [("✏️", "부품 개발", "기판·센서·커넥터"), ("🏭", "생산", "대량 제조"), ("📱", "완제품 회사", "스마트폰·차·서버"), ("💰", "부품 판매", "고객사 생산량에 좌우")],
    "Steel": [("⛏️", "원료", "철광석·석탄·고철"), ("🏭", "제철", "쇳물 → 철판"), ("🏗️", "고객", "건설·자동차·조선"), ("💰", "판매 대금", "철강 가격에 좌우")],
    "Chemicals": [("🛢️", "원료", "나프타·가스"), ("🏭", "화학 공정", "기초·중간 소재"), ("🧴", "고객", "플라스틱·섬유·전자"), ("💰", "판매 대금", "제품값 − 원료값")],
    "Specialty Chemicals": [("🧪", "특수 소재 개발", "고기능 화학제품"), ("🏭", "생산", "소량 고부가"), ("🔌", "고객", "반도체·배터리·디스플레이"), ("💰", "판매 대금", "높은 마진")],
    "Solar": [("☀️", "태양광 소재·모듈", "셀·패널 제조"), ("🏗️", "발전소 설치", "주택·대형 발전소"), ("⚡", "전기 생산", "전력회사에 판매"), ("💰", "모듈·전력 판매", "정책·금리에 민감")],
    "REIT - Industrial": [("🏢", "물류창고 보유", "건물 매입·개발"), ("🔑", "임대", "물류·제조 기업"), ("🔁", "장기 계약", "매년 임대료 인상"), ("💰", "임대료 → 배당", "이익 대부분 배당")],
    "Shell Companies": [("💼", "자금 모집", "상장해서 돈 모으기"), ("🔍", "합병 대상 찾기", "비상장 기업 물색"), ("🤝", "합병", "주주 승인"), ("💰", "합병 후 사업", "합병 전엔 매출 없음")],
}


def easy_flow(d: StockData) -> list[tuple[str, str, str]]:
    if d.industry in INDUSTRY_FLOW:
        return INDUSTRY_FLOW[d.industry]
    base = SECTOR_FLOW.get(d.sector, DEFAULT_FLOW)
    icons = SECTOR_ICONS.get(d.sector, DEFAULT_ICONS)
    return [(icons[i % len(icons)], t, x) for i, (t, x) in enumerate(base)]

MARKET_KO = {"US": "미국", "KR": "한국", "JP": "일본", "CN": "중국", "HK": "홍콩"}


# ── 규칙 기반 ────────────────────────────────────────────────────

def rule_based(d: StockData) -> Narrative:
    sector = SECTOR_KO.get(d.sector, d.sector)
    country = COUNTRY_KO.get(d.country, d.country) or MARKET_KO.get(d.ticker.market, "")
    industry = d.industry_ko or d.industry
    desc = clean_desc(d.desc_ko) or d.business_summary_ko or d.business_summary
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
        if d.desc_ko or d.business_summary_ko:
            sents = re.split(r"(?<=[.다요])\s+", desc.strip())
            overview.append(" ".join(sents[:3])[:420])
        else:
            overview.append(first)

    return Narrative(
        one_liner=one,
        overview=overview,
        flow=easy_flow(d),
        financial_comment=financial_comment(d),
        analyst_summary=analyst_summary(d),
        news_ko=[n.title for n in d.news],
        source="rule",
        summary3=summary3(d, country, sector, first),
        badges=badges(d),
    )


def clean_desc(t: str) -> str:
    """네이버·와이즈리포트 개요 정리: <br>·기준일 꼬리표 제거, '동사는' → 회사."""
    if not t:
        return ""
    t = re.sub(r"<br\s*/?>", " ", t)
    t = re.sub(r"기업개요\s*\[기준:[^\]]*\]\s*", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^동사는\s*", "", t)
    t = re.sub(r"(있음|하였음|되었음|하고 있음|임)\.", lambda m: {"있음": "있습니다", "하였음": "했습니다", "되었음": "되었습니다", "하고 있음": "하고 있습니다", "임": "입니다"}[m.group(1)] + ".", t)
    t = re.sub(r"(있음|하였음|임)$", lambda m: {"있음": "있습니다", "하였음": "했습니다", "임": "입니다"}[m.group(1)] + ".", t)
    return t


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
        who = f"애널리스트 {a.n_analysts}명" if a.n_analysts else "애널리스트"
        line = (f"{who} 평균 '{a.rating}' · " if a.rating else f"{who} · ") + f"평균 목표가는 현재가보다 {pct(up, sign=True)}"
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
