/* Minimal local UI logic (no frameworks, no external CDN).
   Rule: API/user data is inserted only with createElement + textContent — never as HTML strings. */
"use strict";

(function () {
  const POOL_LABELS = {
    testable: "可测试池",
    explore: "探索池（弱证据高潜力）",
    pending: "待核验",
    stale: "已失效",
    archived: "已归档",
  };
  const ORIGIN_LABELS = { real: "真实市场数据", synthetic: "合成测试数据" };
  const PAGE_SIZE = 20;
  const AMOUNT_RE = /^(0|[1-9][0-9]*)(\.[0-9]{1,2})?$/;
  const MINUTES_RE = /^[0-9]+$/;

  const qs = (id) => document.getElementById(id);
  const show = (el) => { if (el) { el.hidden = false; } };
  const hide = (el) => { if (el) { el.hidden = true; } };
  const clear = (el) => { while (el && el.firstChild) { el.removeChild(el.firstChild); } };
  const text = (el, value) => {
    if (el) { el.textContent = value === null || value === undefined ? "" : String(value); }
  };
  const trimmed = (el) => ((el && el.value) || "").trim();
  const setEnabled = (el, enabled) => { if (el) { el.disabled = !enabled; } };

  function triState(value) {
    if (value === true || value === "yes") { return "是"; }
    if (value === false || value === "no") { return "否"; }
    if (value === "unknown") { return "未知"; }
    if (value === null || value === undefined || value === "") { return "未知"; }
    return String(value);
  }

  function formatMoney(minor) {
    if (minor === null || minor === undefined) { return "未知"; }
    return "¥" + (minor / 100).toFixed(2);
  }

  /* Amount input is parsed as a decimal string: no Number() rounding, no silent value changes. */
  function parseYuan(raw) {
    const value = (raw || "").trim();
    if (!value) { return { ok: true, minor: undefined }; }
    if (!AMOUNT_RE.test(value)) {
      return { ok: false, reason: "金额需为最多两位小数的非负数（不接受负数、1e2、12.345）" };
    }
    const parts = value.split(".");
    const whole = parts[0];
    const frac = (parts[1] || "").padEnd(2, "0");
    const minor = Number(whole) * 100 + Number(frac);
    if (!Number.isSafeInteger(minor) || minor < 0) {
      return { ok: false, reason: "金额超出可精确表示的范围（最大 9007199254740991 分），请改填更小金额" };
    }
    return { ok: true, minor: minor };
  }

  /* Minutes must be a whole number: 1.9 is rejected, never truncated to 1. */
  function parseMinutes(raw) {
    const value = (raw || "").trim();
    if (!value) { return { ok: true, minutes: undefined }; }
    if (!MINUTES_RE.test(value)) {
      return { ok: false, reason: "人工分钟必须是完整整数（1.9 不接受、不会取整）" };
    }
    const minutes = Number(value);
    if (minutes > 1440) { return { ok: false, reason: "人工分钟需在 0..1440 之间" }; }
    return { ok: true, minutes: minutes };
  }

  async function requestJSON(url, options) {
    let resp;
    try {
      resp = await fetch(url, Object.assign({ headers: { Accept: "application/json" } }, options || {}));
    } catch (err) {
      return { ok: false, status: 0, body: null, networkError: true, parseFailed: false,
               message: "网络或服务不可用：" + ((err && err.message) || err) };
    }
    let body = null;
    let parseFailed = false;
    try { body = await resp.json(); } catch (err) { parseFailed = true; }
    if (body === null || typeof body !== "object") { parseFailed = true; body = null; }
    // HTTP 200 with a non-JSON / non-object body is a failure for callers, not a success branch.
    return { ok: resp.ok && !parseFailed, status: resp.status, body: body, networkError: false,
             parseFailed: parseFailed, message: "" };
  }

  function errorText(result) {
    if (result.networkError) { return result.message || "网络或服务不可用。"; }
    if (result.parseFailed) { return "服务返回了非 JSON 响应（HTTP " + result.status + "）。"; }
    const body = result.body;
    if (body && body.error) {
      const details = (body.error.details || [])
        .map((d) => [d.field, d.reason].filter(Boolean).join("："))
        .filter(Boolean)
        .join("；");
      return body.error.message + (details ? "（" + details + "）" : "");
    }
    return "请求失败：HTTP " + result.status;
  }

  function badge(className, label) {
    const span = document.createElement("span");
    span.className = "badge " + className;
    span.textContent = label;
    return span;
  }
  function li(className) {
    const node = document.createElement("li");
    if (className) { node.className = className; }
    return node;
  }
  function paragraph(value, className) {
    const node = document.createElement("p");
    if (className) { node.className = className; }
    node.textContent = value;
    return node;
  }
  function definition(term, value) {
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = value;
    return [dt, dd];
  }
  function fillSelect(select, options) {
    clear(select);
    options.forEach((entry) => {
      const option = document.createElement("option");
      option.value = entry.value;
      option.textContent = entry.label;
      select.appendChild(option);
    });
  }

  /* No handler may leak an unhandled rejection: failures are reported instead of breaking the page. */
  function safe(handler) {
    return function (event) {
      try {
        const outcome = handler(event);
        if (outcome && typeof outcome.catch === "function") {
          outcome.catch((err) => { console.error("UI 处理失败：", err); });
        }
      } catch (err) {
        console.error("UI 处理失败：", err);
      }
    };
  }

  // ---------------------------------------------------------------- P1 今日工作台
  function initHome() {
    const form = qs("pool-filter");
    if (!form) { return; }
    const state = { page: 1, total: 0 };
    loadPool();
    loadSources();
    loadRuns();
    form.addEventListener("submit", safe((event) => { event.preventDefault(); state.page = 1; return loadPool(); }));
    qs("status").addEventListener("change", safe(() => { state.page = 1; return loadPool(); }));
    qs("pool-prev").addEventListener("click", safe(() => {
      if (state.page > 1) { state.page -= 1; return loadPool(); }
      return undefined;
    }));
    qs("pool-next").addEventListener("click", safe(() => {
      if (state.page * PAGE_SIZE < state.total) { state.page += 1; return loadPool(); }
      return undefined;
    }));

    function setPager() {
      qs("pool-prev").disabled = state.page <= 1;
      qs("pool-next").disabled = state.page * PAGE_SIZE >= state.total;
      text(qs("pool-page"), "第 " + state.page + " 页｜共 " + state.total + " 条");
    }

    async function loadPool() {
      const list = qs("pool-list");
      hide(qs("pool-empty")); hide(qs("pool-error"));
      clear(list);
      show(qs("pool-loading"));
      try {
        const params = new URLSearchParams({ page: String(state.page), page_size: String(PAGE_SIZE) });
        const keyword = trimmed(qs("q"));
        if (keyword) { params.set("q", keyword); }
        const status = qs("status").value;
        if (status) { params.set("status", status); }
        const result = await requestJSON("/api/candidates?" + params.toString());
        if (!result.ok) {
          text(qs("pool-error"), errorText(result));
          show(qs("pool-error"));
          return;
        }
        state.total = result.body.total || 0;
        const items = result.body.items || [];
        setPager();
        if (items.length === 0) {
          show(qs("pool-empty"));
          return;
        }
        items.forEach((candidate) => list.appendChild(renderCandidate(candidate)));
      } finally {
        hide(qs("pool-loading"));
      }
    }

    function renderCandidate(candidate) {
      const item = li("item");
      const title = paragraph("", "item-title");
      const link = document.createElement("a");
      link.href = "/opportunity/" + encodeURIComponent(candidate.id);
      link.textContent = candidate.title;
      title.appendChild(link);
      item.appendChild(title);

      const meta = paragraph("", "meta");
      meta.appendChild(badge("badge-status-" + candidate.status, POOL_LABELS[candidate.status] || candidate.status));
      meta.appendChild(document.createTextNode(" "));
      meta.appendChild(badge("badge-origin-" + candidate.data_origin, ORIGIN_LABELS[candidate.data_origin] || candidate.data_origin));
      meta.appendChild(document.createTextNode(" ｜更新于 " + (candidate.updated_at || "未知")));
      item.appendChild(meta);
      item.appendChild(paragraph("理由：" + (candidate.status_reason || "未提供"), "meta"));
      return item;
    }

    async function loadSources() {
      const list = qs("sources-list");
      hide(qs("sources-empty")); hide(qs("sources-error"));
      clear(list);
      show(qs("sources-loading"));
      try {
        const result = await requestJSON("/api/sources");
        if (!result.ok) { text(qs("sources-error"), errorText(result)); show(qs("sources-error")); return; }
        const items = result.body.items || [];
        if (items.length === 0) { show(qs("sources-empty")); return; }
        items.forEach((source) => {
          const item = li("item");
          item.appendChild(paragraph(source.name + "（" + source.channel + "）", "item-title"));
          const mode = source.access_mode === "manual_import" ? "人工导入" : source.access_mode;
          item.appendChild(paragraph("访问方式：" + mode + "｜访问条件已核验：" + triState(source.access_verified), "meta"));
          item.appendChild(paragraph("最后成功：" + (source.last_success_at || "暂无成功记录") + "｜最后错误：" + (source.last_error || "无"), "meta"));
          list.appendChild(item);
        });
      } finally {
        hide(qs("sources-loading"));
      }
    }

    async function loadRuns() {
      const list = qs("runs-list");
      hide(qs("runs-empty")); hide(qs("runs-error"));
      clear(list);
      show(qs("runs-loading"));
      try {
        const result = await requestJSON("/api/runs?limit=10");
        if (!result.ok) { text(qs("runs-error"), errorText(result)); show(qs("runs-error")); return; }
        const items = result.body.items || [];
        if (items.length === 0) { show(qs("runs-empty")); return; }
        items.forEach((run) => {
          const item = li("item");
          item.appendChild(paragraph(run.run_type + "｜" + run.status + "｜" + (run.started_at || "未知开始时间"), "item-title"));
          item.appendChild(paragraph("触发：" + run.trigger + "｜发现／新增／重复：" + run.items_found + "／" +
            run.items_new + "／" + run.items_dup + "｜备注：" + (run.error_summary || run.notes || "无"), "meta"));
          list.appendChild(item);
        });
      } finally {
        hide(qs("runs-loading"));
      }
    }
  }

  // ---------------------------------------------------------------- P2 机会详情
  function initOpportunity() {
    const holder = document.querySelector("[data-candidate-id]");
    if (!holder) { return; }
    const candidateId = holder.dataset.candidateId;

    const draftForm = qs("draft-form");
    const draftSubmit = draftForm ? draftForm.querySelector("button[type=submit]") : null;
    if (draftForm) { draftForm.addEventListener("submit", safe(submitDraft)); }
    if (qs("draft-copy")) { qs("draft-copy").addEventListener("click", safe(copyDraft)); }

    const feedbackForm = qs("feedback-form");
    const feedbackSubmit = feedbackForm ? feedbackForm.querySelector("button[type=submit]") : null;
    if (feedbackForm) { feedbackForm.addEventListener("submit", safe(submitFeedback)); }
    if (qs("feedback-kind")) { qs("feedback-kind").addEventListener("change", safe(syncFeedbackFields)); }

    document.querySelectorAll(".review-resolve").forEach((button) => {
      button.addEventListener("click", safe(() => resolveReview(button)));
    });
    syncFeedbackFields();

    async function submitDraft(event) {
      event.preventDefault();
      hide(qs("draft-error"));
      hide(qs("draft-output"));
      show(qs("draft-loading"));
      const draftButtons = [draftSubmit];
      draftButtons.forEach((b) => setEnabled(b, false));
      try {
        const result = await requestJSON("/api/candidates/" + encodeURIComponent(candidateId) + "/drafts", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ kind: qs("draft-kind").value, method: "template" }),
        });
        if (!result.ok) { text(qs("draft-error"), errorText(result)); show(qs("draft-error")); return; }
        text(qs("draft-body"), result.body.body || "");
        show(qs("draft-output"));
        text(qs("draft-copy-note"), "草稿 id " + result.body.id + "（template " + result.body.template_version +
          "，状态 " + result.body.status + "；无发送动作）");
        show(qs("draft-copy-note"));
      } finally {
        draftButtons.forEach((b) => setEnabled(b, true));
        hide(qs("draft-loading"));
      }
    }

    async function copyDraft() {
      const body = qs("draft-body").textContent || "";
      try {
        if (!navigator.clipboard || !navigator.clipboard.writeText) { throw new Error("clipboard unavailable"); }
        await navigator.clipboard.writeText(body);
        text(qs("draft-copy-note"), "已复制到剪贴板（仅复制，不发送）。");
      } catch (err) {
        const range = document.createRange();
        range.selectNodeContents(qs("draft-body"));
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        text(qs("draft-copy-note"), "剪贴板不可用：已选中草稿文本，请按 Ctrl+C 复制（仅复制，不发送）。");
      }
      show(qs("draft-copy-note"));
    }

    function syncFeedbackFields() {
      const kind = qs("feedback-kind").value;
      const amountField = qs("fb-amount");
      const orderField = qs("fb-order-ref");
      const relatedField = qs("fb-related");
      const refundField = qs("fb-refund-state");
      const minutesField = qs("fb-minutes");
      // Contract §5.4: both sale and refund carry amount_minor; manual_time must not.
      const needsAmount = kind === "sale" || kind === "refund";
      const isRefund = kind === "refund";
      const isManual = kind === "manual_time";
      amountField.value = needsAmount ? amountField.value : "";
      relatedField.value = isRefund ? relatedField.value : "";
      refundField.value = isRefund ? refundField.value : "";
      minutesField.value = isManual ? minutesField.value : "";
      orderField.value = isManual ? "" : orderField.value;
      setEnabled(amountField, needsAmount);
      setEnabled(relatedField, isRefund);
      setEnabled(refundField, isRefund);
      setEnabled(minutesField, isManual);
      setEnabled(orderField, !isManual);
    }

    function localFeedbackError(field, reason) {
      hide(qs("feedback-ok"));
      text(qs("feedback-error"), "提交被拒绝：" + field + "：" + reason);
      show(qs("feedback-error"));
    }

    async function submitFeedback(event) {
      event.preventDefault();
      hide(qs("feedback-error"));
      hide(qs("feedback-ok"));
      const kind = qs("feedback-kind").value;
      const payload = { kind: kind };
      const needsAmount = kind === "sale" || kind === "refund";
      let amount = { ok: true, minor: undefined };
      if (needsAmount) {
        amount = parseYuan(qs("fb-amount").value);
        if (!amount.ok) { localFeedbackError("amount_minor", amount.reason); return; }
      }
      if (kind === "sale") {
        if (amount.minor !== undefined) { payload.amount_minor = amount.minor; }
        const orderRef = trimmed(qs("fb-order-ref"));
        if (orderRef) { payload.order_ref = orderRef; }
      } else if (kind === "refund") {
        if (amount.minor === undefined) { localFeedbackError("amount_minor", "退款必须填写金额"); return; }
        const related = qs("fb-related").value;
        if (!related) { localFeedbackError("related_feedback_id", "退款必须选择关联成交"); return; }
        const refundState = qs("fb-refund-state").value;
        if (!refundState) { localFeedbackError("refund_state", "退款必须选择 pending 或 settled"); return; }
        payload.amount_minor = amount.minor;
        payload.related_feedback_id = related;
        payload.refund_state = refundState;
        const orderRef = trimmed(qs("fb-order-ref"));
        if (orderRef) { payload.order_ref = orderRef; }
      } else {
        const minutes = parseMinutes(qs("fb-minutes").value);
        if (!minutes.ok) { localFeedbackError("actual_minutes", minutes.reason); return; }
        if (minutes.minutes === undefined) { localFeedbackError("actual_minutes", "manual_time 必填人工分钟"); return; }
        payload.actual_minutes = minutes.minutes;
      }

      show(qs("feedback-loading"));
      setEnabled(feedbackSubmit, false);
      try {
        const result = await requestJSON("/api/candidates/" + encodeURIComponent(candidateId) + "/feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(payload),
        });
        if (!result.ok) { text(qs("feedback-error"), "提交被拒绝：" + errorText(result)); show(qs("feedback-error")); return; }
        const predicted = result.body.predicted_net_per_order_minor;
        text(qs("feedback-ok"), "已记录反馈 " + result.body.id + "（" + result.body.kind + "）。成交时预测快照：" +
          (predicted === null || predicted === undefined ? "未知（情景不完整，未按 0 处理）" : predicted + " 分") +
          "；实际利润核算属 S5。");
        show(qs("feedback-ok"));
        await refreshFromApi();   // sale / refund / manual_time all refresh the same feedback region
      } finally {
        setEnabled(feedbackSubmit, true);
        hide(qs("feedback-loading"));
      }
    }

    /* Rebuild the sale list and the feedback region (same table kept, empty state toggled by row count). */
    async function refreshFromApi() {
      const result = await requestJSON("/api/candidates/" + encodeURIComponent(candidateId));
      if (!result.ok) { return; }
      const feedback = result.body.feedback || [];
      const sales = feedback.filter((row) => row.kind === "sale");
      const options = [{ value: "", label: "—" }].concat(sales.map((row) => ({
        value: row.id,
        label: row.id + "｜" + (row.order_ref || "无订单号") + "｜" + formatMoney(row.amount_minor),
      })));
      fillSelect(qs("fb-related"), options);

      const tbody = qs("feedback-rows");
      if (tbody) {
        clear(tbody);
        feedback.forEach((row) => {
          const tr = document.createElement("tr");
          [row.kind, formatMoney(row.amount_minor), row.order_ref || "—", row.occurred_at,
           formatMoney(row.predicted_net_per_order_minor), row.refund_state || "—",
           formatMoney(row.actual_net_per_order_minor)].forEach((value) => {
            const td = document.createElement("td");
            td.textContent = value;
            tr.appendChild(td);
          });
          tbody.appendChild(tr);
        });
      }
      const table = qs("feedback-table");
      const empty = qs("feedback-empty");
      if (feedback.length === 0) {
        if (table) { table.hidden = true; }
        show(empty);
      } else {
        if (table) { table.hidden = false; }
        hide(empty);
      }
      syncFeedbackFields();
    }

    async function resolveReview(button) {
      hide(qs("review-error"));
      hide(qs("review-ok"));
      setEnabled(button, false);
      try {
        const result = await requestJSON("/api/review-items/" + encodeURIComponent(button.dataset.reviewId) + "/resolve", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ status: button.dataset.status || "dismissed" }),
        });
        if (!result.ok) { text(qs("review-error"), errorText(result)); show(qs("review-error")); return; }
        text(qs("review-ok"), "复核项 " + result.body.id + " 已标记为 " + result.body.status +
          "（不会把已失效的核验恢复为已核验）；候选状态：" + (result.body.candidate_status || "未变化") + "。刷新页面查看最新状态。");
        show(qs("review-ok"));
      } finally {
        setEnabled(button, true);
      }
    }
  }

  // ---------------------------------------------------------------- P3 导入
  function initImportPage() {
    const validateButton = qs("import-validate");
    const commitButton = qs("import-commit");
    if (!validateButton || !commitButton) { return; }

    let previewGrant = null;   // {token, generation}: set only by a clean preview of the same file + format
    let generation = 0;        // bumped by every file/format change and every invalidation
    let busy = false;

    function currentFile() {
      const files = qs("import-file").files;
      return files && files[0] ? files[0] : null;
    }

    function tokenFor(file) {
      if (!file) { return null; }
      return [file.name, file.size, file.lastModified, qs("import-format").value].join("|");
    }

    function grantIsValid() {
      return Boolean(previewGrant)
        && previewGrant.generation === generation
        && previewGrant.token === tokenFor(currentFile());
    }

    function invalidate(message) {
      generation += 1;          // also makes any in-flight response stale
      previewGrant = null;
      commitButton.disabled = true;
      hide(qs("import-saved-note"));
      refreshHint(message);
    }

    function refreshHint(message) {
      text(qs("import-hint"), message || (grantIsValid()
        ? "预览已通过（未保存）：可以确认写入；写入时服务端会再次完整校验。文件或格式一旦变更，预览即失效。"
        : "需先对同一文件与同一格式完成一次成功预览（saved=false 且行级无错误）后，才能确认导入。"));
      show(qs("import-hint"));
    }

    commitButton.disabled = true;
    refreshHint();

    qs("import-file").addEventListener("change", safe(() => invalidate("文件已变更，请重新预览。")));
    qs("import-format").addEventListener("change", safe(() => invalidate("格式已变更，请重新预览。")));
    validateButton.addEventListener("click", safe(() => runImport("validate")));
    commitButton.addEventListener("click", safe(() => {
      if (!grantIsValid()) {
        invalidate("预览无效或已过期：请先对同一文件与同一格式成功预览，再确认导入。");
        return undefined;
      }
      return runImport("atomic");
    }));

    /* A preview only counts when it saved nothing and every row is clean (HTTP 200 is not enough). */
    function previewRowsClean(payload) {
      const counts = payload.counts || {};
      if ((counts.rejected || 0) > 0) { return false; }
      return (payload.rows || []).every((row) => (row.errors || []).length === 0
        && (row.action || row.preview_action || "created") !== "rejected");
    }

    async function runImport(mode) {
      if (busy) { return; }
      const isCommit = mode === "atomic";
      hide(qs("import-error"));
      hide(qs("import-result"));
      hide(qs("import-saved-note"));      // a new request clears the previous "未保存" note
      clear(qs("import-rows"));
      clear(qs("import-summary"));
      const file = currentFile();
      if (!file) {
        text(qs("import-error"), "请先选择 CSV/JSON 文件。");
        show(qs("import-error"));
        return;
      }
      const format = qs("import-format").value;
      const requestGeneration = generation;
      const requestFile = file;
      const requestToken = tokenFor(file);
      if (!isCommit) { previewGrant = null; commitButton.disabled = true; }  // a new preview revokes the old grant
      const params = new URLSearchParams();
      if (format) { params.set("format", format); }
      params.set("mode", mode);
      const data = new FormData();
      data.append("file", file);
      busy = true;
      setEnabled(validateButton, false);
      setEnabled(commitButton, false);
      show(qs("import-loading"));
      try {
        const result = await requestJSON("/api/imports?" + params.toString(), { method: "POST", body: data });
        const payload = result.body || {};
        if (result.ok) {
          if (isCommit && payload.batch_id) {
            const batch = await requestJSON("/api/imports/" + encodeURIComponent(payload.batch_id));
            renderResult(batch.ok ? batch.body : null, payload, false);
          } else {
            renderResult(null, payload, payload.saved === false);
          }
          if (!isCommit && payload.saved === false) {
            const stillCurrent = requestGeneration === generation
              && currentFile() === requestFile
              && tokenFor(currentFile()) === requestToken;
            if (stillCurrent && previewRowsClean(payload)) {
              previewGrant = { token: requestToken, generation: requestGeneration };
              show(qs("import-saved-note"));
              refreshHint();
            } else {
              previewGrant = null;
              commitButton.disabled = true;
              text(qs("import-error"), stillCurrent
                ? "预览未通过：存在行级错误（未保存任何数据），修正后请重新预览。"
                : "预览结果已过期：文件或格式在预览期间已变更，请重新预览。");
              show(qs("import-error"));
              refreshHint();
            }
          }
          return;
        }
        // Atomic rejection answers 422 with a batch payload (rows + batch_id), not an error envelope.
        if (payload.batch_id && (payload.rows || payload.rows_total !== undefined)) {
          const batch = await requestJSON("/api/imports/" + encodeURIComponent(payload.batch_id));
          renderResult(batch.ok ? batch.body : null, payload, false);
          text(qs("import-error"), "本次写入被拒绝（atomic）：未写入业务数据；行级原因见下方与批次 " + payload.batch_id + "。");
          show(qs("import-error"));
          return;
        }
        text(qs("import-error"), errorText(result));
        show(qs("import-error"));
        invalidate();
      } catch (err) {
        text(qs("import-error"), "请求失败：" + ((err && err.message) || err));
        show(qs("import-error"));
        invalidate();
      } finally {
        if (isCommit) { previewGrant = null; }   // a write revokes the preview authority
        hide(qs("import-loading"));
        busy = false;
        setEnabled(validateButton, true);
        setEnabled(commitButton, grantIsValid());
      }
    }

    function renderResult(batchBody, payload, isPreview) {
      const summary = qs("import-summary");
      const counts = (batchBody && batchBody.batch && batchBody.batch.counts) || payload.counts || {};
      const countText = Object.keys(counts).length
        ? Object.keys(counts).map((key) => key + "=" + counts[key]).join("，")
        : "—";
      [
        ["模式", payload.mode || (isPreview ? "validate" : "atomic")],
        ["状态", payload.status || (isPreview ? "未保存（预览）" : "—")],
        ["总行数", payload.rows_total === undefined ? "—" : payload.rows_total],
        ["计数", countText],
      ].forEach((pair) => definition(pair[0], pair[1]).forEach((node) => summary.appendChild(node)));

      const list = qs("import-rows");
      const batchRows = batchBody && batchBody.row_results;
      const rowItems = (batchRows && batchRows.length)
        ? batchRows.map((row) => ({
            row_no: row.row_no,
            action: row.action,
            errors: row.reason_code ? [{ code: row.reason_code, reason: row.reason_detail }] : [],
            warnings: [],
          }))
        : (payload.rows || []);
      (payload.project_errors || []).forEach((err) => {
        rowItems.unshift({ row_no: err.row, action: "项目级问题", errors: [err], warnings: [] });
      });
      if (rowItems.length === 0) {
        list.appendChild(paragraph("无行级问题。", "meta"));
      }
      rowItems.forEach((row) => {
        const item = li("item");
        const action = row.action || row.preview_action || "—";   // preview rows carry preview_action
        item.appendChild(paragraph("第 " + row.row_no + " 行：action=" + action, "item-title"));
        (row.errors || []).forEach((err) => {
          item.appendChild(paragraph("错误 " + (err.code || "") + "：" + (err.reason || ""), "meta"));
        });
        (row.warnings || []).forEach((warn) => {
          item.appendChild(paragraph("提示 " + (warn.code || "") + "：" + (warn.reason || ""), "meta"));
        });
        list.appendChild(item);
      });

      const batchLine = qs("import-batch");
      if (batchBody && batchBody.batch) {
        const batch = batchBody.batch;
        text(batchLine, "批次 " + batch.id + "｜模式 " + batch.mode + "｜状态 " + batch.status +
          "｜行数 " + batch.rows_total + "｜创建 " + batch.created_at);
      } else if (isPreview) {
        text(batchLine, "预览未生成批次，也未写入运行与幂等记录。确认后由正式导入路径（atomic/partial）再次完整校验并写入。");
      } else {
        text(batchLine, "批次 id：" + (payload.batch_id || "—") + "（写入路径为 atomic/partial）");
      }
      show(qs("import-result"));
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const page = document.body.dataset.page;
    if (page === "home") { initHome(); }
    else if (page === "opportunity") { initOpportunity(); }
    else if (page === "import") { initImportPage(); }
  });

  /* Exposed for the Node behavior harness (tests/ui). Not used by the pages. */
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { parseYuan: parseYuan, parseMinutes: parseMinutes, triState: triState };
  }
})();
