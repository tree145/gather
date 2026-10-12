"""Isolated browser check + silent walkthrough capture; needs Playwright/Chromium.

Run from repository root: python scripts/check_gather.py
Uses its own database and server; never changes the normal demo catalog.
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "data" / "demo-artifacts"


def run():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gather-browser-") as tmp:
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        env = os.environ | {"GATHER_DB": str(Path(tmp) / "browser.db"), "GATHER_PORT": str(port)}
        base = f"http://127.0.0.1:{port}"
        process = subprocess.Popen([sys.executable, "-m", "gather"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("Demo server failed to start")
                try:
                    if httpx.get(f"{base}/api/demo/health", timeout=1, trust_env=False).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Demo server did not become ready")

            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1, record_video_dir=str(ARTIFACTS), record_video_size={"width": 1440, "height": 1000})
                page = context.new_page()
                errors, external = [], []
                page.on("pageerror", lambda error: errors.append(str(error)))

                def local_only(route):
                    if urlparse(route.request.url).hostname not in {"127.0.0.1", "localhost"}:
                        external.append(route.request.url)
                        route.abort()
                    else:
                        route.continue_()

                context.route("**/*", local_only)
                page.goto(base)
                expect(page.locator(".product-card")).to_have_count(3)
                expect(page.locator("#compare")).to_be_enabled()
                expect(page.locator("#budget")).to_have_value("3500")
                page.screenshot(path=str(ARTIFACTS / "01-home.png"), full_page=True)
                page.wait_for_timeout(1800)
                page.locator("#compare").click()
                expect(page.locator("#winner h3")).to_have_text("Trek 32 旅行背包")
                page.wait_for_timeout(1600)
                page.screenshot(path=str(ARTIFACTS / "02-recommendation.png"), full_page=True)

                # Consumer changes their own description; stale results disappear.
                page.locator("#needs").fill("")
                page.locator("#needs").press_sequentially("預算 3500 元，需要 16 吋筆電。重量不要超過 900 g，希望輕量。", delay=45)
                expect(page.locator("#results")).to_be_hidden()
                expect(page.locator("#compare")).to_be_disabled()
                page.locator("#parse").click()
                expect(page.locator("#weight")).to_have_value("900")
                page.wait_for_timeout(900)
                page.locator("#compare").click()
                expect(page.locator("#winner h3")).to_have_text("Transit 24 通勤背包")
                page.wait_for_timeout(1600)

                # Real file selection, submission, extraction and reranking.
                page.locator("#open-import").click()
                page.locator("#file").set_input_files(ROOT / "gather/static/sample-product.json")
                expect(page.locator("#product-name")).to_have_value("City 26 示範通勤背包")
                page.wait_for_timeout(1400)
                page.locator("#import-submit").click()
                expect(page.locator(".product-card")).to_have_count(4)
                expect(page.locator("#import-dialog")).not_to_be_visible()
                page.locator("#compare").click()
                expect(page.locator("#winner h3")).to_have_text("City 26 示範通勤背包")
                page.wait_for_timeout(1600)
                page.screenshot(path=str(ARTIFACTS / "03-imported-product.png"), full_page=True)

                # A low budget + 16-inch laptop must produce no recommendation.
                page.locator("#budget").fill("1800")
                page.locator("#decision-mode").select_option("strict")
                page.locator("#compare").click()
                expect(page.locator(".no-match")).to_be_visible()
                page.wait_for_timeout(1400)
                page.screenshot(path=str(ARTIFACTS / "04-no-match.png"), full_page=True)
                # Tradeoffs: raw spec favors A; accepted, conditional evidence can favor B.
                page.locator("#decision-mode").select_option("tradeoff")
                page.locator('[data-preset="carryon"]').click()
                expect(page.locator("#dimensions")).to_have_value("30x30x40")
                # The custom product remains available, but the example compares A and B only.
                for checkbox in page.locator("[data-select]").all():
                    if not checkbox.get_attribute("data-select").startswith("demo-cabin"):
                        checkbox.uncheck()
                page.locator("#compare").click()
                expect(page.locator("#winner h3")).to_have_text("A 規格符合包")
                page.wait_for_timeout(1300)
                page.locator("#accept-reviews").check()
                page.locator("#compare").click()
                expect(page.locator("#winner h3")).to_have_text("B 彈性隨身包")
                expect(page.locator("#winner")).to_contain_text("省下 NT$1,400")
                expect(page.locator("#winner")).to_contain_text("超出 5 cm")
                expect(page.locator("#winner .winner-tag")).to_contain_text("附條件可考慮")
                expect(page.locator("#winner .review-evidence")).to_contain_text("只裝七分滿")
                page.wait_for_timeout(2400)
                page.screenshot(path=str(ARTIFACTS / "06-carryon-tradeoff.png"), full_page=True)
                page.locator(".hard-options").first.locator("summary").click()
                page.locator('[data-hard="dimensions_cm"]').check()
                page.locator("#compare").click()
                expect(page.locator("#winner h3")).to_have_text("A 規格符合包")
                page.wait_for_timeout(800)
                video = page.video
                context.close()
                video.save_as(str(ARTIFACTS / "demo-walkthrough.webm"))
                video.delete()

                # Additional regression checks without cluttering the walkthrough.
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                context.route("**/*", local_only)
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base)
                expect(page.locator(".product-card")).to_have_count(4)  # persists after reload
                page.locator("[data-delete]").click()
                expect(page.locator(".product-card")).to_have_count(3)
                for checkbox in page.locator("[data-select]").all():
                    checkbox.uncheck()
                expect(page.locator("#compare")).to_be_disabled()
                page.locator("[data-select='demo-transit']").check()
                expect(page.locator("#compare")).to_be_enabled()

                # User text is displayed as text, never interpreted as markup.
                page.locator("#open-import").click()
                page.locator("#product-name").fill('<img src=x onerror="window.injected=true">')
                page.locator("#description").fill("售價：NT$2000。其他規格皆未提供。")
                page.locator("#import-submit").click()
                expect(page.locator(".product-card")).to_have_count(4)
                assert page.evaluate("window.injected === undefined")
                expect(page.locator(".product-name img")).to_have_count(0)
                page.locator("[data-delete]").click()
                expect(page.locator(".product-card")).to_have_count(3)

                # A failed API response remains visible and can be retried.
                page.route("**/api/demo/recommend", lambda route: route.fulfill(status=503, content_type="application/json", body='{"detail":"Temporary test failure"}'))
                page.locator("#compare").click()
                expect(page.locator("#error")).to_have_text("Temporary test failure")
                page.unroute("**/api/demo/recommend")
                page.locator("#compare").click()
                expect(page.locator("#winner h3")).to_have_text("Transit 24 通勤背包")

                page.set_viewport_size({"width": 390, "height": 844})
                page.goto(base)
                expect(page.locator("#compare")).to_be_enabled()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile horizontal overflow"
                page.locator("#compare").click()
                expect(page.locator("#winner h3")).to_have_text("Trek 32 旅行背包")
                page.wait_for_timeout(450)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile result overflow"
                page.screenshot(path=str(ARTIFACTS / "05-mobile.png"), full_page=True)
                context.close()
                browser.close()
                assert not errors, errors
                assert not external, external
                print("PASS: browser workflow, import, persistence, deletion, constraints, no-match, escaping, API retry, mobile layout; no external requests or JS errors.")
                print(f"Artifacts: {ARTIFACTS}")
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    run()
