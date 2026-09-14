/* eslint-env node */
// Run against an isolated API database, never a production API.
const { chromium, request } = require("playwright");
const assert = require("node:assert/strict");

(async () => {
  const apiURL = process.env.TEST_API_URL || "http://127.0.0.1:18001";
  const webURL = process.env.TEST_WEB_URL || "http://localhost:8080";
  const api = await request.newContext({ baseURL: apiURL, extraHTTPHeaders: { "X-User-Role": "procurement_manager", "X-User-Id": "ui-cost-test" } });
  async function post(path, data) {
    const response = await api.post(`/api/v1${path}`, { data });
    assert(response.ok(), `${path}: ${await response.text()}`);
    return response.status() === 204 ? null : response.json();
  }
  const code = `UI-${Date.now()}`;
  const order = await post("/orders", { supplier_id: "UI-SUP", supplier_name: "浏览器验收供应商", factory_code: "UI-F", lines: [{ material_code: code, material_name: "验收轴", unit: "件", quantity: 10, unit_price: 10, tax_rate: 0 }] });
  const receipt = await post("/receipts", { order_id: order.id, material_code: code, material_name: "验收轴", received_quantity: 10 });
  await post(`/receipts/${receipt.id}/confirm`);
  await post("/inspections", { receipt_id: receipt.id, inspected_quantity: 10, accepted_quantity: 8, rejected_quantity: 2 });
  await post("/quotations", { supplier_id: "UI-SUP", supplier_name: "浏览器验收供应商", lines: [{ material_code: code, material_name: "验收轴", unit: "件", quantity: 10, unit_price: 10, tax_rate: 0 }] });
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    await page.route("**/api/v1/**", async route => {
      const url = new URL(route.request().url());
      const response = await route.fetch({ url: `${apiURL}${url.pathname}${url.search}` });
      await route.fulfill({ response });
    });
    await page.goto(`${webURL}/material-costs`, { waitUntil: "networkidle" });
    assert(page.url().endsWith("/rfqs"), "legacy costs URL should redirect to RFQs");
    await page.goto(`${webURL}/materials`, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "导入非标制造分类" }).click();
    await page.getByRole("button", { name: "确认导入", exact: true }).click();
    await page.locator(".el-dialog:visible").waitFor({ state: "hidden" });
    await page.waitForSelector(".el-table__expand-icon");
    await page.waitForFunction(() => document.body.innerText.includes("NS-01-01"));
    assert((await page.locator(".el-table__expand-icon").count()) > 0, "category tree has no expand controls");
    await page.getByRole("button", { name: "新增物料分类", exact: true }).click();
    const categoryDialog = page.locator(".el-dialog:visible");
    const segment = `X${Date.now().toString().slice(-6)}`;
    await categoryDialog.getByPlaceholder("可选：1-8位字母或数字；留空自动编号").fill(segment);
    await categoryDialog.locator(".el-form-item").filter({ hasText: "分类名称" }).locator("input").fill("浏览器自定义分类");
    await categoryDialog.getByRole("button", { name: "保存", exact: true }).click();
    await page.waitForFunction(code => document.body.innerText.includes(code), segment);
    await page.getByRole("tab", { name: "物料档案", exact: true }).click();
    await page.getByRole("button", { name: "新增物料", exact: true }).click();
    const materialDialog = page.locator(".el-dialog:visible");
    await materialDialog.locator(".el-cascader input").click();
    await page.getByText("NS 非标制造", { exact: true }).click();
    await page.getByText("NS-01 机械加工件", { exact: true }).click();
    await page.getByText("NS-01-01 车削件", { exact: true }).click();
    await page.waitForFunction(() => [...document.querySelectorAll(".el-dialog input")].some(input => input.value.startsWith("NS-01-01-000")));
    await materialDialog.locator(".el-form-item").filter({ hasText: "物料名称" }).locator("input").fill("分类自动编号验收物料");
    await materialDialog.getByRole("button", { name: "保存", exact: true }).click();
    await page.waitForFunction(() => document.body.innerText.includes("分类自动编号验收物料") && !document.querySelector(".el-dialog__wrapper:not([style*='display: none'])"));
    await page.screenshot({ path: "/tmp/pebs-material-tree.png", fullPage: true });
    assert.deepEqual(errors, []);
    console.log("PASS: legacy costs redirect, industry import, tree expansion, custom code, category cascader and material creation; no browser errors");
  } finally {
    await browser.close();
    await api.dispose();
  }
})().catch(error => { console.error(error); process.exit(1); });
