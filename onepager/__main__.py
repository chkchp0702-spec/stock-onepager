"""CLI: python -m onepager "삼성전자" [-o report.html] [--no-llm] [--sample]"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="onepager", description="원 페이지 종목 리포트 생성")
    p.add_argument("query", nargs="?", help="종목명 또는 코드 (예: 애플, 005930, 7203.T, 0700.HK)")
    p.add_argument("-o", "--out", help="저장할 HTML 경로 (기본: reports/<종목>.html)")
    p.add_argument("--no-llm", action="store_true", help="Claude API 요약을 쓰지 않음")
    p.add_argument("--sample", action="store_true", help="네트워크 없이 예시 데이터로 생성")
    a = p.parse_args(argv)

    if a.sample:
        from .narrative import rule_based
        from .render import render
        from .sample import sample_data
        d = sample_data()
        name, html = d.ticker.name, render(d, rule_based(d))
    else:
        if not a.query:
            p.error("종목명을 입력하세요.")
        from . import ResolveError, make_report
        try:
            name, html = make_report(a.query, use_llm=False if a.no_llm else None)
        except (ResolveError, LookupError) as ex:
            print(f"오류: {ex}", file=sys.stderr)
            return 1

    out = Path(a.out) if a.out else Path("reports") / (re.sub(r"[^\w가-힣.-]+", "_", name) + ".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
