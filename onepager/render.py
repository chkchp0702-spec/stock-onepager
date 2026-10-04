"""StockData + Narrative → 한 장짜리 HTML 리포트 (휴대폰 우선, 인쇄/PDF 저장 가능).

앱(C. Investing)이 나중에 최신 가격을 끼워 넣기 위해 지키는 약속:
  .hdr            헤더 오른쪽 날짜/통화 줄
  .kpi.k1 .kv/.ks 주가 타일
  h2 '주가 (1년)'  차트 카드 (카드 내용을 통째로 바꿈)
  .w52            52주 위치 바 (data-lo / data-hi)
  h2 '최근 뉴스'   뉴스 카드 (링크 추가)
"""
from __future__ import annotations

from html import escape as _e
from typing import Optional
import re

from .fmt import money, pct, price, unit
from .models import Narrative, StockData
from . import bizmap
from .narrative import clean_desc

MARKET_LABEL = {"US": "미국", "KR": "한국", "JP": "일본", "CN": "중국", "HK": "홍콩"}
MARKET_FLAG = {"US": "🇺🇸", "KR": "🇰🇷", "JP": "🇯🇵", "CN": "🇨🇳", "HK": "🇭🇰"}
UP, DN = "#c0392b", "#1f4e9c"   # 한국식: 상승 빨강 · 하락 파랑


def e(x) -> str:
    return _e(str(x)) if x is not None else ""


# ── 그림 조각 ───────────────────────────────────────────────────

FLOW_COLORS = ["#1f4e9c", "#2f6fb5", "#2c8a5a", "#1d6b45"]


def flow_html(flow, center: str) -> str:
    """회사가 돈을 버는 구조: 큰 그림(이모티콘) 4칸 + 화살표. 휴대폰에서는 2×2."""
    parts = [f'<div class="flow2" role="img" aria-label="{e(center)} 사업 구조">']
    for i, st in enumerate(flow):
        if len(st) == 3:
            icon, title, desc = st
        else:
            icon, (title, desc) = "⭐💰"[0 if i < len(flow) - 1 else 1], st
        c = FLOW_COLORS[i % len(FLOW_COLORS)]
        parts.append(f'<div class="fs" style="--c:{c}"><div class="fs-i">{e(icon)}</div>'
                     f'<div class="fs-t"><span class="no">{i + 1}</span>{e(title)}</div><div class="fs-d">{e(desc)}</div></div>')
        if i < len(flow) - 1:
            parts.append('<div class="fs-a" aria-hidden="true">➜</div>')
    parts.append("</div>")
    return "".join(parts)


def price_svg(hist: list[tuple[str, float]], currency: str) -> str:
    if len(hist) < 2:
        return '<div class="muted">차트는 앱에서 최신 가격으로 그려집니다</div>'
    W, H, pad_l, pad_b, pad_t = 320, 130, 4, 18, 10
    vals = [v for _, v in hist]
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    step = (W - pad_l * 2) / (len(vals) - 1)
    pts = [(pad_l + i * step, pad_t + (hi - v) / rng * (H - pad_t - pad_b)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{pts[0][0]:.1f},{H - pad_b} {line} {pts[-1][0]:.1f},{H - pad_b}"
    c = UP if vals[-1] >= vals[0] else DN
    chg = vals[-1] / vals[0] - 1
    return (f'<svg viewBox="0 0 {W} {H}" class="spark" role="img" aria-label="1년 주가">'
            f'<polygon points="{area}" fill="{c}" opacity="0.10"/>'
            f'<polyline points="{line}" fill="none" stroke="{c}" stroke-width="1.8"/>'
            f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3" fill="{c}"/>'
            f'<text x="{pad_l}" y="{H - 4}" class="ax">{e(hist[0][0])}</text>'
            f'<text x="{W - pad_l}" y="{H - 4}" class="ax" text-anchor="end">{e(hist[-1][0])}</text>'
            f'<text x="{W - pad_l}" y="12" class="ax" text-anchor="end" fill="{c}">1년 {pct(chg, sign=True)}</text></svg>'
            f'<div class="muted small">최고 {price(hi, currency)} · 최저 {price(lo, currency)}</div>')


def krw(v, cur: str, fx: Optional[dict], kind: str = "m") -> str:
    """달러·위안·엔·홍콩달러 옆 원화 환산. 앱이 최신 환율로 다시 채운다 (class krw, data-v, data-c)."""
    if v is None or cur == "KRW":
        return ""
    rate = (fx or {}).get(cur)
    txt = ""
    if rate:
        w = v * rate
        txt = "≈ " + (price(w, "KRW") if kind == "p" else money(w, "KRW"))
    return f'<span class="krw" data-v="{v}" data-c="{e(cur)}" data-k="{kind}">{e(txt)}</span>'


def estimates_html(d: StockData, fx: Optional[dict]) -> str:
    est = [dict(x) for x in (d.estimates or []) if x.get("rev") is not None or x.get("eps") is not None]
    # 성장률은 야후 값 대신 직접 계산 (바로 앞 해 실제값 또는 앞선 추정치 대비)
    act_by = {str(y.period): y for y in d.financials}
    prev_rev = prev_eps = None
    for x in est:
        try:
            py = act_by.get(str(int(x["period"]) - 1))
        except ValueError:
            py = None
        pr = py.revenue if py else prev_rev
        pe_ = py.eps if py else prev_eps
        x["rev_g"] = (x["rev"] / pr - 1) if (x.get("rev") and pr and pr > 0) else None
        x["eps_g"] = (x["eps"] / pe_ - 1) if (x.get("eps") is not None and pe_ and pe_ > 0) else None
        prev_rev, prev_eps = x.get("rev"), x.get("eps")
    if not est:
        return ('<div class="muted">애널리스트 추정치가 없습니다 (분석하는 증권사가 없거나 자료 미공개)</div>'
                + (f'<div class="ltg">향후 5년 EPS 연평균 성장 추정 <b>{pct(d.ltg, sign=True)}</b></div>' if d.ltg is not None else ""))
    cur = d.currency
    # 실제 매출 (최근 3년) + 추정 (2년) 막대
    act = [(y.period, y.revenue, None, None) for y in d.financials if y.revenue][-3:]
    fut = [(x["period"], x.get("rev"), x.get("rev_lo"), x.get("rev_hi")) for x in est if x.get("rev")]
    bars = ""
    allb = act + fut
    if allb:
        W, H, top, bot = 320, 150, 24, 22
        mx = max(max(abs(v or 0), abs(hi or 0)) for _, v, _, hi in allb) or 1
        slot = (W - 20) / len(allb)
        bw = min(46, slot - 12)
        out = [f'<svg viewBox="0 0 {W} {H}" class="bars" role="img" aria-label="실제 매출과 추정 매출">']
        for i, (per, v, lo, hi) in enumerate(allb):
            x = 10 + i * slot + (slot - bw) / 2
            h = (H - top - bot) * abs(v) / mx
            is_est = i >= len(act)
            if is_est:
                out.append(f'<rect x="{x:.1f}" y="{H - bot - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="4" fill="#e6efff" stroke="#1f4e9c" stroke-width="1.5" stroke-dasharray="4 3"/>')
                if lo and hi and hi > lo:
                    y1, y2 = H - bot - (H - top - bot) * hi / mx, H - bot - (H - top - bot) * lo / mx
                    cx = x + bw / 2
                    out.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{y1:.1f}" y2="{y2:.1f}" stroke="#1f4e9c" stroke-width="1.5"/>'
                               f'<line x1="{cx - 6:.1f}" x2="{cx + 6:.1f}" y1="{y1:.1f}" y2="{y1:.1f}" stroke="#1f4e9c" stroke-width="1.5"/>'
                               f'<line x1="{cx - 6:.1f}" x2="{cx + 6:.1f}" y1="{y2:.1f}" y2="{y2:.1f}" stroke="#1f4e9c" stroke-width="1.5"/>')
            else:
                out.append(f'<rect x="{x:.1f}" y="{H - bot - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="4" fill="#9fb6d6"/>')
            ytxt = min(H - bot - h, (H - bot - (H - top - bot) * hi / mx) if (is_est and hi) else 1e9) - 5
            out.append(f'<text x="{x + bw / 2:.1f}" y="{ytxt:.1f}" text-anchor="middle" class="ax b">{e(money(v, cur).replace(" " + unit(cur), ""))}</text>')
            out.append(f'<text x="{x + bw / 2:.1f}" y="{H - 6}" text-anchor="middle" class="ax{" b" if is_est else ""}">{e(per)}{"(E)" if is_est else ""}</text>')
        out.append("</svg>")
        bars = "".join(out) + '<div class="muted small">진한 막대 = 실제 매출 · 점선 막대 = 애널리스트 평균 추정 · 세로줄 = 최저~최고 추정</div>'
    rows = []
    for x in est:
        rev = x.get("rev")
        rv = (f'{e(money(rev, cur))}' + (f' <i class="{"up" if (x.get("rev_g") or 0) >= 0 else "dn"}">{pct(x["rev_g"], sign=True, digits=0)}</i>' if x.get("rev_g") is not None else "")
              + (f'<br>{krw(rev, cur, fx)}' if cur != "KRW" else "")) if rev is not None else "–"
        eps = x.get("eps")
        ev = (f'{e(price(eps, cur))}' + (f' <i class="{"up" if (x.get("eps_g") or 0) >= 0 else "dn"}">{pct(x["eps_g"], sign=True, digits=0)}</i>' if x.get("eps_g") is not None else "")) if eps is not None else "–"
        pe = ""
        if eps and eps > 0 and d.price:
            pe = f"{d.price / eps:.1f}배"
        rows.append(f'<tr><td>{e(x["period"])}(E)' + (f'<br><small class="muted">{x["n"]}명</small>' if x.get("n") else "") + f'</td><td>{rv}</td><td>{ev}</td><td>{e(pe) or "–"}</td></tr>')
    table = ('<div class="tblwrap"><table class="fin est"><thead><tr><th>연도</th><th>매출</th><th>주당순이익</th><th>예상 PER</th></tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>')
    ltg = f'<div class="ltg">향후 5년 EPS 연평균 성장 추정 <b>{pct(d.ltg, sign=True)}</b></div>' if d.ltg is not None else ""
    return bars + table + ltg + '<div class="muted small">(E) = 애널리스트 평균 추정 · N명 = 추정한 애널리스트 수 · % = 전년 대비 · 예상 PER = 현재가 ÷ 추정 EPS</div>'


def w52_html(d: StockData) -> str:
    lo, hi, p = d.week52_low, d.week52_high, d.price
    if not (lo and hi and p and hi > lo):
        return ""
    pos = max(0.0, min(1.0, (p - lo) / (hi - lo))) * 100
    side = "r" if pos > 85 else "l" if pos < 15 else ""
    return (f'<div class="w52" data-lo="{lo}" data-hi="{hi}"><div class="w52-t"><span class="w52-f"></span>'
            f'<span class="w52-n" style="left:{pos:.1f}%"><em class="{side}">현재 {price(p, d.currency)}</em></span></div>'
            f'<div class="w52-l"><span>52주 최저 {price(lo, d.currency)}</span><span>52주 최고 {price(hi, d.currency)}</span></div></div>')


def revenue_svg(d: StockData) -> str:
    f = [y for y in d.financials if y.revenue]
    if not f:
        return ""
    W, H, top, bot = 320, 150, 24, 22
    mx = max(abs(y.revenue) for y in f) or 1
    slot = (W - 20) / len(f)
    bw = min(56, slot - 14)
    out = [f'<svg viewBox="0 0 {W} {H}" class="bars" role="img" aria-label="연도별 매출과 영업이익률">']
    for i, y in enumerate(f):
        h = (H - top - bot) * abs(y.revenue) / mx
        x = 10 + i * slot + (slot - bw) / 2
        last = i == len(f) - 1
        grow = i > 0 and f[i - 1].revenue and y.revenue >= f[i - 1].revenue
        col = "#1f4e9c" if last else ("#9fb6d6" if grow or i == 0 else "#d9a7a2")
        out.append(f'<rect x="{x:.1f}" y="{H - bot - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="4" fill="{col}"/>')
        out.append(f'<text x="{x + bw / 2:.1f}" y="{H - bot - h - 5:.1f}" text-anchor="middle" class="ax b">'
                   f'{e(money(y.revenue, d.currency).replace(" " + unit(d.currency), ""))}</text>')
        out.append(f'<text x="{x + bw / 2:.1f}" y="{H - 6}" text-anchor="middle" class="ax">{e(y.period)}</text>')
        if y.op_margin is not None and h > 22:
            out.append(f'<text x="{x + bw / 2:.1f}" y="{H - bot - 7:.1f}" text-anchor="middle" class="ax inv">'
                       f'{pct(y.op_margin, digits=0)}</text>')
    out.append("</svg>")
    out.append('<div class="muted small">막대 = 연 매출 · 막대 안 숫자 = 영업이익률 · 붉은 막대 = 전년보다 줄어든 해</div>')
    return "".join(out)


def rating_bar(d: StockData) -> str:
    a = d.analyst
    buys, holds, sells = a.strong_buy + a.buy, a.hold, a.sell + a.strong_sell
    tot = buys + holds + sells
    if not tot:
        return ""
    seg = []
    for n, c, lbl in ((buys, "#1d6b45", "매수"), (holds, "#9aa5b4", "보유"), (sells, "#c0392b", "매도")):
        if n:
            seg.append(f'<div style="flex:{n};background:{c}">{lbl} {n}</div>')
    return f'<div class="rbar">{"".join(seg)}</div>'


def target_range(d: StockData) -> str:
    a = d.analyst
    if not (a.target_low and a.target_high and d.price) or a.target_high <= a.target_low:
        return ""
    lo, hi = min(a.target_low, d.price), max(a.target_high, d.price)
    pos = lambda v: (v - lo) / (hi - lo) * 100  # noqa: E731
    mean = (f'<div class="tick mean" style="left:{pos(a.target_mean):.1f}%"><span>평균 {price(a.target_mean, d.currency)}</span></div>'
            if a.target_mean else "")
    return (f'<div class="trange"><div class="track" style="left:{pos(a.target_low):.1f}%;'
            f'width:{pos(a.target_high) - pos(a.target_low):.1f}%"></div>{mean}'
            f'<div class="tick now" style="left:{pos(d.price):.1f}%"><span>현재 {price(d.price, d.currency)}</span></div></div>'
            f'<div class="muted small flexb"><span>최저 목표 {price(a.target_low, d.currency)}</span>'
            f'<span>최고 목표 {price(a.target_high, d.currency)}</span></div>')


def fin_table(d: StockData) -> str:
    cur = d.currency
    rows = []
    f = d.financials
    for i in range(len(f) - 1, -1, -1):
        y = f[i]
        prev = f[i - 1] if i > 0 else None

        def cell(v, pv, is_money=True):
            txt = e(money(v, cur)) if is_money else e(price(v, cur) if v is not None else "–")
            arrow = ""
            if v is not None and pv:
                if pv > 0 and v < 0:
                    arrow = ' <i class="dn">적자전환</i>'
                elif pv < 0 and v > 0:
                    arrow = ' <i class="up">흑자전환</i>'
                elif pv > 0:
                    g = v / pv - 1
                    arrow = f' <i class="{"up" if g >= 0 else "dn"}">{"▲" if g >= 0 else "▼"}{abs(g) * 100:.0f}%</i>'
            neg = ' class="neg"' if (v is not None and v < 0) else ""
            return f"<td{neg}>{txt}{arrow}</td>"

        rows.append(f"<tr><td>{e(y.period)}</td>{cell(y.revenue, prev.revenue if prev else None)}"
                    f"{cell(y.operating_income, prev.operating_income if prev else None)}"
                    f"<td>{e(pct(y.op_margin))}</td>{cell(y.net_income, prev.net_income if prev else None)}"
                    f"{cell(y.eps, None, is_money=False)}</tr>")
    if not rows:
        return '<div class="muted">재무 데이터 없음</div>'
    return (f'<div class="tblwrap"><table class="fin"><thead><tr><th>연도</th><th>매출</th><th>영업이익</th><th>이익률</th>'
            f'<th>순이익</th><th>주당순이익</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
            f'<div class="muted small">▲▼ = 전년 대비 · 붉은 글씨 = 손실</div>')


# ── 페이지 ───────────────────────────────────────────────────────

def calendar_html(d: StockData) -> str:
    """다가오는 일정: 실적 발표 · 배당락 · 배당 지급 (오늘 이후만)"""
    import datetime as _dt
    today = (d.as_of or _dt.date.today().isoformat())[:10]
    c = d.calendar or {}
    items = []
    earn = [x for x in (c.get("earn") or []) if x >= today]
    if earn:
        items.append(("📢", "실적 발표", earn[0] + (" ~ " + earn[-1] if len(earn) > 1 and earn[-1] != earn[0] else "")))
    if c.get("exdiv") and c["exdiv"] >= today:
        items.append(("✂️", "배당락일", c["exdiv"] + " (이 날 전에 사야 배당)"))
    if c.get("div") and c["div"] >= today:
        items.append(("💵", "배당 지급", c["div"]))
    if not items:
        return ""
    return ('<section class="card cal"><h2>다가오는 일정</h2><div class="calr">' +
            "".join(f'<div data-date="{e(v[:10])}"><span>{i}</span><b>{e(t)}</b><em>{e(v)}</em></div>' for i, t, v in items) + "</div></section>")


def peers_html(d: StockData, peers, fx: Optional[dict]) -> str:
    """같은 업종 회사 비교표 (시가총액 큰 순, 이 회사 포함)"""
    if not peers or len(peers) < 2:
        return ""
    rows = []
    for p in peers:
        me = p["sym"] == d.ticker.symbol
        g = p.get("g")
        om = p.get("om")
        pe_s = f'{p["pe"]:.1f}' if p.get("pe") else "–"
        code = p["sym"][:6] if re.fullmatch(r"\d{6}\.K[SQ]", p["sym"] or "") else p["sym"]
        rows.append(f'<tr class="{"me" if me else ""}"><td><a data-op="{e(p["sym"])}">{e(p["name"])}</a><span class="pc">{e(code)}</span></td>'
                    f'<td>{e(money(p.get("cap"), p.get("cur") or d.currency))}</td>'
                    f'<td>{pe_s}</td>'
                    f'<td class="{"pos" if (g or 0) >= 0 else "neg"}">{(f"{g * 100:+.0f}%" if g is not None else "–")}</td>'
                    f'<td class="{"pos" if (om or 0) >= 0 else "neg"}">{(f"{om * 100:.0f}%" if om is not None else "–")}</td></tr>')
    ind = d.industry_ko or d.industry or "같은 업종"
    return (f'<section class="card"><h2>같은 업종 비교 <small class="muted">{e(ind)}</small></h2><div class="tblwrap"><table class="fin peer">'
            '<tr><th>회사</th><th>시가총액</th><th>PER</th><th>매출 성장</th><th>영업이익률</th></tr>' + "".join(rows) +
            '</table></div><div class="muted small">같은 나라·같은 업종에서 큰 회사 순 · 매출 성장·이익률은 최근 연간 실적 · 회사 이름을 누르면 그 리포트로</div></section>')


def render(d: StockData, nv: Narrative, fx: Optional[dict] = None, peers=None, media: Optional[dict] = None, rc: str = "") -> str:
    t = d.ticker
    cur = d.currency
    chg = ""
    if d.change_pct is not None:
        cls = "up" if d.change_pct >= 0 else "down"
        chg = f'<span class="{cls}">{pct(d.change_pct, sign=True, digits=2)}</span>'

    upside = ""
    if d.analyst.target_mean and d.price:
        u = d.analyst.target_mean / d.price - 1
        upside = f'<span class="{"up" if u >= 0 else "down"}">현재가 대비 {pct(u, sign=True)}</span>'

    kpis = [
        ("주가", price(d.price, cur), chg or "전일 대비", "k1", krw(d.price, cur, fx, "p")),
        ("시가총액", money(d.market_cap, cur), f"PER {d.pe:.1f}배" if d.pe else "PER –", "k2", krw(d.market_cap, cur, fx)),
        ("PBR", f"{d.pb:.1f}배" if d.pb else "–", f"배당 {pct(d.dividend_yield)}" if d.dividend_yield else "배당 없음·미확인", "k3", ""),
        ("평균 목표주가", price(d.analyst.target_mean, cur) if d.analyst.target_mean else "–",
         upside or (d.analyst.rating or "의견 없음"), "k4", krw(d.analyst.target_mean, cur, fx, "p") if d.analyst.target_mean else ""),
    ]
    kpi_html = "".join(
        f'<div class="kpi {c}"><div class="kl">{e(l)}</div><div class="kv">{e(v)}</div>'
        + (f'<div class="kw">{w}</div>' if w else "") + f'<div class="ks">{s}</div></div>'
        for l, v, s, c, w in kpis)
    last_rev = next((y for y in reversed(d.financials) if y.revenue), None)
    rev_krw = (f'<div class="muted small">최근 연 매출 {e(money(last_rev.revenue, cur))} {krw(last_rev.revenue, cur, fx)}</div>'
               if (last_rev and cur != "KRW") else "")

    badge_html = "".join(f'<span class="bd {k}">{e(txt)}</span>' for txt, k in nv.badges)
    sum3 = "".join(f'<li><span class="n">{i + 1}</span><span>{e(x)}</span></li>' for i, x in enumerate(nv.summary3))

    news_items = []
    for i, n in enumerate(d.news):
        title = nv.news_ko[i] if i < len(nv.news_ko) else n.title
        link = f'<a href="{e(n.link)}" target="_blank" rel="noopener">{e(title)}</a>' if n.link else e(title)
        news_items.append(f'<li>{link}<span class="muted small"> · {e(n.publisher)} {e(n.date)}</span></li>')
    news_html = f'<ul class="news">{"".join(news_items)}</ul>' if news_items else '<div class="muted">최근 뉴스 없음</div>'

    actions = "".join(f"<li>{e(x)}</li>" for x in d.analyst.recent_actions)
    actions_html = f'<div class="sub">최근 의견 변경</div><ul class="dense">{actions}</ul>' if actions else ""

    fin_comments = ""
    if nv.financial_comment:
        def icon(x: str) -> str:
            return "⚠️" if ("손실" in x or "감소" in x or "-" in x.split("(")[-1]) else "•"
        fin_comments = '<ul class="cm">' + "".join(f"<li><span>{icon(x)}</span>{e(x)}</li>" for x in nv.financial_comment) + "</ul>"

    exch = f"{MARKET_FLAG.get(t.market, '')} {MARKET_LABEL.get(t.market, t.market)} · {t.symbol}"
    desc_txt = clean_desc(d.desc_ko) or d.business_summary_ko or ""
    money_txt = f"매출 {money(last_rev.revenue, cur)}" if last_rev else "매출 정보 없음"
    if last_rev and cur != "KRW" and fx and fx.get(cur):
        money_txt += f" (≈{money(last_rev.revenue * fx[cur], 'KRW')})"
    bm = bizmap.build(d, desc_txt, money_txt, media, rc)
    chips = "".join(f'<div><b>{e(ic)}</b>{e(nm)}</div>' for ic, nm in bm["products"][:6])
    short_desc = " ".join(re.split(r"(?<=[.다요])\s+", desc_txt)[:3])[:360] if desc_txt else ""
    bm_html = bm["svg"] + (f'<p class="bm-desc">{e(short_desc)}</p>' if short_desc else "")
    gen = "Claude 요약" if nv.source == "llm" else "자동 요약"
    translated = bool(d.business_summary_ko) or bool(d.desc_ko)
    auto_tr = bool(d.business_summary_ko) and not d.desc_ko

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(t.name)} 원 페이지 리포트</title>
<style>{CSS}</style></head>
<body><main class="page">
<header class="hd">
  <div class="hd-l"><div class="tk">{e(exch)}</div><h1>{e(t.name)}</h1>
  <div class="one">{e(nv.one_liner)}</div></div>
  <div class="hdr">{e(d.as_of)}<br>통화 {e(unit(cur))}{('<br><span class="fxl">' + e(f"1{unit(cur)} ≈ {fx[cur]:,.2f}원") + '</span>') if (fx and cur != "KRW" and fx.get(cur)) else ""}</div>
</header>

<section class="card sum">
  <h2>한눈에 보기</h2>
  <ol class="s3">{sum3}</ol>
  <div class="bds">{badge_html}</div>
</section>

<section class="kpis">{kpi_html}</section>
{w52_html(d)}

<section class="grid2">
  <div class="card">
    <h2>어떤 회사인가{'' if translated else ' <small class="muted">(영어 원문)</small>'}</h2>
    <ul class="dense">{"".join(f"<li>{e(x)}</li>" for x in nv.overview)}</ul>
  </div>
  <div class="card">
    <h2>주가 (1년)</h2>
    {price_svg(d.price_history, cur)}
  </div>
</section>

<section class="card">
  <h2>이 회사는 이렇게 돈을 번다</h2>
  {bm_html}
</section>

<section class="grid2">
  <div class="card">
    <h2>매출 추이</h2>
    {revenue_svg(d) or '<div class="muted">데이터 없음</div>'}
    {rev_krw}
    {fin_comments}
  </div>
  <div class="card">
    <h2>재무 숫자</h2>
    {fin_table(d)}
  </div>
</section>

{calendar_html(d)}
{peers_html(d, peers, fx)}

<section class="card">
  <h2>애널리스트 추정치 (앞으로)</h2>
  {estimates_html(d, fx)}
</section>

<section class="grid2">
  <div class="card">
    <h2>애널리스트 의견</h2>
    <p>{e(nv.analyst_summary)}</p>
    {rating_bar(d)}
    {target_range(d)}
    {actions_html}
  </div>
  <div class="card">
    <h2>최근 뉴스</h2>
    {news_html}
  </div>
</section>

<footer class="ft">출처: Yahoo Finance(시세·재무·애널리스트), Google News(뉴스){' · 회사 설명은 자동 번역' if auto_tr else (' · 회사 설명: 와이즈리포트·네이버증권' if d.desc_ko else '')} · {e(gen)} · {e(d.as_of)} 기준.
정보 제공 목적이며 투자 권유가 아님. 시세는 지연될 수 있으므로 매매 전 증권사에서 확인하세요. 투자 판단과 책임은 투자자 본인에게 있습니다.</footer>
</main></body></html>"""


CSS = bizmap.CSS + """
:root{--navy:#14284b;--ink:#1c2533;--muted:#6b7686;--line:#e2e7ef;--bg:#f4f6fa;--card:#fff;
--green:#1d6b45;--red:#c0392b;--blue:#1f4e9c;--good:#e6f4ec;--goodt:#1d6b45;--warn:#fdecea;--warnt:#b0352a;--neu:#eef1f6;--neut:#4a5566}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:"Pretendard","Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",system-ui,sans-serif;font-size:14.5px;line-height:1.55;word-break:keep-all}
.page{max-width:900px;margin:0 auto;padding:14px}
.hd{background:var(--navy);color:#fff;border-radius:14px;padding:16px 18px;display:flex;justify-content:space-between;gap:12px}
.hd h1{margin:2px 0 0;font-size:26px;letter-spacing:-.5px;line-height:1.25}
.tk{font-size:12px;color:#f4c542;font-weight:700}
.one{margin-top:6px;color:#d7dfee;font-size:13.5px}.hdr{text-align:right;font-size:12px;color:#b9c4d8;white-space:nowrap}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 15px;margin-bottom:10px}
h2{font-size:15.5px;margin:0 0 10px;padding-left:9px;border-left:4px solid var(--blue)}
h2 small{font-weight:400;font-size:12px}
.sum{margin-top:10px;border-color:#cfd9ea;background:linear-gradient(180deg,#f8fbff,#fff)}
.s3{margin:0;padding:0;list-style:none}
.s3 li{display:flex;gap:10px;align-items:flex-start;padding:6px 0;font-size:15px;line-height:1.5}
.s3 .n{flex:none;width:22px;height:22px;border-radius:50%;background:var(--navy);color:#fff;font-size:12px;font-weight:800;display:flex;align-items:center;justify-content:center;margin-top:2px}
.bds{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.bd{font-size:12.5px;font-weight:700;padding:5px 10px;border-radius:999px;background:var(--neu);color:var(--neut)}
.bd.good{background:var(--good);color:var(--goodt)}.bd.good::before{content:"👍 "}
.bd.warn{background:var(--warn);color:var(--warnt)}.bd.warn::before{content:"⚠️ "}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:10px 0 6px}
.kpi{border-radius:12px;padding:11px 8px;color:#fff;text-align:center;min-width:0;overflow:hidden}
.k1{background:#1f4e9c}.k2{background:#1c355e}.k3{background:#2c6a4f}.k4{background:#5b6675}
.kl{font-size:12px;opacity:.85}.kv{font-size:20px;font-weight:800;letter-spacing:-.3px}.ks{font-size:11.5px;opacity:.95}
.ks .up{color:#ffd0c8}.ks .down{color:#cfe0ff}
.w52{margin:4px 2px 12px}
.w52-t{position:relative;height:10px;border-radius:99px;background:linear-gradient(90deg,#9fc0f0,#e8d1cf,#e89a93);margin:14px 0 4px}
.w52-n{position:absolute;top:-4px;width:18px;height:18px;border-radius:50%;background:#fff;border:3px solid var(--navy);transform:translateX(-9px)}
.w52-n em{position:absolute;top:-17px;left:50%;transform:translateX(-50%);font-style:normal;font-size:10.5px;color:var(--navy);font-weight:700;white-space:nowrap}
.w52-n em.r{left:auto;right:-3px;transform:none}.w52-n em.l{left:-3px;transform:none}
.w52-l{display:flex;justify-content:space-between;font-size:11.5px;color:var(--muted)}
.grid2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px}
.grid2>*{min-width:0}
.dense{margin:0;padding-left:18px}.dense li{margin:3px 0}.mt{margin-top:8px}
.cm{margin:10px 0 0;padding:0;list-style:none}.cm li{display:flex;gap:7px;font-size:13px;margin:4px 0;color:#2a3442}.cm li span{flex:none;width:16px}
.muted{color:var(--muted)}.small{font-size:11.5px}.sub{font-weight:600;margin-top:8px;font-size:13px}
svg{width:100%;height:auto;display:block}
.flow2{display:flex;align-items:stretch;gap:4px}
.fs{flex:1;min-width:0;border-radius:14px;padding:12px 6px 10px;text-align:center;background:color-mix(in srgb,var(--c) 7%,#fff);border:1.5px solid color-mix(in srgb,var(--c) 45%,#fff)}
.fs-i{font-size:34px;line-height:1.1;margin-bottom:6px}
.fs-t{font-weight:800;color:var(--c);font-size:14px;display:flex;align-items:center;justify-content:center;gap:5px}
.fs-t .no{display:inline-flex;width:18px;height:18px;border-radius:50%;background:var(--c);color:#fff;font-size:10.5px;align-items:center;justify-content:center;flex:none}
.fs-d{font-size:12px;color:#4a5566;margin-top:3px;line-height:1.4}
.fs-a{flex:0 0 14px;display:flex;align-items:center;justify-content:center;color:#7a8699;font-size:15px}
.kw{font-size:11.5px;opacity:.9;margin-top:1px}.krw{white-space:nowrap}
.fxl{color:#f4c542}
.est td{vertical-align:top}.est td:nth-child(2),.est td:nth-child(3){text-align:right}.est .krw{font-size:10.5px;color:var(--muted)}
.ltg{margin-top:8px;font-size:13px;background:#eef4ff;border-radius:10px;padding:8px 10px}
.flow{display:flex;align-items:stretch;gap:0}
.step{flex:1;position:relative;border:1px solid var(--c);background:color-mix(in srgb,var(--c) 8%,#fff);border-radius:12px;
padding:16px 8px 12px;text-align:center;display:flex;flex-direction:column;gap:4px;min-width:0}
.step b{color:var(--c);font-size:15px}.step small{color:#4a5566;font-size:12px}
.step .no{position:absolute;top:-9px;left:10px;width:20px;height:20px;border-radius:50%;background:var(--c);color:#fff;font-size:11px;font-weight:700;line-height:20px}
.arrow{flex:0 0 26px;position:relative}
.arrow::after{content:"";position:absolute;top:50%;left:5px;border:8px solid transparent;border-left:12px solid #7a8699;transform:translateY(-50%)}
.tblwrap{overflow-x:auto}
.ax{font-size:10px;fill:#6b7686}.ax.inv{fill:#fff;font-weight:700}.ax.b{font-weight:700;fill:#1c2533}
table.fin{width:100%;border-collapse:collapse;font-size:12px}
.fin th,.fin td{white-space:nowrap}.fin th{background:var(--navy);color:#fff;font-weight:600;padding:5px}.fin td{padding:5px;border-bottom:1px solid var(--line);text-align:right}
.fin td:first-child{text-align:left;font-weight:700}.fin td.neg{color:var(--red)}
.fin i{font-style:normal;font-size:10px;font-weight:700}.fin i.up{color:var(--red)}.fin i.dn{color:var(--blue)}
.rbar{display:flex;height:22px;border-radius:6px;overflow:hidden;margin:6px 0;font-size:11px;color:#fff}
.rbar div{display:flex;align-items:center;justify-content:center;white-space:nowrap;overflow:hidden}
.trange{position:relative;height:36px;margin:22px 8px 2px;background:linear-gradient(#e2e7ef,#e2e7ef) center/100% 4px no-repeat}
.track{position:absolute;top:15px;height:6px;background:#9bc3ad;border-radius:3px}
.tick{position:absolute;top:8px;width:2px;height:20px;transform:translateX(-1px)}
.tick span{position:absolute;left:50%;transform:translateX(-50%);font-size:10px;white-space:nowrap}
.tick.now{background:var(--red)}.tick.now span{top:-16px;color:var(--red)}
.tick.mean{background:var(--green)}.tick.mean span{top:20px;color:var(--green)}
.flexb{display:flex;justify-content:space-between}
.news{margin:0;padding-left:18px}.news li{margin:5px 0}.news a{color:var(--ink);text-decoration:none}.news a:hover{text-decoration:underline}
.up{color:var(--red)}.down{color:var(--blue)}
.ft{font-size:10.5px;color:var(--muted);padding:4px 2px 12px}
/* 일정 · 같은 업종 */
.calr{display:grid;gap:6px}.calr div{display:flex;align-items:center;gap:8px;background:var(--neu);border-radius:10px;padding:8px 10px;font-size:13px}
.calr span{font-size:18px}.calr b{flex:0 0 72px}.calr em{font-style:normal;color:var(--ink)}
.peer td:first-child{max-width:130px;overflow:hidden;text-overflow:ellipsis}.peer .pc{display:block;font-size:10px;color:var(--muted);font-weight:400}.peer a{color:var(--blue);text-decoration:none;cursor:pointer}
.peer tr.me td{background:#eef4ff;font-weight:700}.peer td.pos{color:var(--ink)}.peer td.neg{color:var(--red)}
/* ETF */
.tm{margin:2px 0 4px}.tm g[data-op]{cursor:pointer}
.tm-n{fill:#fff;font-weight:800;letter-spacing:-.3px}.tm-v{fill:#fff;opacity:.92;font-weight:600}
.hl-note{font-size:13px;background:#eef4ff;border-radius:10px;padding:7px 10px;margin-bottom:8px}
.hls{list-style:none;margin:0;padding:0}
.hl{display:grid;grid-template-columns:22px minmax(0,1.25fr) minmax(0,1fr) 54px 10px;align-items:center;gap:7px;padding:7px 2px;border-bottom:1px solid var(--line)}
.hl[data-op]{cursor:pointer}.hl[data-op]:active{background:#f1f5fb}
.hl-r{width:20px;height:20px;border-radius:50%;background:var(--neu);color:var(--neut);font-size:11px;font-weight:800;display:flex;align-items:center;justify-content:center}
.hl-nm{min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:13.5px}
.hl-nm b{font-weight:700}.hl-c{color:var(--muted);font-size:11px;margin-left:5px}
.hl-b{height:9px;background:#eef1f6;border-radius:99px;overflow:hidden}.hl-b i{display:block;height:100%;border-radius:99px}
.hl-w{text-align:right;font-weight:800;font-size:13px}.hl-go{color:#9aa5b5;font-weight:700}
.stk{display:flex;height:16px;border-radius:99px;overflow:hidden;margin:4px 0 10px}.stk i{display:block;height:100%}
.stl{list-style:none;margin:0;padding:0}.stl li{display:flex;align-items:center;gap:8px;padding:3px 0;font-size:13px}
.stl .dot{width:10px;height:10px;border-radius:3px;flex:none}.stl .sl{flex:1;min-width:0}.stl b{font-weight:800}
.facts{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:10px}
.facts div{background:var(--neu);border-radius:10px;padding:6px 9px;min-width:0}
.facts span{display:block;font-size:11px;color:var(--muted)}.facts b{font-size:12.5px;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
@media (max-width:640px){.flow2{display:grid;grid-template-columns:1fr 1fr;gap:8px}.flow2 .fs-a{display:none}
.flow{flex-direction:column}.arrow{flex-basis:22px}
.arrow::after{left:50%;top:3px;border:8px solid transparent;border-top:12px solid #7a8699;transform:translateX(-50%)}
.step{flex-direction:row;justify-content:center;align-items:baseline;gap:10px;padding:12px}.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.grid2{grid-template-columns:minmax(0,1fr)}.hd{flex-direction:column}.hdr{text-align:left}}
@media print{body{background:#fff}.page{padding:0}.card{break-inside:avoid}@page{size:A4;margin:10mm}}
"""
