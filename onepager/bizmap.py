"""회사가 하는 일 그림 — 한국어 회사 설명에서 제품·고객·지역을 뽑아 그림(SVG)으로.

  만드는 것(아이콘) ──▶ 회사 ──▶ 사는 사람(아이콘)
                ◀── 💰 매출 ──

외부 호출 없음. 설명이 없으면 업종 기본 그림.
"""
from __future__ import annotations

import re
from html import escape as _e

# ── 키워드 → 아이콘 (위에서부터 먼저 맞는 것) ─────────────────────────
PRODUCT_ICONS = [
    (r"HBM|DRAM|D램|낸드|NAND|메모리", "💾"), (r"반도체|칩|웨이퍼|파운드리|SoC|GPU|CPU|프로세서", "🔲"),
    (r"스마트폰|휴대폰|모바일 기기|아이폰|iPhone", "📱"), (r"TV|텔레비전", "📺"), (r"냉장고|세탁기|에어컨|가전", "🧊"),
    (r"OLED|LCD|디스플레이|패널", "🖥️"), (r"게임", "🎮"), (r"노트북|PC|컴퓨터|서버|Mac", "💻"), (r"태블릿|iPad", "📲"),
    (r"웨어러블|시계|워치|이어폰|헤드폰|오디오|스피커", "🎧"), (r"카메라|렌즈|이미지 ?센서", "📷"), (r"센서|레이더|라이다", "📡"),
    (r"배터리|2차전지|이차전지|양극재|음극재|전해질|분리막", "🔋"), (r"전기차|자동차|차량|승용차|트럭|SUV", "🚗"),
    (r"전장|자동차 부품|브레이크|타이어|엔진", "⚙️"), (r"로봇|자동화", "🤖"), (r"드론|항공기|비행기|항공우주|위성|로켓", "🛰️"),
    (r"선박|조선|컨테이너선|LNG선|해운", "🚢"), (r"방산|무기|미사일|탄약|방위", "🛡️"),
    (r"항체|신약|의약품|치료제|약물|제약|바이오시밀러|복제약", "💊"), (r"백신", "💉"), (r"세포|유전자|DNA|RNA|단백질|줄기세포", "🧫"),
    (r"진단|검사|키트|시약", "🔬"), (r"의료기기|임플란트|수술|카테터|스텐트|초음파|내시경", "🩺"), (r"병원|의료 서비스|클리닉|요양", "🏥"),
    (r"화장품|스킨케어|뷰티|미용", "💄"), (r"의류|패션|신발|가방|명품|잡화|섬유", "👕"),
    (r"라면|식품|과자|스낵|간식|음식|육류|유제품|우유|커피|설탕|곡물", "🍜"), (r"음료|주류|맥주|와인|소주|생수", "🥤"),
    (r"담배", "🚬"), (r"생활용품|세제|기저귀|위생", "🧴"), (r"가구|인테리어|침대", "🛋️"), (r"장난감|완구", "🧸"),
    (r"게임", "🎮"), (r"영화|드라마|콘텐츠|방송|엔터테인먼트|애니메이션|웹툰", "🎬"), (r"음악|음반|아이돌|공연", "🎵"),
    (r"광고|마케팅", "📣"), (r"검색|포털|SNS|소셜|메신저|커뮤니티", "🔍"), (r"클라우드", "☁️"), (r"인공지능|AI", "🧠"),
    (r"보안|사이버", "🔐"), (r"데이터센터|데이터|데이터베이스", "🗄️"), (r"소프트웨어|플랫폼|앱|솔루션|SaaS|운영체제|iOS", "💻"),
    (r"결제|카드|핀테크|페이", "💳"), (r"대출|예금|은행", "🏦"), (r"보험", "☂️"), (r"증권|투자|자산운용|펀드|중개", "📈"),
    (r"부동산|임대|오피스|리츠|REIT|주택|아파트", "🏢"), (r"건설|시공|플랜트|토목|인프라", "🏗️"),
    (r"철강|강판|강관|금속|알루미늄|구리|니켈|아연", "🔩"), (r"화학|소재|플라스틱|수지|필름|석유화학|코팅", "🧪"),
    (r"원유|석유|정유|휘발유|경유|윤활유", "🛢️"), (r"가스|LNG|LPG", "🔥"), (r"태양광|태양전지|모듈", "☀️"), (r"풍력", "🌬️"),
    (r"원자력|원전|SMR", "⚛️"), (r"전력|전기|변압기|전선|송전|배전|발전", "⚡"), (r"수소|연료전지", "💧"),
    (r"금광|금 채굴|은광|광산|광물|채굴|석탄|리튬|희토류", "⛏️"), (r"비료|농업|농산물|종자|사료", "🌾"),
    (r"물류|택배|운송|배송|창고", "📦"), (r"항공|여객", "✈️"), (r"철도|기차", "🚆"),
    (r"호텔|리조트|여행|관광|카지노", "🏨"), (r"교육|학습|학원", "📚"), (r"통신|5G|네트워크|인터넷|광케이블", "📶"),
    (r"마트|매장|소매|유통|편의점|백화점|쇼핑|이커머스|전자상거래|온라인 쇼핑", "🛒"),
    (r"장비|기계|설비|부품|공구|모터|펌프|밸브", "⚙️"), (r"소모품", "🧪"), (r"기판|PCB|커넥터|케이블|콘덴서|MLCC", "🔌"),
    (r"인수|합병|스팩|SPAC|블랭크", "🤝"), (r"지주|투자회사|자회사 관리", "🏛️"),
    (r"기술|특허|IP|라이선스", "💡"), (r"액세서리|주변기기", "🎒"), (r"네트워크|처리 서비스|프로세싱", "🌐"), (r"서비스", "🛎️"),
]

CUSTOMER_RULES = [
    (r"병원|의료기관|의사|환자", "🏥", "병원·환자"), (r"제약|바이오 ?기업|연구소|연구기관|대학|세포 분석|항체|임상|신약 개발", "🔬", "제약사·연구소"),
    (r"자동차 ?(제조|회사|업체)|완성차|OEM", "🚗", "자동차 회사"), (r"데이터센터|클라우드 ?(사업자|기업)|하이퍼스케일", "🗄️", "데이터센터"),
    (r"스마트폰 ?제조(사|업체)|전자 ?제조(사|업체)|IT 기업", "📱", "전자 제조사"), (r"반도체 ?(제조|업체|기업|공장)", "🔲", "반도체 회사"),
    (r"정부|국방|군|공공기관|지자체", "🏛️", "정부·국방"), (r"통신사|통신 사업자", "📶", "통신사"), (r"항공사", "✈️", "항공사"),
    (r"건설사|건설 ?(업체|회사)", "🏗️", "건설사"), (r"전력 ?회사|유틸리티|발전소", "⚡", "전력회사"), (r"광고주", "📣", "광고주"),
    (r"소매업체|유통업체|(?<!스)마트(?!폰)|리테일러|대리점", "🏬", "유통업체"), (r"금융기관|은행", "🏦", "금융기관"),
    (r"기업 고객|기업용|B2B|기업들|(?<!생)산업체|제조업체|기업에|기업,|, ?기업", "🏢", "기업 고객"),
    (r"소비자|개인|고객|이용자|가정|가입자|회원|관객|플레이어", "👨‍👩‍👧", "소비자"),
]

SECTOR_DEFAULT = {   # (회사 아이콘, 기본 제품 아이콘·이름, 기본 고객)
    "Technology": ("💻", ("💻", "기술 제품"), ("🏢", "기업 고객")),
    "Communication Services": ("📡", ("📺", "서비스·콘텐츠"), ("👨‍👩‍👧", "이용자")),
    "Consumer Cyclical": ("🛍️", ("🛍️", "소비재"), ("👨‍👩‍👧", "소비자")),
    "Consumer Defensive": ("🛒", ("🍜", "생활 필수품"), ("👨‍👩‍👧", "소비자")),
    "Healthcare": ("⚕️", ("💊", "의약·의료"), ("🏥", "병원·환자")),
    "Financial Services": ("🏦", ("💳", "금융 상품"), ("👨‍👩‍👧", "개인·기업")),
    "Industrials": ("🏭", ("⚙️", "산업재"), ("🏢", "기업 고객")),
    "Energy": ("🛢️", ("🛢️", "에너지"), ("🏢", "산업·소비자")),
    "Basic Materials": ("⛏️", ("🧪", "소재"), ("🏭", "제조업체")),
    "Real Estate": ("🏢", ("🏢", "부동산"), ("🏢", "임차인")),
    "Utilities": ("⚡", ("⚡", "전기·가스"), ("🏠", "가정·공장")),
}

REGIONS = [
    (r"한국|국내", "🇰🇷", "한국"), (r"미국|북미", "🇺🇸", "미국"), (r"중국", "🇨🇳", "중국"), (r"일본", "🇯🇵", "일본"),
    (r"홍콩", "🇭🇰", "홍콩"), (r"대만", "🇹🇼", "대만"), (r"유럽|독일|영국|프랑스", "🇪🇺", "유럽"), (r"인도", "🇮🇳", "인도"),
    (r"동남아|베트남|싱가포르|인도네시아|태국", "🌏", "동남아"), (r"전 ?세계|국제적|글로벌|해외|세계 각국", "🌍", "전 세계"),
]

VERBS = r"(?:생산|제조|판매|개발|제공|운영|공급|설계|유통|서비스|연구|수출|수입|취급|임대|시공|건조|채굴|정제)"
STOP = re.compile(r"^(동사|당사|이 회사|회사|그|및|등|기타|관련|다양한|주요|각종|자회사|종속회사|함께|통해|전 세계적으로|국제적으로|중국 및|미국 및)$")


CUT = re.compile(r".*(?:도록|위해|위한|하는|되는|있는|하며|하고|하여|해서|으로서|에게|에서는|대상으로|상대로|통해)\s*")
HEAD = re.compile(r"[\w&.\-]+\s*(?:부문|사업부|부문에서|사업)?(?:은|는)\s+")
NOT_PRODUCT = re.compile(r"^(?:개인|소비자|고객|기업|정부|금융기관|한국|미국|중국|일본|유럽|홍콩|대만|국내|해외|글로벌|전 세계|국제|아시아|북미)$")


def _clean(t: str) -> str:
    t = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", t).strip()
    t = re.sub(r"^(또한|그리고|주로|자회사와 함께|중국 및 국제적으로|국제적으로|전 세계적으로|미국에서|한국에서|다양한|각종|주요)\s*", "", t)
    t = re.sub(r"\s*(등의|등을|등|분야의|분야|관련|의|을|를|은|는|이|가|으로|로|에|과|와)$", "", t.strip())
    t = re.sub(r"^\S+(은|는)\s+", "", t)            # 'SDC는 OLED 패널' → 'OLED 패널'
    t = re.sub(r"^(등의|등|기타)\s+", "", t)
    t = re.sub(r"(을|를)\s.*$", "", t)
    t = t.strip(" ,.·-")
    words = t.split()
    if len(t) > 12 and len(words) > 2:
        t = " ".join(words[-2:])                       # 긴 이름은 끝 두 단어 (핵심 명사)
    return t


def products(text: str, limit: int = 5) -> list[tuple[str, str]]:
    """설명에서 '무엇을 (생산|판매|제공…)' 의 목적어를 뽑아 (아이콘, 이름) 목록."""
    if not text:
        return []
    text = re.sub(r"<br\s*/?>", ". ", text)
    objs = re.findall(r"([^.。:;]{2,160}?)(?:을|를)\s*(?:주로\s*)?(?:[가-힣]+,\s*)*(?:[가-힣]+\s*및\s*)?" + VERBS, text)
    objs += re.findall(r"([^.。:;]{2,80}?)\s*(?:전문 ?기업|전문 ?업체|제조 ?기업|제조업체|기술 ?회사로|전문 ?회사)", text)
    objs += re.findall(r"(?:카테고리|제품|서비스|사업)(?:은|는)\s*([^.。]{2,120}?)(?:을|를)?\s*포함", text)
    items, seen = [], set()
    chunks = []
    for o in objs:
        for c in HEAD.split(o):                      # 'DX 부문은 TV, 냉장고, 스마트폰을, DS 부문은 …' → 부문별로
            c = CUT.sub("", c) if CUT.search(c) else c
            if c.strip():
                chunks.append(c)
    for o in chunks:
        for part in re.split(r",|·|/| 및 | 와 | 과 |와 |과 |\s등의?\s| 그리고 ", o):
            p = _clean(part)
            p = re.sub(r"^(글로벌|종합|대형|선도적인|선도|대표적인|세계적인)\s+", "", p)
            if not p or len(p) < 2 or len(p) > 16 or STOP.match(p) or NOT_PRODUCT.match(p):
                continue
            if re.search(r"\d{4}년|설립|상장|보유|종속|있음|하였|되었|합니다|있습니다|기업$|회사$|업체$|^[은는이가을를으로의에]", p):
                continue
            k = p.lower()
            if k in seen:
                continue
            seen.add(k)
            items.append(p)
    out = []
    for p in items:
        icon = next((ic for pat, ic in PRODUCT_ICONS if re.search(pat, p, re.I)), "📦")
        out.append((icon, p))
    out.sort(key=lambda x: x[0] == "📦")
    known = [x for x in out if x[0] != "📦"]
    if len(known) >= 3:
        out = known
    # 같은 아이콘이 너무 많으면 앞의 것만 (게임 게임 게임 …)
    res, cnt = [], {}
    for ic, nm in out:
        cnt[ic] = cnt.get(ic, 0) + 1
        if cnt[ic] <= 2:
            res.append((ic, nm))
    return res[:limit]


CONSUMER_ICONS = set("📱📺🧊🎧💄👕🍜🥤🎮🛋️🧸🚗🎬🎵🏨📚🛒💳🚬🧴📲💻")
B2B_ICONS = set("💾🔲⚙️🧪🔩🖥️🔌🤖🏗️🛢️⛏️🌾")


def customers(text: str, sector: str, prods=None, limit: int = 3) -> list[tuple[str, str]]:
    out, seen = [], set()
    for pat, ic, name in [(r"게임|플레이어|게이머", "🎮", "게이머")] + CUSTOMER_RULES:
        if text and re.search(pat, text) and name not in seen:
            seen.add(name)
            out.append((ic, name))
    icons = [p[0] for p in (prods or [])]
    if any(i in CONSUMER_ICONS for i in icons) and "소비자" not in seen and "게이머" not in seen:
        out.append(("👨‍👩‍👧", "소비자"))
        seen.add("소비자")
    if any(i in B2B_ICONS for i in icons) and not ({"기업 고객", "전자 제조사", "반도체 회사", "자동차 회사", "제약사·연구소", "데이터센터"} & seen):
        out.append(("🏢", "기업 고객"))
    if not out:
        out = [SECTOR_DEFAULT.get(sector, ("", None, ("👥", "고객")))[2]]
    return out[:limit]


def regions(text: str, market: str, limit: int = 4) -> list[tuple[str, str]]:
    out = []
    for pat, fl, name in REGIONS:
        if text and re.search(pat, text):
            out.append((fl, name))
    if not out:
        home = {"US": ("🇺🇸", "미국"), "KR": ("🇰🇷", "한국"), "JP": ("🇯🇵", "일본"), "CN": ("🇨🇳", "중국"), "HK": ("🇭🇰", "홍콩")}.get(market)
        if home:
            out = [home]
    return out[:limit]


def _short(t: str, n: int) -> str:
    """한글 1칸, 영문·숫자 0.6칸으로 세서 자르기"""
    w = lambda c: 0.6 if ord(c) < 128 else 1.0
    if sum(w(c) for c in t) <= n:
        return t
    out, tot = "", 0.0
    for c in t:
        if tot + w(c) > n - 1:
            break
        out += c
        tot += w(c)
    return out.rstrip() + "…"


def svg(name: str, sector: str, prods, custs, regs, money: str) -> str:
    comp_icon = SECTOR_DEFAULT.get(sector, ("🏭",))[0]
    if not prods:
        d = SECTOR_DEFAULT.get(sector)
        prods = [d[1]] if d else [("📦", "제품·서비스")]
    W, rowh, top = 340, 66, 34
    n = max(len(prods), len(custs), 2)
    body = n * rowh
    H = top + body + 64 + (22 if regs else 0)
    cy = top + body / 2 - 8
    xL, xC, xR = 56, 170, 284
    s = [f'<svg viewBox="0 0 {W} {H}" class="bm" role="img" aria-label="{_e(name)} 사업 그림">',
         '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
         '<path d="M0,0 L10,5 L0,10 z" fill="#7d8aa0"/></marker>'
         '<marker id="am" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
         '<path d="M0,0 L10,5 L0,10 z" fill="#1d8a55"/></marker>'
         '<radialGradient id="hub" cx=".35" cy=".3" r=".9"><stop offset="0" stop-color="#3a6fd0"/><stop offset="1" stop-color="#14284b"/></radialGradient>'
         '<linearGradient id="bgL" x1="0" x2="1"><stop offset="0" stop-color="#eef3fb"/><stop offset="1" stop-color="#eef3fb" stop-opacity="0"/></linearGradient>'
         '<linearGradient id="bgR" x1="1" x2="0"><stop offset="0" stop-color="#eff7ea"/><stop offset="1" stop-color="#eff7ea" stop-opacity="0"/></linearGradient></defs>',
         f'<rect x="4" y="{top - 6}" width="120" height="{body}" rx="16" fill="url(#bgL)"/>',
         f'<rect x="{W - 124}" y="{top - 6}" width="120" height="{body}" rx="16" fill="url(#bgR)"/>',
         f'<text x="{xL}" y="20" text-anchor="middle" class="bm-h">만드는 것 · 하는 일</text>',
         f'<text x="{xR}" y="20" text-anchor="middle" class="bm-h">누가 사나</text>']
    hubR = 38

    def node(x, y, ic, label, fill, stroke):
        return (f'<circle cx="{x}" cy="{y:.1f}" r="21" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
                f'<text x="{x}" y="{y + 1:.1f}" text-anchor="middle" class="bm-i">{_e(ic)}</text>'
                f'<text x="{x}" y="{y + 36:.1f}" text-anchor="middle" class="bm-l">{_e(_short(label, 9))}</text>')

    np_ = len(prods[:n])
    for i, (ic, label) in enumerate(prods[:n]):
        y = top + 16 + i * (body / np_) + (body / np_ - rowh) / 2
        # 회사 원 가장자리까지 부드러운 곡선
        s.append(f'<path d="M{xL + 23},{y:.1f} C{xL + 60},{y:.1f} {xC - 70},{cy:.1f} {xC - hubR - 2},{cy:.1f}" fill="none" stroke="#c3ccda" stroke-width="1.6"/>')
        s.append(node(xL, y, ic, label, "#fff", "#c9d6ec"))
    s.append(f'<path d="M{xC - hubR - 14},{cy:.1f} L{xC - hubR - 1},{cy:.1f}" stroke="#7d8aa0" stroke-width="1.6" marker-end="url(#ah)"/>')
    nc = len(custs[:n])
    for i, (ic, label) in enumerate(custs[:n]):
        y = top + 16 + i * (body / nc) + (body / nc - rowh) / 2
        s.append(f'<path d="M{xC + hubR + 2},{cy:.1f} C{xC + 70},{cy:.1f} {xR - 60},{y:.1f} {xR - 25},{y:.1f}" fill="none" stroke="#c3ccda" stroke-width="1.6" marker-end="url(#ah)"/>')
        s.append(node(xR, y, ic, label, "#fff", "#cfe3c2"))
    # 가운데 회사
    s.append(f'<circle cx="{xC}" cy="{cy:.1f}" r="{hubR + 6}" fill="#2f5fb3" opacity=".12"/>'
             f'<circle cx="{xC}" cy="{cy:.1f}" r="{hubR}" fill="url(#hub)"/>'
             f'<text x="{xC}" y="{cy + 1:.1f}" text-anchor="middle" class="bm-ci">{_e(comp_icon)}</text>'
             f'<text x="{xC}" y="{cy + hubR + 18:.1f}" text-anchor="middle" class="bm-cn">{_e(_short(name, 10))}</text>')
    # 돈 흐름: 고객 → 회사 (아래쪽 곡선)
    yb = top + body + 4
    s.append(f'<path d="M{xR},{yb - 14} C{xR},{yb + 26} {xC + 20},{yb + 26} {xC + 8},{cy + hubR + 26:.1f}" fill="none" stroke="#1d8a55" stroke-width="2.2" stroke-dasharray="6 5" marker-end="url(#am)"/>')
    s.append(f'<rect x="{xC + 26}" y="{yb + 14}" width="{W - xC - 30}" height="24" rx="12" fill="#e6f4ec"/>'
             f'<text x="{(xC + 26 + W - 4) / 2:.1f}" y="{yb + 30}" text-anchor="middle" class="bm-m">💰 {_e(money)}</text>')
    if regs:
        s.append(f'<text x="8" y="{H - 8}" class="bm-r">' + "  ".join(_e(f"{fl} {nm}") for fl, nm in regs) + '</text>')
    s.append("</svg>")
    return "".join(s)


def build(d, text: str, money: str) -> dict:
    """그림과 '사업 한눈에' 목록을 함께 돌려준다."""
    prods = products(text)
    custs = customers(text, d.sector, prods)
    regs = regions(text, d.ticker.market)
    return {"svg": svg(d.ticker.name, d.sector, prods, custs, regs, money),
            "products": prods, "customers": custs, "regions": regs}


CSS = """
.bm{width:100%;height:auto;display:block;margin:4px 0 2px}
.bm-h{font-size:11px;fill:#6b7686;font-weight:700}
.bm-i{font-size:20px;dominant-baseline:middle}
.bm-l{font-size:11.5px;fill:#1c2533;font-weight:700}
.bm-ci{font-size:30px;dominant-baseline:middle}
.bm-cn{font-size:12.5px;fill:#14284b;font-weight:800}
.bm-m{font-size:11.5px;fill:#1d6b45;font-weight:800}
.bm-r{font-size:12px;fill:#4a5566}
.bm-list{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px}
.bm-list div{background:#f4f6fa;border-radius:10px;padding:7px 9px;font-size:12.5px;display:flex;gap:6px;align-items:center}
.bm-list b{font-size:16px}
.bm-desc{font-size:13.5px;line-height:1.65;color:#2a3442;margin:10px 0 0;padding:10px 12px;background:#f8fafd;border-radius:10px;border-left:3px solid #2f5fb3}
"""
