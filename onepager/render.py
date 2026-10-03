"""StockData + Narrative → 한 장짜리 HTML 리포트 (인쇄/PDF 저장 가능)."""
from __future__ import annotations

from html import escape as _e

from .fmt import money, pct, price, unit
from .models import Narrative, StockData

MARKET_LABEL = {"US": "미국", "KR": "한국", "JP": "일본", "CN": "중국", "HK": "홍콩"}


def e(x) -> str:
    return _e(str(x)) if x is not None else ""


# ── SVG 그림 ─────────────────────────────────────────────────────

FLOW_COLORS = ["#1f4e9c", "#2f6fb5", "#2c8a5a", "#1d6b45"]


def flow_html(flow: list[tuple[str, str]], center: str) -> str:
    """회사가 돈을 버는 구조: 상자 → 화살표 → 상자 (모바일에서는 세로로 쌓임)."""
    parts = [f'<div class="flow" role="img" aria-label="{e(center)} 사업 구조">']
    for i, (title, desc) in enumerate(flow):
        c = FLOW_COLORS[i % len(FLOW_COLORS)]
        if i:
            parts.append('<div class="arrow" aria-hidden="true"></div>')
        parts.append(f'<div class="step" style="--c:{c}"><span class="no">{i + 1}</span>'
                     f'<b>{e(title)}</b><small>{e(desc)}</small></div>')
    parts.append("</div>")
    return "".join(parts)


def price_svg(hist: list[tuple[str, float]], currency: str) -> str:
    if len(hist) < 2:
        return '<div class="muted">차트 데이터 없음</div>'
    W, H, pad_l, pad_b, pad_t = 320, 130, 4, 18, 10
    vals = [v for _, v in hist]
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    step = (W - pad_l * 2) / (len(vals) - 1)
    pts = [(pad_l + i * step, pad_t + (hi - v) / rng * (H - pad_t - pad_b)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{pts[0][0]:.1f},{H - pad_b} {line} {pts[-1][0]:.1f},{H - pad_b}"
    up = vals[-1] >= vals[0]
    c = "#c0392b" if up else "#1f4e9c"   # 한국식: 상승 빨강, 하락 파랑
    chg = vals[-1] / vals[0] - 1
    first, last = hist[0][0], hist[-1][0]
    return (f'<svg viewBox="0 0 {W} {H}" class="spark" role="img" aria-label="1년 주가">'
            f'<polygon points="{area}" fill="{c}" opacity="0.10"/>'
            f'<polyline points="{line}" fill="none" stroke="{c}" stroke-width="1.8"/>'
            f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3" fill="{c}"/>'
            f'<text x="{pad_l}" y="{H - 4}" class="ax">{e(first)}</text>'
            f'<text x="{W - pad_l}" y="{H - 4}" class="ax" text-anchor="end">{e(last)}</text>'
            f'<text x="{W - pad_l}" y="12" class="ax" text-anchor="end" fill="{c}">1년 {pct(chg, sign=True)}</text>'
            f'</svg>'
            f'<div class="muted small">최고 {price(hi, currency)} · 최저 {price(lo, currency)}</div>')


def revenue_svg(d: StockData) -> str:
    f = [y for y in d.financials if y.revenue]
    if not f:
        return ""
    W, H, top, bot = 320, 140, 22, 20
    mx = max(y.revenue for y in f)
    bw = min(48, (W - 20) / len(f) - 16)
    slot = (W - 20) / len(f)
    out = [f'<svg viewBox="0 0 {W} {H}" class="bars" role="img" aria-label="연도별 매출과 영업이익률">']
    for i, y in enumerate(f):
        h = (H - top - bot) * y.revenue / mx
        x = 10 + i * slot + (slot - bw) / 2
        last = i == len(f) - 1
        out.append(f'<rect x="{x:.1f}" y="{H - bot - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="3" '
                   f'fill="{"#1d6b45" if last else "#b8c4d6"}"/>')
        out.append(f'<text x="{x + bw / 2:.1f}" y="{H - bot - h - 4:.1f}" text-anchor="middle" class="ax">'
                   f'{e(money(y.revenue, d.currency).replace(" " + unit(d.currency), ""))}</text>')
        out.append(f'<text x="{x + bw / 2:.1f}" y="{H - 5}" text-anchor="middle" class="ax">{e(y.period)}</text>')
        if y.op_margin is not None:
            out.append(f'<text x="{x + bw / 2:.1f}" y="{H - bot - 6:.1f}" text-anchor="middle" class="ax inv">'
                       f'{pct(y.op_margin, digits=0)}</text>')
    out.append("</svg>")
    out.append(f'<div class="muted small">막대: 매출({e(unit(d.currency))}) · 막대 안 숫자: 영업이익률</div>')
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


# ── 페이지 ───────────────────────────────────────────────────────

def render(d: StockData, nv: Narrative) -> str:
    t = d.ticker
    cur = d.currency
    chg = ""
    if d.change_pct is not None:
        cls = "up" if d.change_pct >= 0 else "down"
        chg = f'<span class="{cls}">{pct(d.change_pct, sign=True, digits=2)}</span>'

    upside = ""
    if d.analyst.target_mean and d.price:
        upside = f"현재가 대비 {pct(d.analyst.target_mean / d.price - 1, sign=True)}"

    kpis = [
        ("주가", price(d.price, cur), chg or "전일 대비", "k1"),
        ("시가총액", money(d.market_cap, cur), f"52주 {price(d.week52_low, cur)} ~ {price(d.week52_high, cur)}", "k2"),
        ("PER · PBR", f"{d.pe:.1f}배" if d.pe else "–", f"PBR {d.pb:.1f}배" if d.pb else "PBR –", "k3"),
        ("평균 목표주가", price(d.analyst.target_mean, cur) if d.analyst.target_mean else "–",
         upside or (d.analyst.rating or "의견 없음"), "k4"),
    ]
    kpi_html = "".join(
        f'<div class="kpi {c}"><div class="kl">{e(l)}</div><div class="kv">{e(v)}</div><div class="ks">{s}</div></div>'
        for l, v, s, c in kpis)

    fin_rows = "".join(
        f"<tr><td>{e(y.period)}</td><td>{e(money(y.revenue, cur))}</td><td>{e(money(y.operating_income, cur))}</td>"
        f"<td>{e(pct(y.op_margin))}</td><td>{e(money(y.net_income, cur))}</td>"
        f"<td>{e(price(y.eps, cur) if y.eps is not None else '–')}</td></tr>"
        for y in reversed(d.financials))
    fin_table = (f'<div class="tblwrap"><table class="fin"><thead><tr><th>연도</th><th>매출</th><th>영업이익</th><th>이익률</th>'
                 f'<th>순이익</th><th>EPS</th></tr></thead><tbody>{fin_rows}</tbody></table></div>'
                 if fin_rows else '<div class="muted">재무 데이터 없음</div>')

    news_items = []
    for i, n in enumerate(d.news):
        title = nv.news_ko[i] if i < len(nv.news_ko) else n.title
        link = f'<a href="{e(n.link)}" target="_blank" rel="noopener">{e(title)}</a>' if n.link else e(title)
        news_items.append(f'<li>{link}<span class="muted small"> · {e(n.publisher)} {e(n.date)}</span></li>')
    news_html = f'<ul class="news">{"".join(news_items)}</ul>' if news_items else '<div class="muted">최근 뉴스 없음</div>'

    actions = "".join(f"<li>{e(x)}</li>" for x in d.analyst.recent_actions)
    actions_html = f'<div class="sub">최근 의견 변경</div><ul class="dense">{actions}</ul>' if actions else ""

    exch = f"{MARKET_LABEL.get(t.market, t.market)} · {t.symbol}"
    gen = "Claude 요약" if nv.source == "llm" else "자동 요약"

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(t.name)} 원 페이지 리포트</title>
<style>{CSS}</style></head>
<body><main class="page">
<header class="hd">
  <div><h1>{e(t.name)} <span class="tk">{e(exch)}</span></h1>
  <div class="one">{e(nv.one_liner)}</div></div>
  <div class="hdr">{e(d.as_of)}<br>통화 {e(unit(cur))}</div>
</header>
<section class="kpis">{kpi_html}</section>

<section class="grid2">
  <div class="card">
    <h2>회사 개요</h2>
    <ul class="dense">{"".join(f"<li>{e(x)}</li>" for x in nv.overview)}</ul>
  </div>
  <div class="card">
    <h2>주가 (1년)</h2>
    {price_svg(d.price_history, cur)}
  </div>
</section>

<section class="card">
  <h2>이 회사는 이렇게 돈을 번다</h2>
  {flow_html(nv.flow, t.name)}
</section>

<section class="grid2">
  <div class="card">
    <h2>재무 요약</h2>
    {fin_table}
    <ul class="dense mt">{"".join(f"<li>{e(x)}</li>" for x in nv.financial_comment)}</ul>
  </div>
  <div class="card">
    <h2>매출 추이</h2>
    {revenue_svg(d) or '<div class="muted">데이터 없음</div>'}
  </div>
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

<footer class="ft">출처: Yahoo Finance(시세·재무·애널리스트), Google News(뉴스) · {e(gen)} · {e(d.as_of)} 기준.
정보 제공 목적이며 투자 권유가 아님. 시세는 지연될 수 있으므로 매매 전 증권사에서 확인하세요. 투자 판단과 책임은 투자자 본인에게 있습니다.</footer>
</main></body></html>"""


CSS = """
:root{--navy:#14284b;--ink:#1c2533;--muted:#6b7686;--line:#e2e7ef;--bg:#f4f6fa;--card:#fff;
--green:#1d6b45;--red:#c0392b;--blue:#1f4e9c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:"Pretendard","Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",system-ui,sans-serif;font-size:14px;line-height:1.5}
.page{max-width:900px;margin:0 auto;padding:16px}
.hd{background:var(--navy);color:#fff;border-radius:10px;padding:16px 20px;display:flex;justify-content:space-between;gap:12px}
.hd h1{margin:0;font-size:24px}.tk{font-size:14px;color:#f4c542;font-weight:600;margin-left:6px}
.one{margin-top:4px;color:#d7dfee}.hdr{text-align:right;font-size:12px;color:#b9c4d8;white-space:nowrap}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:10px 0}
.kpi{border-radius:8px;padding:10px;color:#fff;text-align:center}
.k1{background:#1f4e9c}.k2{background:#1c355e}.k3{background:#2c6a4f}.k4{background:#5b6675}
.kl{font-size:12px;opacity:.85}.kv{font-size:20px;font-weight:700}.ks{font-size:11px;opacity:.9}
.ks .up{color:#ffd0c8}.ks .down{color:#cfe0ff}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:10px}
h2{font-size:15px;margin:0 0 8px;padding-left:8px;border-left:4px solid var(--blue)}
.dense{margin:0;padding-left:18px}.dense li{margin:2px 0}.mt{margin-top:8px}
.muted{color:var(--muted)}.small{font-size:11px}.sub{font-weight:600;margin-top:8px;font-size:13px}
svg{width:100%;height:auto;display:block}
.flow{display:flex;align-items:stretch;gap:0}
.step{flex:1;position:relative;border:1px solid var(--c);background:color-mix(in srgb,var(--c) 8%,#fff);border-radius:10px;
padding:16px 8px 12px;text-align:center;display:flex;flex-direction:column;gap:4px;min-width:0}
.step b{color:var(--c);font-size:15px}.step small{color:#4a5566;font-size:12px}
.step .no{position:absolute;top:-9px;left:10px;width:20px;height:20px;border-radius:50%;background:var(--c);color:#fff;font-size:11px;font-weight:700;line-height:20px}
.arrow{flex:0 0 26px;position:relative}
.arrow::after{content:"";position:absolute;top:50%;left:5px;border:8px solid transparent;border-left:12px solid #7a8699;transform:translateY(-50%)}
.tblwrap{overflow-x:auto}
.ax{font-size:10px;fill:#6b7686}.ax.inv{fill:#fff;font-weight:700}
table.fin{width:100%;border-collapse:collapse;font-size:12px}
.fin th,.fin td{white-space:nowrap}.fin th{background:var(--navy);color:#fff;font-weight:600;padding:4px}.fin td{padding:4px;border-bottom:1px solid var(--line);text-align:right}
.fin td:first-child{text-align:left;font-weight:600}
.rbar{display:flex;height:22px;border-radius:5px;overflow:hidden;margin:6px 0;font-size:11px;color:#fff}
.rbar div{display:flex;align-items:center;justify-content:center;white-space:nowrap;overflow:hidden}
.trange{position:relative;height:36px;margin:22px 8px 2px;background:linear-gradient(#e2e7ef,#e2e7ef) center/100% 4px no-repeat}
.track{position:absolute;top:15px;height:6px;background:#9bc3ad;border-radius:3px}
.tick{position:absolute;top:8px;width:2px;height:20px;transform:translateX(-1px)}
.tick span{position:absolute;left:50%;transform:translateX(-50%);font-size:10px;white-space:nowrap}
.tick.now{background:var(--red)}.tick.now span{top:-16px;color:var(--red)}
.tick.mean{background:var(--green)}.tick.mean span{top:20px;color:var(--green)}
.flexb{display:flex;justify-content:space-between}
.news{margin:0;padding-left:18px}.news li{margin:4px 0}.news a{color:var(--ink);text-decoration:none}.news a:hover{text-decoration:underline}
.up{color:var(--red)}.down{color:var(--blue)}
.ft{font-size:10.5px;color:var(--muted);padding:4px 2px 12px}
@media (max-width:640px){.flow{flex-direction:column}.arrow{flex-basis:22px}
.arrow::after{left:50%;top:3px;border:8px solid transparent;border-top:12px solid #7a8699;transform:translateX(-50%)}
.step{flex-direction:row;justify-content:center;align-items:baseline;gap:10px;padding:12px}.kpis{grid-template-columns:repeat(2,1fr)}.grid2{grid-template-columns:1fr}.hd{flex-direction:column}.hdr{text-align:left}}
@media print{body{background:#fff}.page{padding:0}.card{break-inside:avoid}@page{size:A4;margin:10mm}}
"""
