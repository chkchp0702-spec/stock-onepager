"""종목명 하나로 원 페이지 종목 리포트(HTML)를 만드는 패키지."""
from __future__ import annotations

from typing import Optional

from . import narrative
from .render import render
from .resolver import ResolveError, resolve

__all__ = ["make_report", "ResolveError"]


def make_report(query: str, use_llm: Optional[bool] = None) -> tuple[str, str]:
    """종목명/코드 → (종목명, HTML)."""
    from .data import fetch

    ticker = resolve(query)
    data = fetch(ticker)
    nv = narrative.build(data, use_llm=use_llm)
    return ticker.name, render(data, nv)
