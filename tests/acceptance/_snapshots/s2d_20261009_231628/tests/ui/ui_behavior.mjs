/* Executable JS behaviour checks for the S2-C pages.
   Runs app/static/ui.js inside Node's vm with a minimal DOM + fetch simulation:
   no browser, no network, no new dependencies. Exit code 0 = all checks passed. */
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import vm from "node:vm";

const here = path.dirname(fileURLToPath(import.meta.url));
const UI_SOURCE = readFileSync(path.join(here, "..", "..", "app", "static", "ui.js"), "utf8");
const ARTIFACT_DIR = path.join(here, "_tmp");
const ARTIFACT = path.join(ARTIFACT_DIR, "feedback_payloads.json");

class El {
  constructor(tag, doc) {
    this.tagName = String(tag).toUpperCase();
    this.doc = doc;
    this.children = [];
    this.parent = null;
    this.listeners = {};
    this.attrs = {};
    this.dataset = {};
    this.className = "";
    this.id = "";
    this.hidden = false;
    this.disabled = false;
    this.value = "";
    this.files = [];
    this._text = "";
  }
  get firstChild() { return this.children[0] || null; }
  get textContent() {
    if (this.children.length === 0) { return this._text; }
    return this.children.map((child) => child.textContent).join("");
  }
  set textContent(value) {
    this.children = [];
    this._text = value === null || value === undefined ? "" : String(value);
  }
  appendChild(child) { child.parent = this; this.children.push(child); return child; }
  removeChild(child) {
    const index = this.children.indexOf(child);
    if (index >= 0) { this.children.splice(index, 1); }
    return child;
  }
  addEventListener(type, handler) {
    (this.listeners[type] = this.listeners[type] || []).push(handler);
  }
  dispatch(type) {
    const event = { preventDefault() {}, target: this };
    (this.listeners[type] || []).forEach((handler) => handler(event));
  }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  reset() { this.children.forEach((child) => { if ("value" in child) { child.value = ""; } }); }
  querySelector(selector) { return this.doc.querySelectorWithin(this, selector); }
  querySelectorAll(selector) { return this.doc.querySelectorAllWithin(this, selector); }
  descendants(out = []) {
    this.children.forEach((child) => { out.push(child); child.descendants(out); });
    return out;
  }
}

class Doc {
  constructor() {
    this.byId = new Map();
    this.listeners = {};
    this.body = new El("body", this);
  }
  createElement(tag) { return new El(tag, this); }
  createTextNode(text) { const node = new El("#text", this); node.textContent = text; return node; }
  register(element) { if (element.id) { this.byId.set(element.id, element); } return element; }
  getElementById(id) { return this.byId.get(id) || null; }
  roots() { return [this.body, ...this.byId.values()].filter((el, i, all) => all.indexOf(el) === i && !el.parent); }
  allElements() {
    const out = [];
    this.roots().forEach((root) => { out.push(root); root.descendants(out); });
    return out.filter((el, i, all) => all.indexOf(el) === i);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  querySelectorAll(selector) { return this.allElements().filter((el) => matches(el, selector)); }
  querySelectorWithin(root, selector) { return root.descendants().filter((el) => matches(el, selector))[0] || null; }
  querySelectorAllWithin(root, selector) { return root.descendants().filter((el) => matches(el, selector)); }
  addEventListener(type, handler) { (this.listeners[type] = this.listeners[type] || []).push(handler); }
  dispatch(type) { const event = { preventDefault() {} }; (this.listeners[type] || []).forEach((h) => h(event)); }
  createRange() { return { selectNodeContents() {} }; }
}

function matches(el, selector) {
  if (selector.startsWith("[") && selector.endsWith("]")) {
    const name = selector.slice(1, -1);
    const camel = name.replace(/^data-/, "").replace(/-([a-z])/g, (_m, c) => c.toUpperCase());
    return name.startsWith("data-") ? camel in el.dataset : el.attrs[name] !== undefined;
  }
  if (selector.startsWith(".")) {
    return el.className.split(/\s+/).includes(selector.slice(1));
  }
  const attrMatch = /^([a-zA-Z]+)\[([a-zA-Z-]+)=("?)([^"\]]+)\3\]$/.exec(selector);
  if (attrMatch) {
    return el.tagName === attrMatch[1].toUpperCase() && String(el.attrs[attrMatch[2]]) === attrMatch[4];
  }
  return el.tagName === selector.toUpperCase();
}

function makeEnvironment(pageName) {
  const document = new Doc();
  document.body.dataset.page = pageName;
  const calls = [];
  let responder = async () => ({ ok: true, status: 200, json: async () => ({}) });
  const context = {
    document,
    window: { getSelection: () => ({ removeAllRanges() {}, addRange() {} }) },
    navigator: {},
    FormData: class { constructor() { this.entries = []; } append(k, v) { this.entries.push([k, v]); } },
    URLSearchParams,
    URL,
    console,
    module: { exports: {} },
    fetch: async (url, options) => {
      calls.push({ url: String(url), options: options || {} });
      return responder(String(url), options || {});
    },
  };
  context.globalThis = context;
  const sandbox = vm.createContext(context);
  vm.runInContext(UI_SOURCE, sandbox, { filename: "ui.js" });
  return {
    document,
    calls,
    exports: context.module.exports,
    setResponder(fn) { responder = fn; },
    el(id, props = {}) {
      const element = document.createElement("div");
      element.id = id;
      Object.assign(element, props);
      return document.register(element);
    },
    button(id, parent) {
      const element = document.createElement("button");
      element.id = id;
      element.attrs.type = "submit";
      if (parent) { parent.appendChild(element); } else { document.register(element); }
      return element;
    },
    init() { document.dispatch("DOMContentLoaded"); },
  };
}

const flush = async (times = 8) => {
  for (let i = 0; i < times; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
};
const json = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
const textOf = (element) => (element ? element.textContent : "");
const callsWith = (calls, needle) => calls.filter((call) => call.url.includes(needle));
const bodyOf = (call) => JSON.parse(call.options.body || "{}");

const checks = [];
const check = (name, run) => checks.push({ name, run });

function expect(condition, message) {
  if (!condition) { throw new Error(message); }
}

// ------------------------------------------------------------------ P3 导入
function importPage() {
  const env = makeEnvironment("import");
  const fileInput = env.el("import-file", { value: "", files: [] });
  const formatSelect = env.el("import-format", { value: "" });
  const validateButton = env.button("import-validate");
  const commitButton = env.button("import-commit");
  const hint = env.el("import-hint", { hidden: true });
  env.el("import-loading", { hidden: true });
  env.el("import-error", { hidden: true });
  env.el("import-result", { hidden: true });
  env.el("import-summary");
  env.el("import-rows");
  env.el("import-saved-note", { hidden: true });
  env.el("import-batch");
  env.init();
  return { env, fileInput, formatSelect, validateButton, commitButton, hint };
}

function file(name, size = 10, lastModified = 1) { return { name, size, lastModified }; }

check("import: 未预览时确认按钮禁用且不产生任何 POST", async () => {
  const { env, fileInput, commitButton, hint } = importPage();
  fileInput.files = [file("a.csv")];
  fileInput.dispatch("change");
  expect(commitButton.disabled === true, "确认按钮应初始禁用");
  commitButton.dispatch("click");
  await flush();
  expect(env.calls.length === 0, "未预览就点击确认不得发出请求");
  expect(textOf(hint).includes("预览"), "提示应说明需先预览");
});

check("import: 预览成功后确认可用，更换文件立即失效", async () => {
  const { env, fileInput, commitButton } = importPage();
  env.setResponder(async (url) => {
    if (url.includes("mode=validate")) {
      return json({
        mode: "validate", saved: false, rows_total: 1, counts: { created: 1 },
        project_errors: [],
        rows: [{ row_no: 1, preview_action: "created", errors: [], warnings: [] }],
      });
    }
    return json({ batch_id: "ib_unexpected" }, 201);
  });
  fileInput.files = [file("a.csv")];
  fileInput.dispatch("change");
  env.document.getElementById("import-validate").dispatch("click");
  await flush();
  expect(callsWith(env.calls, "mode=validate").length === 1, "应发出一次预览请求");
  expect(commitButton.disabled === false, "预览成功后确认按钮应可用");
  expect(env.document.getElementById("import-saved-note").hidden === false, "应显示未保存提示");
  expect(textOf(env.document.getElementById("import-rows")).includes("第 1 行"), "预览行应显示行号");
  expect(textOf(env.document.getElementById("import-rows")).includes("created"), "预览应使用 preview_action");

  fileInput.files = [file("b.csv")];
  fileInput.dispatch("change");
  expect(commitButton.disabled === true, "更换文件后确认按钮应失效");
  commitButton.dispatch("click");
  await flush();
  expect(callsWith(env.calls, "mode=atomic").length === 0, "失效的预览不得触发写入");
});

check("import: atomic 422 展示批次与行级原因，并清除旧的未保存提示", async () => {
  const { env, fileInput, commitButton } = importPage();
  env.setResponder(async (url) => {
    if (url.includes("mode=validate")) {
      return json({ mode: "validate", saved: false, rows_total: 1, counts: {}, project_errors: [],
                   rows: [{ row_no: 1, preview_action: "created", errors: [], warnings: [] }] });
    }
    if (url.includes("mode=atomic")) {
      return json({
        batch_id: "ib_422", status: "rejected", mode: "atomic", rows_total: 2, counts: { rejected: 1 },
        rows: [{ row_no: 2, action: "rejected", errors: [{ code: "V22", reason: "负金额" }], warnings: [] }],
      }, 422);
    }
    return json({
      batch: { id: "ib_422", mode: "atomic", status: "rejected", rows_total: 2, created_at: "t" },
      row_results: [{ row_no: 2, action: "rejected", record_type: null, record_id: null,
                      reason_code: "V22", reason_detail: "负金额" }],
    });
  });
  fileInput.files = [file("a.csv")];
  fileInput.dispatch("change");
  env.document.getElementById("import-validate").dispatch("click");
  await flush();
  commitButton.dispatch("click");
  await flush();
  expect(callsWith(env.calls, "mode=atomic").length === 1, "应发出写入请求");
  const rows = textOf(env.document.getElementById("import-rows"));
  expect(rows.includes("第 2 行"), "422 响应应展示行号");
  expect(rows.includes("V22"), "422 响应应展示校验码");
  expect(textOf(env.document.getElementById("import-batch")).includes("ib_422"), "应展示批次 id");
  expect(textOf(env.document.getElementById("import-error")).includes("未写入业务数据"), "应说明 atomic 未写入");
  expect(env.document.getElementById("import-saved-note").hidden === true, "新请求应清除旧的未保存提示");
});

check("import: 预览网络失败撤销 loading、保持确认禁用", async () => {
  const { env, fileInput, commitButton } = importPage();
  env.setResponder(async () => { throw new Error("ECONNREFUSED"); });
  fileInput.files = [file("a.csv")];
  fileInput.dispatch("change");
  env.document.getElementById("import-validate").dispatch("click");
  await flush();
  expect(env.document.getElementById("import-loading").hidden === true, "失败后应撤销 loading");
  expect(textOf(env.document.getElementById("import-error")).includes("网络"), "应显示网络错误");
  expect(commitButton.disabled === true, "预览失败后确认应禁用");
});

// ------------------------------------------------------------------ P1 今日工作台
function homePage(responder) {
  const env = makeEnvironment("home");
  ["q", "status"].forEach((id) => env.el(id, { value: "" }));
  ["pool-list", "sources-list", "runs-list"].forEach((id) => env.el(id));
  ["pool-loading", "sources-loading", "runs-loading",
   "pool-empty", "sources-empty", "runs-empty",
   "pool-error", "sources-error", "runs-error",
   "pool-total", "pool-page"].forEach((id) => env.el(id, { hidden: true }));
  env.el("pool-prev", { disabled: true });
  env.el("pool-next", { disabled: false });
  const form = env.el("pool-filter");
  if (responder) { env.setResponder(responder); }
  env.init();
  return { env, form };
}

check("home: 网络失败撤销 loading 并显示错误", async () => {
  const { env } = homePage(async (url) => {
    if (url.includes("/api/candidates")) { throw new Error("boom"); }
    return json({ items: [] });
  });
  await flush(12);
  expect(env.document.getElementById("pool-loading").hidden === true, "失败后应撤销 loading");
  expect(textOf(env.document.getElementById("pool-error")).includes("网络"), "应显示网络错误文案");
});

check("home: 来源访问条件按 yes/no/unknown 三态显示", async () => {
  const { env } = homePage(async (url) => {
    if (url.includes("/api/candidates")) { return json({ items: [], total: 0, page: 1, page_size: 20 }); }
    if (url.includes("/api/sources")) {
      return json({ items: [
        { name: "甲", channel: "xianyu", access_mode: "manual_import", access_verified: "no" },
        { name: "乙", channel: "xiaohongshu", access_mode: "manual_import", access_verified: "unknown" },
        { name: "丙", channel: "bilibili", access_mode: "manual_import", access_verified: "yes" },
      ] });
    }
    return json({ items: [] });
  });
  await flush(12);
  const rendered = textOf(env.document.getElementById("sources-list"));
  expect(rendered.includes("甲（xianyu）"), "应渲染来源名称");
  expect(rendered.includes("访问条件已核验：否"), "no 应显示为否");
  expect(rendered.includes("访问条件已核验：未知"), "unknown 应显示为未知");
  expect(rendered.includes("访问条件已核验：是"), "yes 应显示为是");
  expect(!rendered.includes("乙（xiaohongshu））访问条件已核验：是"), "unknown 不得显示为是");
});

check("home: 翻页请求 page 参数，筛选变更复位到第 1 页", async () => {
  const items = Array.from({ length: 20 }, (_v, i) => ({ id: "c_" + i, title: "候选" + i, status: "pending",
    status_reason: "缺证据", data_origin: "synthetic", updated_at: "t" }));
  const { env, form } = homePage(async (url) => {
    if (url.includes("/api/candidates")) { return json({ items, total: 45, page: 1, page_size: 20 }); }
    return json({ items: [] });
  });
  await flush(12);
  expect(env.document.getElementById("pool-next").disabled === false, "总数 45 时下一页应可用");
  env.document.getElementById("pool-next").dispatch("click");
  await flush(12);
  expect(callsWith(env.calls, "page=2").length === 1, "点击下一页应请求 page=2");
  env.document.getElementById("status").value = "pending";
  env.document.getElementById("status").dispatch("change");
  await flush(12);
  const last = callsWith(env.calls, "/api/candidates").pop();
  expect(last.url.includes("page=1"), "筛选变更应复位到第 1 页");
  form.dispatch("submit");
  await flush(12);
  expect(callsWith(env.calls, "/api/candidates").pop().url.includes("page=1"), "搜索提交也应复位到第 1 页");
});

// ------------------------------------------------------------------ P2 机会详情
function opportunityPage() {
  const env = makeEnvironment("opportunity");
  const holder = env.el("holder");
  holder.dataset.candidateId = "c_1";
  const draftForm = env.el("draft-form");
  const draftSubmit = env.button("draft-submit", draftForm);
  env.el("draft-kind", { value: "listing_copy" });
  env.el("draft-loading", { hidden: true });
  env.el("draft-error", { hidden: true });
  env.el("draft-output", { hidden: true });
  env.el("draft-body");
  env.el("draft-copy-note", { hidden: true });
  const feedbackForm = env.el("feedback-form");
  const feedbackSubmit = env.button("feedback-submit", feedbackForm);
  env.el("feedback-kind", { value: "sale" });
  env.el("fb-amount", { value: "" });
  env.el("fb-order-ref", { value: "" });
  env.el("fb-related", { value: "" });
  env.el("fb-refund-state", { value: "" });
  env.el("fb-minutes", { value: "" });
  env.el("feedback-loading", { hidden: true });
  env.el("feedback-error", { hidden: true });
  env.el("feedback-ok", { hidden: true });
  // Same structure the server renders for a candidate without feedback: table hidden, tbody present but empty.
  env.el("feedback-table", { hidden: true });
  env.el("feedback-rows");
  env.el("feedback-empty", { hidden: false });
  env.init();
  return { env, draftSubmit, feedbackSubmit };
}

function feedbackRows(env) {
  const tbody = env.document.getElementById("feedback-rows");
  return (tbody ? tbody.children : []).map((tr) => (tr.children[0] ? tr.children[0].textContent : ""));
}

check("feedback: 金额与分钟精确解析，非法输入本地拒绝且不发请求", async () => {
  const { env } = opportunityPage();
  env.setResponder(async () => json({ id: "fb_x", kind: "manual_time" }, 201));
  const form = env.document.getElementById("feedback-form");
  const kind = env.document.getElementById("feedback-kind");
  const minutes = env.document.getElementById("fb-minutes");

  kind.value = "sale";
  kind.dispatch("change");
  env.document.getElementById("fb-amount").value = "12.345";
  form.dispatch("submit");
  await flush();
  expect(env.calls.length === 0, "三位小数不得发出请求");
  expect(textOf(env.document.getElementById("feedback-error")).includes("两位小数"), "应提示两位小数");

  kind.value = "manual_time";
  kind.dispatch("change");
  minutes.value = "1.9";
  form.dispatch("submit");
  await flush();
  expect(env.calls.length === 0, "非整数分钟不得发出请求");
  expect(textOf(env.document.getElementById("feedback-error")).includes("完整整数"), "应提示必须是整数");

  minutes.value = "15";
  form.dispatch("submit");
  await flush(14);
  const manualCall = callsWith(env.calls, "/feedback").pop();
  expect(bodyOf(manualCall).actual_minutes === 15, "分钟应按整数 15 提交");
  expect(bodyOf(manualCall).amount_minor === undefined, "manual_time 不得携带金额字段");
  expect(callsWith(env.calls, "/api/candidates/c_1").length >= 1, "manual_time 成功也刷新同一反馈区");
});

check("feedback: 成交按分提交，成功后就地刷新可关联成交列表与空态撤销", async () => {
  const { env } = opportunityPage();
  let written = false;
  env.setResponder(async (url) => {
    if (url.includes("/feedback")) {
      written = true;
      return json({ id: "fb_1", kind: "sale", predicted_net_per_order_minor: null }, 201);
    }
    if (url.includes("/api/candidates/c_1")) {
      // Real timing: nothing before the sale, then exactly the sale row.
      return json({ feedback: written ? [{ id: "fb_1", kind: "sale", order_ref: null, amount_minor: 990,
        occurred_at: "t", predicted_net_per_order_minor: null, refund_state: null,
        actual_net_per_order_minor: null }] : [] });
    }
    return json({});
  });
  const kind = env.document.getElementById("feedback-kind");
  kind.value = "sale";
  kind.dispatch("change");

  // 初始 0 行：空态可见、表格隐藏
  expect(feedbackRows(env).length === 0, "初始不应有反馈行");
  expect(env.document.getElementById("feedback-empty").hidden === false, "初始空态应可见");
  expect(env.document.getElementById("feedback-table").hidden === true, "初始表格应隐藏");

  env.document.getElementById("fb-amount").value = "9.90";
  env.document.getElementById("feedback-form").dispatch("submit");
  await flush(14);
  const posted = callsWith(env.calls, "/feedback")[0];
  expect(bodyOf(posted).amount_minor === 990, "9.90 应提交为 990 分");
  expect(bodyOf(posted).actual_minutes === undefined, "sale 不得携带分钟字段");
  const select = env.document.getElementById("fb-related");
  const values = select.children.map((option) => option.value);
  expect(values.includes("fb_1"), "新成交应出现在关联成交列表中");
  expect(textOf(env.document.getElementById("feedback-ok")).includes("未知"), "预测快照为空应按未知展示");
  expect(JSON.stringify(feedbackRows(env)) === JSON.stringify(["sale"]), "sale 后应只有一条 sale 行");
  expect(env.document.getElementById("feedback-empty").hidden === true, "sale 后空态应撤销");
  expect(env.document.getElementById("feedback-table").hidden === false, "sale 后表格应可见");
});

check("draft: 提交期间禁用按钮，完成后恢复并渲染正文", async () => {
  const { env, draftSubmit } = opportunityPage();
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  env.setResponder(async () => {
    await gate;
    return json({ id: "d_1", kind: "listing_copy", method: "template", status: "draft",
                  template_version: "v1", body: "正文【待核验：平台发布条件】" }, 201);
  });
  const form = env.document.getElementById("draft-form");
  form.dispatch("submit");
  await flush(2);
  expect(draftSubmit.disabled === true, "提交中应禁用按钮");
  release();
  await flush(12);
  expect(draftSubmit.disabled === false, "完成后应恢复按钮");
  expect(textOf(env.document.getElementById("draft-body")).includes("【待核验"), "应渲染草稿正文");
  expect(env.document.getElementById("draft-loading").hidden === true, "完成后应撤销 loading");
});

// ------------------------------------------------------------------ 纯函数边界
check("parseYuan/parseMinutes/triState 边界", async () => {
  const { env } = importPage();
  const api = env.exports;
  expect(api.parseYuan("9.90").minor === 990, "9.90 → 990 分");
  expect(api.parseYuan("0.5").minor === 50, "0.5 → 50 分");
  expect(api.parseYuan("12.345").ok === false, "三位小数应拒绝");
  expect(api.parseYuan("1e2").ok === false, "科学计数法应拒绝");
  expect(api.parseYuan("-9.90").ok === false, "负数应拒绝");
  expect(api.parseYuan("90071992547409.91").minor === 9007199254740991, "最大可精确整数分应接受");
  expect(api.parseYuan("90071992547410.00").ok === false, "超出可精确表示应拒绝");
  expect(api.parseYuan("99999999999999999999").ok === false, "超长整数应拒绝");
  expect(api.parseMinutes("1.9").ok === false, "1.9 应拒绝");
  expect(api.parseMinutes("15").minutes === 15, "15 → 15");
  expect(api.parseMinutes("1441").ok === false, "1441 超界应拒绝");
  expect(api.triState("no") === "否" && api.triState("unknown") === "未知" && api.triState("yes") === "是",
    "三态映射应为 是/否/未知");
});

check("import: 预览请求进行中更换文件，旧响应不得授权（generation 守卫）", async () => {
  const { env, fileInput, commitButton } = importPage();
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  env.setResponder(async () => {
    await gate;
    return json({ mode: "validate", saved: false, rows_total: 1, counts: { created: 1 }, project_errors: [],
                 rows: [{ row_no: 1, preview_action: "created", errors: [], warnings: [] }] });
  });
  fileInput.files = [file("a.csv")];
  fileInput.dispatch("change");
  env.document.getElementById("import-validate").dispatch("click");
  await flush(2);
  fileInput.files = [file("b.csv")];
  fileInput.dispatch("change");
  release();
  await flush(12);
  expect(commitButton.disabled === true, "A 的响应到达后确认仍应禁用");
  expect(env.document.getElementById("import-saved-note").hidden === true, "不得显示预览已通过");
  commitButton.dispatch("click");
  await flush(6);
  expect(callsWith(env.calls, "mode=atomic").length === 0, "确认不得触发写入");
});

check("import: 200 + saved=false 但含 rejected 行 → 不视为预览通过", async () => {
  const { env, fileInput, commitButton } = importPage();
  env.setResponder(async () => json({
    mode: "validate", saved: false, rows_total: 2, counts: { created: 1, rejected: 1 }, project_errors: [],
    rows: [
      { row_no: 1, preview_action: "created", errors: [], warnings: [] },
      { row_no: 2, preview_action: "rejected", errors: [{ code: "V22", reason: "负金额" }], warnings: [] },
    ],
  }));
  fileInput.files = [file("a.csv")];
  fileInput.dispatch("change");
  env.document.getElementById("import-validate").dispatch("click");
  await flush(12);
  expect(commitButton.disabled === true, "行级错误时确认必须禁用");
  expect(env.document.getElementById("import-saved-note").hidden === true, "不得显示未保存即为通过");
  expect(textOf(env.document.getElementById("import-error")).includes("预览未通过"), "应提示预览未通过");
  commitButton.dispatch("click");
  await flush(6);
  expect(callsWith(env.calls, "mode=atomic").length === 0, "行级错误时不得写入");
});

check("200 非 JSON：home／草稿／导入 都显示可见错误并撤 loading", async () => {
  const broken = async () => ({ ok: true, status: 200, json: async () => { throw new Error("not json"); } });

  const home = homePage(broken);
  await flush(12);
  expect(home.env.document.getElementById("pool-loading").hidden === true, "home 应撤 loading");
  expect(textOf(home.env.document.getElementById("pool-error")).includes("非 JSON"), "home 应显示非 JSON 错误");

  const opp = opportunityPage();
  opp.env.setResponder(broken);
  opp.env.document.getElementById("draft-form").dispatch("submit");
  await flush(12);
  expect(textOf(opp.env.document.getElementById("draft-error")).includes("非 JSON"), "草稿应显示非 JSON 错误");
  expect(opp.env.document.getElementById("draft-loading").hidden === true, "草稿应撤 loading");

  const imp = importPage();
  imp.env.setResponder(broken);
  imp.fileInput.files = [file("a.csv")];
  imp.fileInput.dispatch("change");
  imp.env.document.getElementById("import-validate").dispatch("click");
  await flush(12);
  expect(textOf(imp.env.document.getElementById("import-error")).includes("非 JSON"), "导入应显示非 JSON 错误");
  expect(imp.env.document.getElementById("import-loading").hidden === true, "导入应撤 loading");
});

check("feedback: 退款必须带金额；行数按时序 0→1(sale)→2(sale+refund)", async () => {
  const { env } = opportunityPage();
  const saleRow = { id: "fb_1", kind: "sale", order_ref: "ORD-1", amount_minor: 990, occurred_at: "t",
    predicted_net_per_order_minor: null, refund_state: null, actual_net_per_order_minor: null };
  const refundRow = { id: "fb_2", kind: "refund", order_ref: "ORD-1", amount_minor: 990, occurred_at: "t2",
    predicted_net_per_order_minor: null, refund_state: "settled", actual_net_per_order_minor: null };
  let phase = 0;   // 0 = 无记录；1 = 仅 sale；2 = sale + refund（退款成功后才出现）
  env.setResponder(async (url) => {
    if (url.includes("/feedback")) {
      phase += 1;
      return json(phase === 1
        ? { id: "fb_1", kind: "sale", predicted_net_per_order_minor: null }
        : { id: "fb_2", kind: "refund", predicted_net_per_order_minor: null }, 201);
    }
    if (url.includes("/api/candidates/c_1")) {
      return json({ feedback: phase === 0 ? [] : (phase === 1 ? [saleRow] : [saleRow, refundRow]) });
    }
    return json({});
  });
  const form = env.document.getElementById("feedback-form");
  const kind = env.document.getElementById("feedback-kind");
  const amountField = env.document.getElementById("fb-amount");

  expect(feedbackRows(env).length === 0, "初始不应有反馈行");
  expect(env.document.getElementById("feedback-empty").hidden === false, "初始空态应可见");

  kind.value = "sale";
  kind.dispatch("change");
  amountField.value = "9.90";
  form.dispatch("submit");
  await flush(14);
  const salePayload = bodyOf(callsWith(env.calls, "/feedback")[0]);
  expect(salePayload.amount_minor === 990, "成交应按分提交");
  expect(salePayload.actual_minutes === undefined, "成交不得携带人工分钟");
  expect(JSON.stringify(feedbackRows(env)) === JSON.stringify(["sale"]), "sale 后只有 sale 行，退款不得预填");
  expect(env.document.getElementById("feedback-empty").hidden === true, "sale 后空态应撤销");

  const before = callsWith(env.calls, "/feedback").length;
  kind.value = "refund";
  kind.dispatch("change");
  env.document.getElementById("fb-related").value = "fb_1";
  env.document.getElementById("fb-refund-state").value = "settled";
  amountField.value = "";
  form.dispatch("submit");
  await flush();
  expect(callsWith(env.calls, "/feedback").length === before, "退款缺金额不得发出请求");
  expect(textOf(env.document.getElementById("feedback-error")).includes("amount_minor"), "应显示 amount_minor 字段错误");
  expect(amountField.disabled === false, "退款必须启用金额字段");

  amountField.value = "9.90";
  form.dispatch("submit");
  await flush(14);
  const refundCall = callsWith(env.calls, "/feedback")[1];
  const refundPayload = bodyOf(refundCall);
  expect(refundPayload.amount_minor === 990, "退款必须携带 amount_minor");
  expect(refundPayload.related_feedback_id === "fb_1", "退款必须关联成交");
  expect(refundPayload.refund_state === "settled", "退款必须携带状态");
  expect(JSON.stringify(feedbackRows(env)) === JSON.stringify(["sale", "refund"]),
    "退款成功后才出现第二条 refund 行");

  const refreshes = callsWith(env.calls, "/api/candidates/c_1");
  expect(refreshes.length >= 2, "成交与退款后都应刷新反馈数据");
  expect(env.calls.indexOf(refreshes[refreshes.length - 1]) > env.calls.indexOf(refundCall),
    "退款成功后的刷新应发生在退款请求之后");

  kind.value = "manual_time";
  kind.dispatch("change");
  expect(amountField.disabled === true, "manual_time 应禁用金额");
  expect(amountField.value === "", "manual_time 应清空金额");

  const refreshesBefore = callsWith(env.calls, "/api/candidates/c_1").length;
  const freshOpp = opportunityPage();   // 独立实例：验证 manual_time 成功也刷新同一反馈区
  freshOpp.env.setResponder(async (url) => {
    if (url.includes("/feedback")) { return json({ id: "fb_time", kind: "manual_time", predicted_net_per_order_minor: null }, 201); }
    if (url.includes("/api/candidates/c_1")) {
      return json({ feedback: [{ id: "fb_1", kind: "sale", order_ref: "ORD-1", amount_minor: 990,
        occurred_at: "t", predicted_net_per_order_minor: 150, refund_state: null,
        actual_net_per_order_minor: null }] });
    }
    return json({});
  });
  const freshKind = freshOpp.env.document.getElementById("feedback-kind");
  freshKind.value = "manual_time";
  freshKind.dispatch("change");
  freshOpp.env.document.getElementById("fb-minutes").value = "15";
  freshOpp.env.document.getElementById("feedback-form").dispatch("submit");
  await flush(14);
  expect(callsWith(freshOpp.env.calls, "/api/candidates/c_1").length >= 1,
    "manual_time 成功也应刷新同一反馈区");
  const predictedCell = freshOpp.env.document.getElementById("feedback-rows").children[0].children[4].textContent;
  expect(predictedCell === "¥1.50", "刷新后预测快照应保留（服务端快照值，不被清空）");
  expect(refreshesBefore === callsWith(env.calls, "/api/candidates/c_1").length, "两个实例互不干扰");

  mkdirSync(ARTIFACT_DIR, { recursive: true });
  writeFileSync(ARTIFACT, JSON.stringify({
    sale: { keys: Object.keys(salePayload).sort(), payload: salePayload },
    refund: { keys: Object.keys(refundPayload).sort(), payload: refundPayload },
  }, null, 2));
});

let failed = 0;
for (const item of checks) {
  try {
    await item.run();
    console.log("PASS " + item.name);
  } catch (err) {
    failed += 1;
    console.log("FAIL " + item.name + " :: " + (err && err.message ? err.message : err));
  }
}
console.log(`${checks.length - failed} passed / ${failed} failed`);
process.exitCode = failed === 0 ? 0 : 1;
