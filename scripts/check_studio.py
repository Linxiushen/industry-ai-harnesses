"""Exercise the published UI and Python worker on a GitHub-hosted Linux runner."""
import argparse
import json
import shutil
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import expect, sync_playwright


def exercise(url):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which("google-chrome"), headless=True)
        page = browser.new_page(accept_downloads=True)
        page.goto(url)
        page.locator('#record-mode[data-live="false"]').wait_for()
        cases = (
            ("pharma", "检索 COPD 临床试验", 3, "completed", "trial_landscape"),
            ("manufacturing", "设备交接，全流程", 1, "budget_exhausted", "condition-monitoring"),
            ("energy", "能源全流程", 3, "needs_review", "flexible-load-scheduling"),
        )
        for domain, request, budget, expected, tool in cases:
            page.locator(f'label:has(input[name=domain][value="{domain}"])').click()
            page.locator("#request").fill(request)
            page.locator(f'label:has(input[name=budget][value="{budget}"])').click()
            page.locator("#run").click()
            page.wait_for_function("""() => document.querySelector('#record-mode').dataset.live === 'true'
                && document.querySelector('.request-line')?.textContent.includes(document.querySelector('#request').value)
                || document.querySelector('#feedback').dataset.error === 'true'""", timeout=120000)
            if page.locator("#feedback").get_attribute("data-error") == "true":
                raise AssertionError(page.locator("#feedback").inner_text())
            with page.expect_download() as event:
                page.locator(".download").click()
            report = json.loads(event.value.path().read_text())
            assert report["request"] == request and report["status"] == expected, report["status"]
            assert tool in {record["id"] for record in report["tools"]}
            assert len(report["tools"]) <= budget
            if domain == "pharma":
                assert "NCT00440687" in json.dumps(report["tools"])
            print(domain, report["status"], len(report["tools"]), flush=True)
        catalog = page.request.get(url + "catalog.json").json()["scenarios"]
        assert len(catalog) == 27
        page.set_viewport_size({"width": 375, "height": 900})
        for domain in {item["domain"] for item in catalog}:
            page.locator(f'label:has(input[name=domain][value="{domain}"])').click()
            choices = page.locator("button[data-scenario]")
            assert choices.count() == 9
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            for item in (row for row in catalog if row["domain"] == domain):
                tool_id = item["id"]
                page.locator(f'button[data-scenario="{tool_id}"]').click()
                expect(page.locator('#record-mode[data-live="false"]')).to_have_text("已保存的运行")
                assert page.locator("#request").input_value() == item["prompt"]
                page.locator("#run").click()
                page.locator('#record-mode[data-live="true"]').wait_for()
                with page.expect_download() as event:
                    page.locator(".download").click()
                report = json.loads(event.value.path().read_text())
                assert [tool["id"] for tool in report["tools"]] == [tool_id]
                assert report["status"] in ("completed", "needs_review")
                if tool_id.startswith(domain + "-"):
                    assert report["tools"][0]["output"]["records"]
                    assert report["tools"][0]["data"]["kind"] == "synthetic"
                print(tool_id, report["status"], flush=True)
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    directory = parser.parse_args().directory
    with ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=directory)) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            exercise(f"http://127.0.0.1:{server.server_port}/")
        finally:
            server.shutdown()
