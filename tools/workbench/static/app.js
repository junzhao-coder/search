/* 渐进增强：移动端目录折叠 + 记住展开状态；无 JS 时导航仍可用（结构折叠用 body class） */
(function () {
  "use strict";

  var body = document.body;
  if (window.matchMedia("(max-width: 900px)").matches) {
    body.classList.add("nav-collapsed");
  }

  var toggle = document.querySelector(".nav-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var collapsed = body.classList.toggle("nav-collapsed");
      toggle.setAttribute("aria-expanded", String(!collapsed));
    });
  }

  // 展开证据后保持焦点可见（键盘可达）
  document.querySelectorAll("details").forEach(function (node) {
    node.addEventListener("toggle", function () {
      if (node.open) {
        var summary = node.querySelector("summary");
        if (summary) { summary.focus({ preventScroll: true }); }
      }
    });
  });

  // 分组整行可点：按钮 aria-expanded + 隐藏明细行（button 原生支持 Enter/Space）
  document.querySelectorAll("tr[data-toggle]").forEach(function (row) {
    var id = row.getAttribute("data-toggle");
    var btn = row.querySelector(".row-toggle");
    var panel = document.getElementById(id);
    if (!btn || !panel) { return; }
    var count = btn.getAttribute("data-count") || "";
    function setOpen(open) {
      panel.hidden = !open;
      btn.setAttribute("aria-expanded", String(open));
      btn.textContent = (open ? "收起组内明细（" : "展开组内明细（") + count + " 条）";
    }
    btn.addEventListener("click", function (event) {
      event.stopPropagation();
      setOpen(panel.hidden);
    });
    row.addEventListener("click", function (event) {
      if (event.target.closest("a, button, summary, details")) { return; }
      setOpen(panel.hidden);
      btn.focus({ preventScroll: true });
    });
  });
})();
