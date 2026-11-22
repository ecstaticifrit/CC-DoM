(() => {
  // Start page: show the chosen file and the expected columns for the chosen job.
  const fileInput = document.querySelector(".dropzone input[type='file']");
  const dropzone = document.querySelector(".dropzone");
  const chosen = document.querySelector(".file-chosen");
  if (fileInput && chosen) {
    fileInput.addEventListener("change", () => {
      const f = fileInput.files && fileInput.files[0];
      chosen.textContent = f ? `Selected: ${f.name}` : "";
    });
    if (dropzone) {
      ["dragenter", "dragover"].forEach(ev => dropzone.addEventListener(ev, () => dropzone.classList.add("dragover")));
      ["dragleave", "drop"].forEach(ev => dropzone.addEventListener(ev, () => dropzone.classList.remove("dragover")));
    }
  }
  const colsByMode = {
    pay_bills: "bill_id, carrier_id, carrier_name, amount, currency, account_number, ifsc, sender_email",
    post_lines: "date, description, amount, currency, reference",
  };
  const colsTarget = document.querySelector("[data-expected-cols]");
  document.querySelectorAll('input[name="mode"]').forEach(radio => {
    radio.addEventListener("change", () => {
      if (colsTarget && colsByMode[radio.value]) colsTarget.textContent = colsByMode[radio.value];
    });
  });

  // Run page.
  const head = document.querySelector(".run-head");
  if (!head) return;
  const runId = head.dataset.runId;
  const conn = document.querySelector(".conn");
  const inr = n => n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  let lastUpdate = head.dataset.updated;
  let lost = false;
  let reloadPending = false;

  // Dialogs: close on the close button and on a click outside the card.
  const anyOpen = () => document.querySelector("dialog[open]") !== null;
  document.querySelectorAll("dialog.dlg").forEach(dlg => {
    dlg.addEventListener("click", e => {
      if (e.target === dlg || e.target.closest("[data-close]")) dlg.close();
    });
    dlg.addEventListener("close", () => {
      if (dlg.returnFocus) dlg.returnFocus.focus();
      if (reloadPending && !anyOpen()) location.reload();
    });
  });

  // Decision card for one row.
  const why = document.getElementById("why-dialog");
  function openRow(rowNumber, opener) {
    const tpl = document.getElementById(`why-${rowNumber}`);
    if (!tpl || !why) return;
    const inner = why.querySelector(".dlg-inner");
    inner.replaceChildren(tpl.content.cloneNode(true));
    document.querySelectorAll(".row").forEach(r => r.setAttribute("aria-selected", String(r.dataset.row === String(rowNumber))));
    why.returnFocus = opener || null;
    why.showModal();
    const first = inner.querySelector(".dlg-actions .btn");
    if (first) first.focus();
  }
  document.querySelectorAll("[data-open-row]").forEach(btn => {
    btn.addEventListener("click", e => { e.stopPropagation(); openRow(btn.dataset.openRow, btn); });
  });
  document.querySelectorAll(".row").forEach(row => {
    row.addEventListener("click", e => {
      if (e.target.closest("input, a, button")) return;
      openRow(row.dataset.row, row);
    });
    row.addEventListener("keydown", e => {
      if (e.target !== row) return;
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openRow(row.dataset.row, row); }
    });
  });

  const linked = location.hash.match(/^#why-(\d+)$/);
  if (linked) openRow(linked[1], null);

  // Batch selection and the sign-off dialog.
  const form = document.querySelector("[data-sign-form]");
  const selected = document.querySelector(".selected");
  const reviewBtn = form ? form.querySelector(".signbar button[type='submit']") : null;
  const selectAll = document.querySelector("[data-select-all]");
  const boxes = Array.from(document.querySelectorAll('input[name="row"]'));
  const picked = () => boxes.filter(b => b.checked);
  const total = list => list.reduce((sum, b) => sum + parseFloat((b.dataset.amount || "0").replace(/,/g, "")), 0);

  function updateSelection() {
    if (!selected) return;
    const list = picked();
    selected.textContent = `${list.length} ${list.length === 1 ? "bill" : "bills"} selected · Rs ${inr(total(list))}`;
    if (reviewBtn) reviewBtn.disabled = list.length === 0;
    if (selectAll) selectAll.checked = boxes.length > 0 && list.length === boxes.length;
  }
  boxes.forEach(b => {
    b.addEventListener("click", e => e.stopPropagation());
    b.addEventListener("change", updateSelection);
  });
  if (selectAll) selectAll.addEventListener("change", () => { boxes.forEach(b => { b.checked = selectAll.checked; }); updateSelection(); });
  updateSelection();

  const sign = document.getElementById("sign-dialog");
  if (form && sign) {
    form.addEventListener("submit", e => {
      const list = picked();
      if (!list.length) return;
      e.preventDefault();
      const rowsEl = sign.querySelector("[data-sign-rows]");
      const itemsEl = sign.querySelector("[data-sign-items]");
      rowsEl.replaceChildren();
      itemsEl.replaceChildren();
      list.forEach(b => {
        const tr = document.createElement("tr");
        [b.dataset.ref, b.dataset.carrier, `${b.dataset.dest} · ${b.dataset.ifsc} · version ${b.dataset.version}`, `Rs ${b.dataset.amount}`]
          .forEach((text, i) => {
            const cell = document.createElement(i === 0 ? "th" : "td");
            if (i === 0) cell.scope = "row";
            if (i === 2) cell.className = "mono";
            if (i === 3) cell.className = "num";
            cell.textContent = text;
            tr.append(cell);
          });
        rowsEl.append(tr);
        const input = document.createElement("input");
        input.type = "hidden"; input.name = "item"; input.value = b.dataset.item;
        itemsEl.append(input);
      });
      const label = `Sign ${list.length} ${list.length === 1 ? "bill" : "bills"} for Rs ${inr(total(list))}?`;
      sign.querySelector("#sign-title").textContent = label;
      sign.returnFocus = reviewBtn;
      sign.showModal();
      sign.querySelector("[data-sign-submit]").focus();
    });
    sign.querySelector("form").addEventListener("submit", () => {
      const btn = sign.querySelector("[data-sign-submit]");
      btn.disabled = true;
      btn.textContent = "Signing…";
    });
  }

  // Keep the page in step with the server; never reload while a dialog is open.
  async function poll() {
    try {
      const res = await fetch(`/runs/${runId}/status.json`, { cache: "no-store" });
      if (!res.ok) throw new Error(String(res.status));
      const status = await res.json();
      if (lost) { conn.hidden = true; lost = false; }
      if (status.updated_at !== lastUpdate) {
        if (anyOpen()) reloadPending = true; else location.reload();
      }
    } catch {
      lost = true;
      conn.querySelector("time").textContent = lastUpdate;
      conn.hidden = false;
    }
  }
  setInterval(poll, 3000);
})();
