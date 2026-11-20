"""Exercise the studio UI and Python worker in headless Chromium."""
import argparse
import csv
import io
import json
import shutil
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import expect, sync_playwright


def exercise_ui(page):
    search = page.get_by_role("searchbox", name="场景库")
    expect(page.locator("button[data-scenario]")).to_have_count(9)
    expect(page.locator("button[data-quick-scenario]")).to_have_count(3)
    search.fill("trial_landscape")
    expect(page.locator("button[data-scenario]")).to_have_count(1)
    search.fill("no-match-987")
    expect(page.get_by_text("没有匹配的场景。")).to_be_visible()
    search.fill("")

    card = page.locator('button[data-quick-scenario="trial_landscape"]')
    card.click()
    expect(card).to_have_attribute("aria-pressed", "true")
    expect(page.locator('button[data-scenario="trial_landscape"]')).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_role("tab", name="概览")).to_have_attribute("aria-selected", "true")
    page.get_by_role("tab", name="数据依据").click()
    expect(page.get_by_role("tabpanel", name="数据依据").get_by_text("数据来源", exact=True)).to_be_visible()
    page.keyboard.press("ArrowRight")
    expect(page.get_by_role("tab", name="执行轨迹")).to_be_focused()
    expect(page.get_by_role("tabpanel", name="执行轨迹").locator(".steps li").first).to_be_visible()
    page.keyboard.press("Home")
    expect(page.get_by_role("tab", name="概览")).to_be_focused()
    page.locator("#load-example").click()
    expect(page.locator("#record-title")).to_be_focused()

    menu = page.locator("#menu-toggle")
    for width in (801, 800, 375):
        page.set_viewport_size({"width": width, "height": 900})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        if width == 801:
            expect(menu).to_be_hidden()
            expect(search).to_be_visible()
        else:
            menu.click()
            expect(menu).to_have_attribute("aria-expanded", "true")
            expect(page.locator("#drawer-close")).to_be_focused()
            expect(search).to_be_visible()
            page.keyboard.press("Escape")
            expect(menu).to_have_attribute("aria-expanded", "false")
            expect(menu).to_be_focused()
    page.set_viewport_size({"width": 1280, "height": 900})


def exercise_catalog(page, url):
    expect(page.locator("#scenario-count")).to_have_text("27")
    expect(page.locator(".atlas-choice")).to_have_count(27)
    expect(page.locator("#featured-case-list button")).to_have_count(3)
    expect(page.locator("#casebook-grid .case-card")).to_have_count(3)
    case = page.locator('#featured-case-list button[data-featured-scenario="inspection-queue"]')
    case.click()
    expect(page.locator("#breadcrumb-domain")).to_have_text("制造运营")
    expect(page.locator("#record-title")).to_be_focused()
    link = page.get_by_role("link", name="场景永久链接")
    expect(link).to_have_attribute("href", url + "?scenario=inspection-queue#record-title")
    page.goto(link.get_attribute("href"))
    expect(page.locator("#breadcrumb-domain")).to_have_text("制造运营")
    expect(page.locator('button[data-scenario="inspection-queue"]')).to_have_attribute("aria-pressed", "true")

    energy = page.locator('#explore-grid article[data-domain="energy"]')
    phase = energy.locator("details").filter(has_text="服务与结算")
    phase.locator("summary").click()
    phase.locator('button[data-atlas-scenario="energy-bill-audit"]').click()
    expect(page.locator("#console-domain")).to_have_text("能源运营")
    expect(page.get_by_role("link", name="场景永久链接")).to_have_attribute(
        "href", url + "?scenario=energy-bill-audit#record-title"
    )
    page.goto(url)
    expect(page.locator("#breadcrumb-domain")).to_have_text("制药临床")


def exercise_run_tools(page):
    page.locator('label:has(input[name=domain][value="manufacturing"])').click()
    task = "设备运维交接"
    page.locator("#request").fill(task)
    page.locator("#compare-budget").click()
    comparison = page.locator("#budget-comparison")
    expect(comparison).to_be_visible(timeout=120000)
    cards = comparison.locator(".comparison-card")
    expect(cards.first.locator("li")).to_have_count(1)
    expect(cards.last.locator("li")).to_have_count(3)
    expect(cards.last.locator("li strong")).to_have_count(2)
    cards.first.get_by_role("button", name="查看完整结果").click()
    with page.expect_download() as event:
        page.locator(".download").click()
    report = event.value.path().read_bytes()
    assert json.loads(report)["max_tools"] == 1

    history = page.locator("#run-history")
    rows = history.locator(".history-entry")
    expect(rows).to_have_count(2)
    page.reload()
    expect(rows).to_have_count(2)
    rows.last.locator(".history-open").click()
    expect(page.locator("#request")).to_have_value(task)
    expect(page.locator('input[name=budget][value="1"]')).to_be_checked()
    rows.last.locator(".history-delete").click()
    expect(rows).to_have_count(1)
    upload = history.locator("input[type=file]")
    upload.set_input_files({"name": "invalid.json", "mimeType": "application/json", "buffer": b'{}'})
    expect(history.locator(".history-message")).to_have_attribute("data-error", "true")
    upload.set_input_files({"name": "run.json", "mimeType": "application/json", "buffer": report})
    expect(page.locator("#record-mode")).to_have_text("导入的运行")
    expect(rows).to_have_count(1)
    page.get_by_role("button", name="存入历史").click()
    expect(rows).to_have_count(2)


def exercise_result_workspaces(page, url):
    page.goto(url + "?scenario=inspection-queue#record-title")
    expect(page.locator("#record-mode")).to_have_text("已保存的运行")
    table = page.locator(".result-table")
    table.get_by_role("searchbox").fill("no-matching-record")
    expect(table.locator(".result-table-empty")).to_be_visible()
    table.get_by_role("button", name="重置视图").click()
    with page.expect_download() as event:
        table.get_by_role("button", name="导出 CSV").click()
    records = list(csv.reader(io.StringIO(event.value.path().read_text(encoding="utf-8-sig"))))
    assert len(records) == 41

    review = page.locator(".result-review")
    review.get_by_role("checkbox").first.check()
    review.locator(".result-review-notes").fill("Seen on the validation shift")
    with page.expect_download() as event:
        review.locator(".result-review-export").click()
    review_package = event.value.path().read_bytes()
    assert json.loads(review_package)["report"]["tools"][0]["id"] == "inspection-queue"
    page.reload()
    expect(review.get_by_role("checkbox").first).to_be_checked()
    expect(review.locator(".result-review-notes")).to_have_value("Seen on the validation shift")
    review.get_by_role("checkbox").first.uncheck()
    file_input = review.locator(".result-review-file")
    file_input.set_input_files({"name": "review.json", "mimeType": "application/json", "buffer": review_package})
    expect(review.get_by_role("checkbox").first).to_be_checked()

    slider = page.locator("#inspection-slots")
    slider.press("End")
    page.get_by_role("button", name="打开本档报告").click()
    expect(page.locator("#record-mode")).to_have_text("容量推演 · 样本回放")
    with page.expect_download() as event:
        page.locator(".download").click()
    capacity = json.loads(event.value.path().read_text(encoding="utf-8"))
    assert capacity["tools"][0]["output"]["slots_per_batch"] == 8
    assert capacity["tools"][0]["metrics"]["records_reviewed"] == 320

    batch = page.locator("#batch-workspace")
    batch.locator('[data-batch="mode"]').select_option("replay")
    batch.locator('[data-batch="examples"]').click()
    batch.locator('[data-batch="start"]').click()
    done = batch.locator('.batch-state[data-state="completed"], .batch-state[data-state="needs_review"]')
    expect(done).to_have_count(3)
    page.reload()
    expect(done).to_have_count(3)
    with page.expect_download() as event:
        batch.locator('[data-batch="export"]').click()
    data = list(csv.reader(io.StringIO(event.value.path().read_text(encoding="utf-8-sig"))))
    assert len(data) == 4
    page.goto(url)


def exercise_live_capacity(page):
    page.locator("#inspection-slots").press("End")
    page.get_by_role("button", name="转到实时任务").click()
    expect(page.locator("#inspection-setting")).to_contain_text("每批 8 个巡检名额")
    expect(page.locator('input[name="budget"][value="1"]')).to_be_checked()
    page.locator("#run").click()
    expect(page.locator("#record-mode")).to_have_attribute("data-live", "true", timeout=120000)
    with page.expect_download() as event:
        page.locator(".download").click()
    report = json.loads(event.value.path().read_text(encoding="utf-8"))
    assert report["data"]["inspection_capacity"]["slots_per_batch"] == 8
    assert report["tools"][0]["metrics"]["records_reviewed"] == 320
    page.locator("#request").fill("设备运维交接")
    expect(page.locator("#inspection-setting")).to_be_hidden()


def exercise_slow_deep_link(browser, url):
    page = browser.new_page()
    page.add_init_script("""{
        const fetchOriginal = window.fetch.bind(window);
        window.fetch = (resource, options) => resource === "./catalog.json"
            ? new Promise(resolve => {
                window.releaseStudioCatalog = () => resolve(fetchOriginal(resource, options));
            })
            : fetchOriginal(resource, options);
    }""")
    try:
        page.goto(url + "?scenario=inspection-queue#record-title")
        page.wait_for_function("typeof window.releaseStudioCatalog === 'function'")
        task = "检索 COPD 临床试验"
        # Use a different request even after the built-in example has loaded.
        task += "，仅查看历史记录"
        page.locator("#request").fill(task)
        page.evaluate("window.releaseStudioCatalog()")
        expect(page.locator('#featured-case-list button')).to_have_count(3)
        expect(page.locator("#request")).to_have_value(task)
        expect(page.locator("#breadcrumb-domain")).to_have_text("制药临床")
    finally:
        page.close()


def exercise(url, ui_only=False):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which("google-chrome"), headless=True)
        page = browser.new_page(accept_downloads=True)
        page.goto(url)
        page.locator('#record-mode[data-live="false"]').wait_for()
        exercise_catalog(page, url)
        exercise_ui(page)
        exercise_result_workspaces(page, url)
        exercise_slow_deep_link(browser, url)
        if ui_only:
            return
        exercise_run_tools(page)
        exercise_live_capacity(page)
        cases = (
            ("pharma", "检索 COPD 临床试验", 3, "completed", "trial_landscape"),
            ("manufacturing", "设备交接，全流程", 1, "budget_exhausted", "condition-monitoring"),
            ("energy", "能源全流程", 3, "needs_review", "flexible-load-scheduling"),
        )
        for domain, request, budget, expected, tool in cases:
            page.locator(f'label:has(input[name=domain][value="{domain}"])').click()
            page.locator("#request").fill(request)
            page.locator(f'label:has(input[name=budget][value="{budget}"])').click()
            if domain == "pharma":
                page.locator("#request").press("Control+Enter")
            else:
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
                page.get_by_role("link", name="查看结果").click()
                expect(page.locator("#record-title")).to_be_focused()
            print(domain, report["status"], len(report["tools"]), flush=True)
        catalog = page.request.get(url + "catalog.json").json()["scenarios"]
        assert len(catalog) == 27
        page.set_viewport_size({"width": 375, "height": 900})
        menu = page.locator("#menu-toggle")
        for domain in sorted({item["domain"] for item in catalog}):
            menu.click()
            page.locator(f'label:has(input[name=domain][value="{domain}"])').click()
            expect(page.locator("button[data-scenario]")).to_have_count(9)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.locator("#drawer-close").click()
            for item in (row for row in catalog if row["domain"] == domain):
                tool_id = item["id"]
                menu.click()
                page.locator(f'button[data-scenario="{tool_id}"]').click()
                expect(menu).to_have_attribute("aria-expanded", "false")
                expect(page.locator("#request")).to_be_focused()
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
    parser.add_argument("--ui-only", action="store_true", help="Check navigation and saved reports without the runtime archive")
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=args.directory)) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            exercise(f"http://127.0.0.1:{server.server_port}/", ui_only=args.ui_only)
        finally:
            server.shutdown()
