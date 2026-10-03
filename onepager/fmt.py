"""숫자 표기 (한국식 조·억 단위)."""
from __future__ import annotations

from typing import Optional

CUR_KO = {"USD": "달러", "KRW": "원", "JPY": "엔", "CNY": "위안", "HKD": "홍콩달러"}


def unit(currency: str) -> str:
    return CUR_KO.get(currency, currency)


def money(v: Optional[float], currency: str = "USD", compact: bool = True) -> str:
    if v is None:
        return "–"
    u = unit(currency)
    neg = "-" if v < 0 else ""
    a = abs(v)
    if not compact or a < 1e4:
        dec = 0 if currency in ("KRW", "JPY") or a >= 1000 else 2
        return f"{neg}{a:,.{dec}f}{u}" if u in ("원", "엔") else f"{neg}{a:,.{dec}f} {u}"
    if a >= 1e12:
        jo = a / 1e12
        return f"{neg}{jo:,.1f}조 {u}" if jo < 100 else f"{neg}{jo:,.0f}조 {u}"
    if a >= 1e8:
        return f"{neg}{a / 1e8:,.0f}억 {u}" if a >= 1e10 else f"{neg}{a / 1e8:,.1f}억 {u}"
    return f"{neg}{a / 1e4:,.0f}만 {u}"


def price(v: Optional[float], currency: str = "USD") -> str:
    return money(v, currency, compact=False)


def pct(v: Optional[float], sign: bool = False, digits: int = 1) -> str:
    if v is None:
        return "–"
    return f"{v * 100:+.{digits}f}%" if sign else f"{v * 100:.{digits}f}%"
