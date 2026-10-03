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

from .fmt import money, pct, price, unit
from .models import Narrative, StockData

MARKET_LABEL = {"US": "미국", "KR": "한국", "JP": "일본", "CN": "중국", "HK": "홍콩"}
MARKET_FLAG = {"US": "🇺🇸", "KR": "🇰🇷", "JP": "🇯🇵", "CN": "🇨🇳", "HK": "🇭🇰"}
UP, DN = "#c0392b", "#1f4e9c"   # 한국식: 상승 빨강 · 하락 파랑


def e(x) -> str:
    return _e(str(x)) if x is not None else ""


# ── 그림 조각 ───────────────────────────────────────────────────

FLOW_COLORS = ["#1f4e9c", "#2f6fb5", "#2c8a5a", "#1d6b45"]


def flow_html(flow: list[tuple[str, str]], center: str) -> str:
    """회사가 돈을 버는 구조: 상자 → 화살표 → 상자 (휴대폰에서는 세로)."""
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

def render(d: StockData, nv: Narrative) -> str:
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
        ("주가", price(d.price, cur), chg or "전일 대비", "k1"),
        ("시가총액", money(d.market_cap, cur), f"PER {d.pe:.1f}배" if d.pe else "PER –", "k2"),
        ("PBR", f"{d.pb:.1f}배" if d.pb else "–", f"배당 {pct(d.dividend_yield)}" if d.dividend_yield else "배당 없음·미확인", "k3"),
        ("평균 목표주가", price(d.analyst.target_mean, cur) if d.analyst.target_mean else "–",
         upside or (d.analyst.rating or "의견 없음"), "k4"),
    ]
    kpi_html = "".join(
        f'<div class="kpi {c}"><div class="kl">{e(l)}</div><div class="kv">{e(v)}</div><div class="ks">{s}</div></div>'
        for l, v, s, c in kpis)

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
    gen = "Claude 요약" if nv.source == "llm" else "자동 요약"
    translated = bool(d.business_summary_ko)

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(t.name)} 원 페이지 리포트</title>
<style>{CSS}</style></head>
<body><main class="page">
<header class="hd">
  <div class="hd-l"><div class="tk">{e(exch)}</div><h1>{e(t.name)}</h1>
  <div class="one">{e(nv.one_liner)}</div></div>
  <div class="hdr">{e(d.as_of)}<br>통화 {e(unit(cur))}</div>
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
  {flow_html(nv.flow, t.name)}
</section>

<section class="grid2">
  <div class="card">
    <h2>매출 추이</h2>
    {revenue_svg(d) or '<div class="muted">데이터 없음</div>'}
    {fin_comments}
  </div>
  <div class="card">
    <h2>재무 숫자</h2>
    {fin_table(d)}
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

<footer class="ft">출처: Yahoo Finance(시세·재무·애널리스트), Google News(뉴스){' · 회사 설명은 자동 번역' if translated else ''} · {e(gen)} · {e(d.as_of)} 기준.
정보 제공 목적이며 투자 권유가 아님. 시세는 지연될 수 있으므로 매매 전 증권사에서 확인하세요. 투자 판단과 책임은 투자자 본인에게 있습니다.</footer>
</main></body></html>"""


CSS = """
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
@media (max-width:640px){.flow{flex-direction:column}.arrow{flex-basis:22px}
.arrow::after{left:50%;top:3px;border:8px solid transparent;border-top:12px solid #7a8699;transform:translateX(-50%)}
.step{flex-direction:row;justify-content:center;align-items:baseline;gap:10px;padding:12px}.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.grid2{grid-template-columns:minmax(0,1fr)}.hd{flex-direction:column}.hdr{text-align:left}}
@media print{body{background:#fff}.page{padding:0}.card{break-inside:avoid}@page{size:A4;margin:10mm}}
"""
