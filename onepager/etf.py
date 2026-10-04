"""ETF 한 장 리포트.

입력은 단순한 dict (opdb/build_etf.py 가 만든다):
  sym, name, name_en, mkt(US/KR), cur, as_of, issuer, index, category, desc(한글), listed,
  aum(통화 금액), fee(%), div_yield(%), price, w52_lo, w52_hi,
  returns {"1개월": %, "3개월": %, ...}, holdings [{code, name, w(%)}], n_hold,
  sectors [{k, w(%)}], assets [{k, w}], countries [{k, w}], price_history [[날짜, 값], ...]

종목 리포트와 같은 CSS/약속(.hdr, .kpi.k1, h2 '주가 (1년)', .w52)을 지켜서 앱이 최신가를 끼워 넣는다.
구성 종목 줄은 data-op="코드" — 앱에서 누르면 그 종목 리포트로 이동.
"""
from __future__ import annotations

import math
import re
from html import escape as _e
from typing import Optional

from .fmt import money, price, unit
from .render import MARKET_FLAG, MARKET_LABEL, krw, price_svg

SECTOR_KO = {
    # 야후
    "technology": ("💻", "IT·기술"), "financial_services": ("🏦", "금융"), "healthcare": ("💊", "헬스케어"),
    "consumer_cyclical": ("🛍️", "경기소비재"), "consumer_defensive": ("🛒", "필수소비재"), "industrials": ("🏭", "산업재"),
    "communication_services": ("📡", "커뮤니케이션"), "energy": ("🛢️", "에너지"), "basic_materials": ("⛏️", "소재"),
    "utilities": ("⚡", "유틸리티"), "realestate": ("🏢", "부동산"),
    # 네이버
    "IT": ("💻", "IT·기술"), "FINANCIALS": ("🏦", "금융"), "HEALTHCARE": ("💊", "헬스케어"),
    "CONSUMER_DISCRETIONARY": ("🛍️", "경기소비재"), "CONSUMER_STAPLES": ("🛒", "필수소비재"), "INDUSTRIALS": ("🏭", "산업재"),
    "COMMUNICATION": ("📡", "커뮤니케이션"), "ENERGY": ("🛢️", "에너지"), "MATERIALS": ("⛏️", "소재"),
    "UTILITIES": ("⚡", "유틸리티"), "REAL_ESTATE": ("🏢", "부동산"), "UNCLASSIFIED": ("❔", "기타"),
}
ASSET_KO = {"stockPosition": "주식", "bondPosition": "채권", "cashPosition": "현금", "preferredPosition": "우선주",
            "convertiblePosition": "전환사채", "otherPosition": "기타", "EQUITY": "주식", "BOND": "채권", "CASH": "현금",
            "DERIVATIVES": "파생상품", "OTHERS": "기타"}
COUNTRY_KO = {"KR": "🇰🇷 한국", "US": "🇺🇸 미국", "JP": "🇯🇵 일본", "CN": "🇨🇳 중국", "HK": "🇭🇰 홍콩", "MISC": "🌐 기타"}
PALETTE = ["#1f4e9c", "#d95926", "#199e70", "#c98500", "#d55181", "#9085e9", "#2f8fb5", "#7a8a2a", "#b5523b", "#5b6675"]
UP, DN = "#c0392b", "#1f4e9c"


def e(x) -> str:
    return _e(str(x)) if x is not None else ""


def kind(name: str) -> list[tuple[str, str]]:
    """이름으로 ETF 성격 배지 (레버리지·인버스·채권·배당 …)"""
    n = name or ""
    out = []
    if re.search(r"인버스|Inverse|Short|Bear|-1X|\(-", n, re.I):
        out.append(("인버스(반대로 움직임)", "warn"))
    if re.search(r"레버리지|2X|3X|Ultra|Bull|2배|3배", n, re.I):
        out.append(("레버리지(변동 큼)", "warn"))
    if re.search(r"채권|국채|Bond|Treasury|회사채|단기|머니마켓|CD금리|KOFR|Income", n, re.I):
        out.append(("채권·이자형", "neu"))
    if re.search(r"배당|Dividend|커버드콜|Covered Call|Premium|Yield", n, re.I):
        out.append(("배당·분배형", "good"))
    if re.search(r"금|Gold|은|Silver|원유|Oil|Commodity|원자재", n, re.I):
        out.append(("원자재", "neu"))
    return out


# ── 그림: 1만원을 넣으면 (트리맵) ─────────────────────────────

def _squarify(vals, x, y, w, h):
    """간단한 squarified treemap → [(x, y, w, h)] (vals 합 = w*h 로 정규화되어 있어야 함)"""
    rects, vals = [], list(vals)
    while vals:
        short = min(w, h)
        row, best = [], math.inf
        for v in vals:
            test = row + [v]
            s = sum(test)
            worst = max(max(short * short * r / (s * s), (s * s) / (short * short * r)) for r in test)
            if worst > best:
                break
            row, best = test, worst
        s = sum(row)
        if w >= h:
            cw = s / h
            cy = y
            for v in row:
                rh = v / cw
                rects.append((x, cy, cw, rh))
                cy += rh
            x, w = x + cw, w - cw
        else:
            rh = s / w
            cx = x
            for v in row:
                cw = v / rh
                rects.append((cx, y, cw, rh))
                cx += cw
            y, h = y + rh, h - rh
        vals = vals[len(row):]
    return rects


ASSET_TM = {"stockPosition": "주식", "bondPosition": "채권", "cashPosition": "현금", "preferredPosition": "우선주",
            "convertiblePosition": "전환사채", "otherPosition": "기타 (실물·스왑·선물 등)", "EQUITY": "주식", "BOND": "채권",
            "CASH": "현금", "DERIVATIVES": "파생상품", "OTHERS": "기타"}


def treemap_svg(holdings, total_amt=10000, cur_label="원", assets=None) -> str:
    hs = [h for h in holdings if h.get("w")][:12]
    if not hs and assets:
        hs = [{"name": ASSET_TM.get(a["k"], a["k"]), "w": a["w"], "code": None} for a in sorted(assets, key=lambda a: -a["w"]) if a.get("w")]
    if not hs:
        return ""
    top = sum(h["w"] for h in hs)
    items = [(h["name"], h["w"], h.get("code")) for h in hs]
    if top < 99.5:
        items.append(("나머지", 100 - top, None))
    items.sort(key=lambda t: -t[1])          # 큰 것부터 놓아야 모양이 반듯함
    W, H = 340, 230
    tot = sum(v for _, v, _ in items)
    areas = [v / tot * W * H for _, v, _ in items]
    rects = _squarify(areas, 0, 0, W, H)
    cidx = {h["name"]: j for j, h in enumerate(hs)}
    s = [f'<svg viewBox="0 0 {W} {H}" class="tm" role="img" aria-label="1만원을 넣으면 나뉘는 비율">']
    for i, ((nm, v, code), (x, y, w, h)) in enumerate(zip(items, rects)):
        col = "#b4bccb" if nm == "나머지" else PALETTE[cidx[nm] % len(PALETTE)]
        amt = total_amt * v / 100
        s.append(f'<g{" data-op=" + chr(34) + e(code) + chr(34) if code else ""}>'
                 f'<rect x="{x + 1:.1f}" y="{y + 1:.1f}" width="{max(w - 2, 0):.1f}" height="{max(h - 2, 0):.1f}" rx="7" fill="{col}"/>')
        if w > 46 and h > 30:
            fs = 13 if (w > 110 and h > 60) else 11 if w > 70 else 9.5
            maxc = max(3, int(w / (fs * 0.95)))
            label = nm if len(nm) <= maxc else nm[: maxc - 1] + "…"
            cx, cy = x + w / 2, y + h / 2
            s.append(f'<text x="{cx:.1f}" y="{cy - 2:.1f}" text-anchor="middle" class="tm-n" font-size="{fs}">{e(label)}</text>'
                     f'<text x="{cx:.1f}" y="{cy + fs + 1:.1f}" text-anchor="middle" class="tm-v" font-size="{fs - 1.5}">'
                     f'{amt:,.0f}{cur_label} · {v:.1f}%</text>')
        elif w > 22 and h > 16:
            s.append(f'<text x="{x + w / 2:.1f}" y="{y + h / 2 + 4:.1f}" text-anchor="middle" class="tm-v" font-size="9">{v:.0f}%</text>')
        s.append("</g>")
    s.append("</svg>")
    return "".join(s)


def holdings_html(holdings, n_hold: Optional[int]) -> str:
    hs = [h for h in holdings if h.get("w") is not None][:30]
    if not hs and holdings:
        items = []
        for i, h in enumerate(holdings[:15]):
            op = f' data-op="{e(h["code"])}"' if h.get("code") else ""
            sh = f'{h["sh"]:,.0f}주' if h.get("sh") else ""
            items.append(f'<li class="hl"{op}><span class="hl-r">{i + 1}</span><span class="hl-nm"><b>{e(h["name"])}</b></span>'
                         f'<span class="hl-b"></span><span class="hl-w">{sh}</span><span></span></li>')
        rows = "".join(items)
        return ('<div class="hl-note">운용사가 비중(%) 대신 <b>보유 주식 수</b>만 공개한 ETF예요. 많이 담은 순서는 아래와 같아요.</div>'
                f'<ul class="hls">{rows}</ul><div class="muted small">주식 수 = 설정 단위(CU)당 보유 주식 수</div>')
    if not hs:
        return '<div class="muted">운용사가 구성 종목을 공개하지 않았어요. 위 그림은 자산 종류별 비중이에요.</div>'
    mx = max(h["w"] for h in hs) or 1
    rows = []
    for i, h in enumerate(hs):
        col = PALETTE[i % len(PALETTE)] if i < 12 else "#9aa5b5"
        link = f' data-op="{e(h["code"])}"' if h.get("code") else ""
        sub = (f'<span class="hl-c">{e(h["code"])}</span>' if h.get("code") and h["code"] != h["name"]
               and not h["code"].isdigit() else "")
        rows.append(f'<li class="hl"{link}><span class="hl-r">{i + 1}</span>'
                    f'<span class="hl-nm"><b>{e(h["name"])}</b>{sub}</span>'
                    f'<span class="hl-b"><i style="width:{h["w"] / mx * 100:.1f}%;background:{col}"></i></span>'
                    f'<span class="hl-w">{h["w"]:.2f}%</span>{"<span class=hl-go>›</span>" if link else ""}</li>')
    top10 = sum(h["w"] for h in hs[:10])
    note = f'상위 10개가 전체의 <b>{top10:.1f}%</b>'
    if n_hold:
        note += f' · 총 {n_hold:,}개 종목'
    return f'<div class="hl-note">{note}</div><ul class="hls">{"".join(rows)}</ul><div class="muted small">종목을 누르면 그 회사 리포트로 이동해요</div>'


def stack_html(parts, labels: dict, with_icon: bool = False) -> str:
    ps = [(k, w) for k, w in parts if w and w > 0.05]
    if not ps:
        return '<div class="muted">정보 없음</div>'
    ps.sort(key=lambda x: -x[1])
    tot = sum(w for _, w in ps) or 1
    bar = "".join(f'<i style="width:{w / tot * 100:.2f}%;background:{PALETTE[i % len(PALETTE)]}"></i>' for i, (k, w) in enumerate(ps))
    li = []
    for i, (k, w) in enumerate(ps[:9]):
        lab = labels.get(k, k)
        if isinstance(lab, tuple):
            lab = f"{lab[0]} {lab[1]}" if with_icon else lab[1]
        li.append(f'<li><span class="dot" style="background:{PALETTE[i % len(PALETTE)]}"></span><span class="sl">{e(lab)}</span><b>{w:.1f}%</b></li>')
    return f'<div class="stk">{bar}</div><ul class="stl">{"".join(li)}</ul>'


def returns_svg(rets: dict) -> str:
    items = [(k, v) for k, v in rets.items() if v is not None]
    if not items:
        return '<div class="muted">정보 없음</div>'
    W, H, top, bot = 330, 160, 22, 34
    vmax = max([0.0] + [v for _, v in items])
    vmin = min([0.0] + [v for _, v in items])
    scale = (H - top - bot) / ((vmax - vmin) or 1)
    zero = top + vmax * scale
    bw = W / len(items)
    s = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="기간별 수익률">',
         f'<line x1="0" x2="{W}" y1="{zero:.1f}" y2="{zero:.1f}" stroke="#c9d1dd"/>']
    for i, (k, v) in enumerate(items):
        x = i * bw + bw * 0.22
        w = bw * 0.56
        h = abs(v) * scale
        y = zero - h if v >= 0 else zero
        c = UP if v >= 0 else DN
        s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{max(h, 1):.1f}" rx="4" fill="{c}"/>')
        ty = y - 5 if v >= 0 else y + h + 13
        s.append(f'<text x="{x + w / 2:.1f}" y="{ty:.1f}" text-anchor="middle" class="ax b" fill="{c}">{v:+.1f}%</text>')
        s.append(f'<text x="{x + w / 2:.1f}" y="{H - 5}" text-anchor="middle" class="ax">{e(k)}</text>')
    s.append("</svg>")
    return "".join(s)


def summary3(x: dict) -> list[str]:
    out = []
    what = x.get("index") or x.get("category")
    hs = x.get("holdings") or []
    if what:
        out.append(f"‘{what}’을(를) 따라가는 ETF예요." if x.get("index") else f"‘{what}’ 유형의 ETF예요.")
    if hs:
        names = ", ".join(h["name"] for h in hs[:3])
        top10 = sum(h["w"] for h in hs[:10] if h.get("w"))
        out.append(f"가장 많이 담은 종목은 {names} — 상위 10개 비중 {top10:.0f}%.")
    r1 = (x.get("returns") or {}).get("1년")
    fee = x.get("fee")
    tail = []
    if r1 is not None:
        tail.append(f"최근 1년 수익률 {r1:+.1f}%")
    if fee is not None:
        tail.append(f"1년 보수 {fee:.2f}% (100만원당 약 {fee * 10000:,.0f}원)")
    if tail:
        out.append(", ".join(tail) + ".")
    return out[:3] or ["ETF 정보를 정리했어요."]


def render_etf(x: dict, fx: Optional[dict] = None) -> str:
    cur = x.get("cur") or ("KRW" if x.get("mkt") == "KR" else "USD")
    mkt = x.get("mkt", "US")
    name = x.get("name") or x["sym"]
    exch = f"{MARKET_FLAG.get(mkt, '')} {MARKET_LABEL.get(mkt, mkt)} ETF · {x['sym']}"
    one = " · ".join(t for t in [f"기초지수 {x['index']}" if x.get("index") else "", x.get("issuer") or "",
                                 f"상장 {x['listed']}" if x.get("listed") else ""] if t)
    badges = kind(name + " " + (x.get("name_en") or "") + " " + (x.get("index") or ""))
    fee = x.get("fee")
    if fee is not None and fee <= 0.2:
        badges.append(("낮은 보수", "good"))
    if fee is not None and fee >= 0.75:
        badges.append(("보수 높은 편", "warn"))
    if x.get("aum") and fx is not None:
        won = x["aum"] * ((fx or {}).get(cur, 1) if cur != "KRW" else 1)
        if won >= 1e12:
            badges.append(("큰 ETF(순자산 1조원↑)", "good"))
        elif won < 1e10:
            badges.append(("작은 ETF(거래 적을 수 있음)", "warn"))
    hs = x.get("holdings") or []
    if hs and hs[0].get("w") and hs[0]["w"] >= 25:
        badges.append((f"{hs[0]['name']} 비중 큼", "neu"))
    badge_html = "".join(f'<span class="bd {k}">{e(t)}</span>' for t, k in badges)
    sum3 = "".join(f'<li><span class="n">{i + 1}</span><span>{e(s)}</span></li>' for i, s in enumerate(summary3(x)))

    r1 = (x.get("returns") or {}).get("1년")
    kpis = [
        ("현재가", price(x.get("price"), cur) if x.get("price") else "–", "전일 대비", "k1", krw(x.get("price"), cur, fx, "p")),
        ("순자산", money(x.get("aum"), cur) if x.get("aum") else "–", "펀드 크기", "k2", krw(x.get("aum"), cur, fx)),
        ("1년 보수", f"{fee:.2f}%" if fee is not None else "–", "매년 떼는 비용", "k3", ""),
        ("1년 수익률", f"{r1:+.1f}%" if r1 is not None else "–",
         f"분배 {x['div_yield']:.2f}%" if x.get("div_yield") else "분배 정보 없음", "k4", ""),
    ]
    kpi_html = "".join(
        f'<div class="kpi {c}"><div class="kl">{e(l)}</div><div class="kv">{e(v)}</div>'
        + (f'<div class="kw">{w}</div>' if w else "") + f'<div class="ks">{e(s)}</div></div>' for l, v, s, c, w in kpis)

    lo, hi, p = x.get("w52_lo"), x.get("w52_hi"), x.get("price")
    w52 = ""
    if lo and hi and p and hi > lo:
        pos = max(0.0, min(1.0, (p - lo) / (hi - lo))) * 100
        side = "r" if pos > 85 else "l" if pos < 15 else ""
        w52 = (f'<div class="w52" data-lo="{lo}" data-hi="{hi}"><div class="w52-t"><span class="w52-f"></span>'
               f'<span class="w52-n" style="left:{pos:.1f}%"><em class="{side}">현재 {price(p, cur)}</em></span></div>'
               f'<div class="w52-l"><span>52주 최저 {price(lo, cur)}</span><span>52주 최고 {price(hi, cur)}</span></div></div>')

    desc = (x.get("desc") or "").strip()
    sents = [s for s in re.split(r"(?<=[.다요])\s+", desc) if s][:5]
    desc_html = "<ul class='dense'>" + "".join(f"<li>{e(s)}</li>" for s in sents) + "</ul>" if sents else '<div class="muted">설명 없음</div>'
    facts = [("운용사", x.get("issuer")), ("기초지수", x.get("index")), ("유형", x.get("category")), ("상장일", x.get("listed"))]
    facts_html = "".join(f"<div><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in facts if v)

    tm_cur = "원"
    tm = treemap_svg(hs, 10000, tm_cur, x.get("assets"))
    if not any(h.get("w") for h in hs) and tm:
        tm += '<div class="muted small">구성 종목 비중이 공개되지 않아 자산 종류별로 나눴어요.</div>'
    if x.get("hold_proxy"):
        tm += f'<div class="hl-note" style="margin-top:8px">이 ETF는 운용사가 비중을 공개하지 않아서, <b>같은 지수를 따르는 미국 ETF {e(x["hold_proxy"])}</b>의 비중으로 보여줘요. 실제와 조금 다를 수 있어요.</div>'
    elif x.get("hold_src"):
        tm += f'<div class="muted small">구성 종목 출처: {e(x["hold_src"])}</div>'
    hist = [tuple(h) for h in (x.get("price_history") or [])]
    sectors = stack_html([(s["k"], s["w"]) for s in (x.get("sectors") or [])], SECTOR_KO, True)
    assets = stack_html([(s["k"], s["w"]) for s in (x.get("assets") or [])], ASSET_KO)
    countries = x.get("countries") or []
    ctry = stack_html([(s["k"], s["w"]) for s in countries], COUNTRY_KO) if countries else ""

    fxline = ""
    if fx and cur != "KRW" and fx.get(cur):
        fxline = '<br><span class="fxl">' + e(f"1{unit(cur)} ≈ {fx[cur]:,.2f}원") + "</span>"
    src = "네이버증권·와이즈리포트" if mkt == "KR" else "Yahoo Finance·Nasdaq (설명은 자동 번역)"

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(name)} ETF 리포트</title>
<style></style></head>
<body><main class="page etf">
<header class="hd">
  <div class="hd-l"><div class="tk">{e(exch)}</div><h1>{e(name)}</h1>
  <div class="one">{e(one)}</div></div>
  <div class="hdr">{e(x.get('as_of', ''))}<br>통화 {e(unit(cur))}{fxline}</div>
</header>

<section class="card sum">
  <h2>한눈에 보기</h2>
  <ol class="s3">{sum3}</ol>
  <div class="bds">{badge_html}</div>
</section>

<section class="kpis">{kpi_html}</section>
{w52}

<section class="card">
  <h2>1만원을 넣으면 이렇게 나뉘어요</h2>
  {tm or '<div class="muted">구성 정보 없음</div>'}
</section>

<section class="card">
  <h2>구성 종목</h2>
  {holdings_html(hs, x.get('n_hold'))}
</section>

<section class="grid2">
  <div class="card">
    <h2>업종 비중</h2>
    {sectors}
  </div>
  <div class="card">
    <h2>자산{' · 국가' if ctry else ''} 비중</h2>
    {assets}
    {('<div class="sub">국가</div>' + ctry) if ctry else ''}
  </div>
</section>

<section class="grid2">
  <div class="card">
    <h2>어떤 ETF인가</h2>
    {desc_html}
    <div class="facts">{facts_html}</div>
  </div>
  <div class="card">
    <h2>주가 (1년)</h2>
    {price_svg(hist, cur)}
  </div>
</section>

<section class="card">
  <h2>기간별 수익률</h2>
  {returns_svg(x.get('returns') or {})}
</section>

<footer class="ft">출처: {e(src)} · {e(x.get('as_of', ''))} 기준. 구성 비중은 운용사 공시 시점 기준이라 오늘과 다를 수 있어요.
정보 제공 목적이며 투자 권유가 아님. 투자 판단과 책임은 투자자 본인에게 있습니다.</footer>
</main></body></html>"""


