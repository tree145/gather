"""Run without pytest: python -m unittest discover -s tests -p test_gather.py"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from gather.app import create_app
from gather.service import draft_requirements, extract_specs


class ExtractionTests(unittest.TestCase):
    def test_evidence_units_and_explicit_booleans(self):
        specs = extract_specs("售價：NT$3,280\n重量：1.38 kg\n容量：32 L\n筆電隔層：16 吋\n加厚背板：有\n腰帶：沒有")
        self.assertEqual(specs["price_ntd"]["value"], 3280)
        self.assertEqual(specs["weight_g"]["value"], 1380)
        self.assertIn("1.38 kg", specs["weight_g"]["evidence"])
        self.assertEqual(specs["capacity_l"]["value"], 32)
        self.assertEqual(specs["laptop_inches"]["value"], 16)
        self.assertTrue(specs["padded_back"]["value"])
        self.assertFalse(specs["hip_belt"]["value"])

    def test_missing_and_foreign_currency_are_unknown(self):
        specs = extract_specs("USD 150。舒服輕巧、很好背，適合筆電。腰帶資料未提供。")
        self.assertTrue(all(v["value"] is None for v in specs.values()))

    def test_requirements_preserve_context_and_parse_constraints(self):
        text = "預算 3,500 元，需要 16 吋筆電。重量不要超過 0.9 kg，容量至少 24 L，希望輕量。"
        req = draft_requirements(text)
        self.assertEqual(req.text, text)
        self.assertEqual((req.budget_ntd, req.max_weight_g, req.laptop_inches, req.min_capacity_l), (3500, 900, 16, 24))
        self.assertEqual(req.priority, "lightweight")


class DemoApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "demo.db"
        self.client = TestClient(create_app(self.db))
        self.client.__enter__()
        self.ids = [p["id"] for p in self.client.get("/api/demo/products").json()["products"] if p.get("scenario") == "everyday"]

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def recommend(self, ids=None, **overrides):
        req = {"text": "旅行與通勤使用", "budget_ntd": 3500, "laptop_inches": 16, "priority": "comfort", "decision_mode": "strict"}
        req.update(overrides)
        response = self.client.post("/api/demo/recommend", json={"product_ids": ids or self.ids, "requirements": req})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def upload(self, description="售價：NT$2000\n重量：700 g\n筆電隔層：16 吋"):
        response = self.client.post("/api/demo/products", json={"name": "我的商品", "description": description})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_local_assets_and_mode(self):
        self.assertEqual(self.client.get("/api/demo/health").json(), {"status": "ok", "mode": "offline_rules", "aws": False, "llm": False})
        for path in ["/", "/assets/app.js", "/assets/style.css", "/assets/sample-product.json"]:
            self.assertEqual(self.client.get(path).status_code, 200)

    def test_preference_and_hard_limits_change_winner(self):
        self.assertEqual(self.recommend()["winner_id"], "demo-trek")
        data = self.recommend(max_weight_g=900, priority="lightweight")
        self.assertEqual(data["winner_id"], "demo-transit")
        rows = {r["product"]["id"]: r for r in data["results"]}
        self.assertEqual(rows["demo-trek"]["status"], "excluded")
        self.assertEqual(rows["demo-lite"]["status"], "excluded")
        self.assertEqual(data["persona"]["budget"]["flexibility"], "hard")
        self.assertEqual(data["persona"]["criteria"][0]["attribute"], "weight")

    def test_no_eligible_product_is_not_recommended(self):
        data = self.recommend(budget_ntd=1800)
        self.assertIsNone(data["winner_id"])
        self.assertTrue(all(r["status"] == "excluded" for r in data["results"]))
        self.assertEqual(self.recommend(budget_ntd=1800, laptop_inches=None, priority="value")["winner_id"], "demo-lite")

    def test_unknown_required_spec_is_pending_not_a_match(self):
        product = self.upload("售價：NT$1000，適合旅行使用。沒有提供筆電隔層的尺寸資訊。")
        data = self.recommend(ids=[product["id"]])
        self.assertIsNone(data["winner_id"])
        self.assertEqual(data["results"][0]["status"], "excluded")
        self.assertEqual(data["results"][0]["checks"][1]["status"], "unknown")
        self.assertIsNone(product["specs"]["laptop_inches"]["value"])
        self.assertIsNone(product["review"])

    def test_import_and_persistence_and_delete(self):
        product = self.upload("<h1>測試商品</h1><p>售價：NT$2,000</p><p>重量：0.7 kg</p><p>筆電隔層：16 吋</p><script>window.bad=true;</script>")
        self.assertEqual(product["specs"]["weight_g"]["value"], 700)
        self.assertNotIn("window.bad", product["description"])
        with TestClient(create_app(self.db)) as second:
            self.assertEqual(len(second.get("/api/demo/products").json()["products"]), 6)
            self.assertEqual(second.delete(f"/api/demo/products/{product['id']}").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/demo/products/{product['id']}").status_code, 404)
        self.assertEqual(self.client.delete("/api/demo/products/demo-trek").status_code, 400)

    def test_invalid_input_and_missing_id(self):
        for body in ({"text": "   "}, {"text": "ab"}, {"text": "預算 999999999 元"}):
            self.assertEqual(self.client.post("/api/demo/requirements", json=body).status_code, 422)
        for req in ({"text": "旅行使用", "budget_ntd": -1}, {"text": "旅行使用", "priority": "invented"}):
            self.assertEqual(self.client.post("/api/demo/recommend", json={"product_ids": self.ids, "requirements": req}).status_code, 422)
        self.assertEqual(self.client.post("/api/demo/recommend", json={"product_ids": [], "requirements": {"text": "旅行使用"}}).status_code, 422)
        self.assertEqual(self.client.post("/api/demo/recommend", json={"product_ids": ["missing"], "requirements": {"text": "旅行使用"}}).status_code, 404)

    def test_fixtures_are_labeled_and_reviews_do_not_affect_ranking(self):
        from gather.models import Requirements
        from gather.service import recommend
        products = self.client.get("/api/demo/products").json()["products"]
        self.assertTrue(all(p["is_demo"] for p in products))
        req = Requirements(text="旅行使用", priority="comfort")
        before = recommend(products, req)
        for product in products:
            product["review"] = {"text": "This should never affect ranking."}
        after = recommend(products, req)
        self.assertEqual([(r["product"]["id"], r["score"]) for r in before["results"]], [(r["product"]["id"], r["score"]) for r in after["results"]])

    def test_startup_and_complete_flow_without_network_or_aws(self):
        script = '''
import socket, sys
from unittest.mock import patch
from fastapi.testclient import TestClient
from gather.app import create_app
from pathlib import Path
original_connect = socket.socket.connect
def local_only(sock, address):
    # Windows asyncio creates a loopback socket pair for its event loop.
    assert address[0] in ('127.0.0.1', '::1'), 'Unexpected outbound connection'
    return original_connect(sock, address)
with patch.object(socket.socket, 'connect', local_only):
    with TestClient(create_app(Path(sys.argv[1]))) as client:
        products = client.get('/api/demo/products').json()['products']
        body = {'product_ids': [p['id'] for p in products], 'requirements': {'text': 'local test', 'priority': 'comfort'}}
        assert client.post('/api/demo/recommend', json=body).json()['winner_id'] == 'demo-trek'
assert 'boto3' not in sys.modules
assert 'backend.llm' not in sys.modules
'''
        result = subprocess.run([sys.executable, "-c", script, str(self.db)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_imperfect_products_still_get_a_relative_recommendation(self):
        result = self.recommend(budget_ntd=1800, decision_mode="tradeoff")
        self.assertIsNotNone(result["winner_id"])
        winner = next(r for r in result["results"] if r["product"]["id"] == result["winner_id"])
        self.assertEqual(winner["status"], "compromise")
        self.assertTrue(winner["cautions"])
        self.assertEqual(result["persona"]["budget"]["flexibility"], "soft")

    def test_carryon_evidence_changes_ranking_only_with_user_acceptance(self):
        kwargs = dict(ids=["demo-cabin-a", "demo-cabin-b"], decision_mode="tradeoff",
                      max_dimensions_cm=[30, 30, 40], laptop_inches=None,
                      priority="value", wants_bottle_pocket=True)
        self.assertEqual(self.recommend(**kwargs)["winner_id"], "demo-cabin-a")
        result = self.recommend(**kwargs, accept_review_conditions=True)
        self.assertEqual(result["winner_id"], "demo-cabin-b")
        winner = result["results"][0]
        self.assertEqual(winner["status"], "conditional")
        self.assertEqual(winner["product"]["specs"]["dimensions_cm"]["value"], [30, 20, 45])
        self.assertIn("1,400", winner["reasons"][0])
        self.assertTrue(winner["applied_evidence"]["conditions"])
        self.assertEqual(self.recommend(**kwargs, accept_review_conditions=True, hard_constraints=["dimensions_cm"])["winner_id"], "demo-cabin-a")

    def test_conflicting_or_inapplicable_evidence_cannot_resolve_size_gap(self):
        from copy import deepcopy
        from gather.models import Requirements
        from gather.service import recommend
        products = [p for p in self.client.get("/api/demo/products").json()["products"] if p.get("scenario") == "carryon"]
        req = Requirements(text="隨身包省錢", priority="value", max_dimensions_cm=[40, 30, 30],
                           accept_review_conditions=True, wants_bottle_pocket=True)
        for mode in ("conflict", "too_large", "no_evidence"):
            changed = deepcopy(products)
            bag = next(p for p in changed if p["id"] == "demo-cabin-b")
            if mode == "conflict":
                counterexample = deepcopy(bag["compression_evidence"][0])
                counterexample["stance"] = "conflicting"
                bag["compression_evidence"].append(counterexample)
            elif mode == "too_large":
                bag["compression_evidence"][0]["compressed_dimensions_cm"] = [30, 20, 42]
            else:
                bag["compression_evidence"] = []
            result = recommend(changed, req)
            self.assertEqual(result["winner_id"], "demo-cabin-a", mode)
            self.assertTrue(all(r["applied_evidence"] is None for r in result["results"]), mode)
        products[0]["specs"]["price_ntd"]["value"] = 1000
        self.assertEqual(recommend(products, req)["winner_id"], "demo-cabin-a")  # not tied to product ID

    def test_review_upload_validation_and_roundtrip(self):
        item = {"name": "測試隨身包", "description": "售價：NT$1400\n尺寸：30x20x45 cm\n水壺袋：有",
                "compression_evidence": [{"source_label": "自備心得", "quote": "頂部放衣服才能壓縮", "conditions": "裝載七分滿", "compressed_dimensions_cm": [30, 20, 40]}]}
        response = self.client.post("/api/demo/products", json=item)
        self.assertEqual(response.status_code, 201)
        saved = next(p for p in self.client.get("/api/demo/products").json()["products"] if p["id"] == response.json()["id"])
        self.assertEqual(saved["compression_evidence"][0]["quote"], "頂部放衣服才能壓縮")
        item["compression_evidence"][0]["compressed_dimensions_cm"] = [0, 20, 40]
        self.assertEqual(self.client.post("/api/demo/products", json=item).status_code, 422)


if __name__ == "__main__":
    unittest.main()
