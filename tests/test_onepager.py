"""네트워크 없이 돌아가는 테스트:  python -m unittest discover -s tests"""
import json
import unittest

from onepager import narrative
from onepager.fmt import money, pct
from onepager.render import render
from onepager.resolver import ResolveError, resolve
from onepager.sample import sample_data


class ResolverTest(unittest.TestCase):
    def check(self, q, symbol, market):
        t = resolve(q, search=lambda _: [])
        self.assertEqual((t.symbol, t.market), (symbol, market), q)

    def test_aliases(self):
        self.check("삼성전자", "005930.KS", "KR")
        self.check("SK 하이닉스", "000660.KS", "KR")
        self.check("애플", "AAPL", "US")
        self.check("토요타", "7203.T", "JP")
        self.check("텐센트", "0700.HK", "HK")
        self.check("마오타이", "600519.SS", "CN")
        self.check("에코프로비엠", "247540.KQ", "KR")

    def test_codes(self):
        self.check("AAPL", "AAPL", "US")
        self.check("BRK.B", "BRK-B", "US")
        self.check("005930", "005930.KS", "KR")
        self.check("247540.kq", "247540.KQ", "KR")
        self.check("7203", "7203.T", "JP")
        self.check("700.HK", "0700.HK", "HK")
        self.check("HK:9988", "9988.HK", "HK")
        self.check("CN:600519", "600519.SS", "CN")
        self.check("CN:000858", "000858.SZ", "CN")
        self.check("300750.SZ", "300750.SZ", "CN")

    def test_search_fallback_filters_unsupported_exchanges(self):
        results = [
            {"symbol": "XYZ.L", "quoteType": "EQUITY", "longname": "London Co"},
            {"symbol": "6501.T", "quoteType": "EQUITY", "longname": "Hitachi, Ltd."},
        ]
        t = resolve("hitachi", search=lambda _: results)
        self.assertEqual((t.symbol, t.market, t.name), ("6501.T", "JP", "Hitachi, Ltd."))

    def test_not_found(self):
        with self.assertRaises(ResolveError):
            resolve("없는회사이름", search=lambda _: [])
        with self.assertRaises(ResolveError):
            resolve("  ")


class FmtTest(unittest.TestCase):
    def test_money(self):
        self.assertEqual(money(1.367e10, "USD"), "137억 달러")
        self.assertEqual(money(4.5e14, "KRW"), "450조 원")
        self.assertEqual(money(3.2e12, "JPY"), "3.2조 엔")
        self.assertEqual(money(6e8, "USD"), "6.0억 달러")
        self.assertEqual(money(71200, "KRW", compact=False), "71,200원")
        self.assertEqual(money(260.5, "USD", compact=False), "260.50 달러")
        self.assertEqual(money(None), "–")

    def test_pct(self):
        self.assertEqual(pct(0.227, sign=True), "+22.7%")
        self.assertEqual(pct(-0.05), "-5.0%")


class NarrativeTest(unittest.TestCase):
    def test_rule_based(self):
        d = sample_data()
        n = narrative.rule_based(d)
        self.assertIn("미국", n.one_liner)
        self.assertIn("경기소비재", n.one_liner)
        self.assertEqual(len(n.flow), 4)
        self.assertTrue(any("영업이익률" in x for x in n.financial_comment))
        self.assertIn("17명", n.analyst_summary)
        self.assertIn("+5.2%", n.analyst_summary)   # 273.43 / 260 - 1
        self.assertTrue(any(x.startswith("Five Below, Inc. operates") for x in n.overview))

    def test_parse_llm_json(self):
        d = sample_data()
        text = "결과:\n" + json.dumps({
            "one_liner": "전 품목 5달러 이하 잡화점",
            "overview": ["본사 필라델피아"],
            "flow": [["상품 조달", "저가 수입"], ["매장", "1,970개"], ["10대 고객", "구매"], ["매출", "판매"]],
            "financial_comment": ["매출 성장"],
            "analyst_summary": "매수 우위",
            "news_ko": ["a", "b"],   # 개수 불일치 → 원문 사용
        }, ensure_ascii=False)
        n = narrative.parse_llm_json(text, d)
        self.assertEqual(n.source, "llm")
        self.assertEqual(n.flow[0], ("상품 조달", "저가 수입"))
        self.assertEqual(len(n.news_ko), len(d.news))

    def test_build_without_key_is_rule(self):
        self.assertEqual(narrative.build(sample_data(), use_llm=False).source, "rule")


class RenderTest(unittest.TestCase):
    def test_render_sections(self):
        d = sample_data()
        html = render(d, narrative.rule_based(d))
        for s in ("회사 개요", "이 회사는 이렇게 돈을 번다", "재무 요약", "애널리스트 의견", "최근 뉴스", "주가 (1년)"):
            self.assertIn(s, html)
        self.assertEqual(html.count("<svg"), 2)   # 주가, 매출
        self.assertEqual(html.count('class="step"'), 4)   # 사업 구조 그림

    def test_escapes_html(self):
        d = sample_data()
        d.ticker.name = "<script>x</script>"
        html = render(d, narrative.rule_based(d))
        self.assertNotIn("<script>x", html)

    def test_handles_missing_data(self):
        d = sample_data()
        d.financials, d.price_history, d.news = [], [], []
        d.analyst.target_mean = d.analyst.target_low = d.analyst.target_high = None
        d.pe = d.price = None
        html = render(d, narrative.rule_based(d))
        self.assertIn("재무 데이터 없음", html)
        self.assertIn("최근 뉴스 없음", html)


class DataParseTest(unittest.TestCase):
    def test_google_rss(self):
        from onepager.data import parse_google_rss
        xml = b"""<?xml version="1.0"?><rss><channel>
        <item><title>A news - Pub1</title><link>http://a</link><pubDate>Tue, 01 Sep 2026 10:00:00 GMT</pubDate><source>Pub1</source></item>
        <item><title>B news - Pub2</title><link>http://b</link><pubDate>Wed, 02 Sep 2026 10:00:00 GMT</pubDate><source>Pub2</source></item>
        </channel></rss>"""
        items = parse_google_rss(xml)
        self.assertEqual([i.title for i in items], ["B news", "A news"])
        self.assertEqual(items[0].date, "2026-09-02")

    def test_yf_news_both_formats(self):
        from onepager.data import parse_yf_news
        items = parse_yf_news([
            {"content": {"title": "New", "pubDate": "2026-09-02T12:00:00Z",
                         "provider": {"displayName": "Reuters"}, "canonicalUrl": {"url": "http://n"}}},
            {"title": "Old", "publisher": "AP", "link": "http://o", "providerPublishTime": 1788000000},
        ])
        self.assertEqual((items[0].title, items[0].publisher, items[0].date), ("New", "Reuters", "2026-09-02"))
        self.assertEqual((items[1].title, items[1].publisher), ("Old", "AP"))

    def test_parse_info(self):
        from onepager.data import parse_info
        from onepager.models import Ticker
        d = parse_info(Ticker("005930.KS", "삼성전자", "KR"), {
            "currentPrice": 70000, "previousClose": 69000, "currency": "KRW",
            "dividendRate": 1444, "recommendationKey": "buy", "numberOfAnalystOpinions": 30,
            "targetMeanPrice": 90000, "trailingPE": float("nan")})
        self.assertAlmostEqual(d.change_pct, 70000 / 69000 - 1)
        self.assertAlmostEqual(d.dividend_yield, 1444 / 70000)
        self.assertEqual((d.analyst.rating, d.analyst.n_analysts, d.pe), ("매수", 30, None))


if __name__ == "__main__":
    unittest.main()
