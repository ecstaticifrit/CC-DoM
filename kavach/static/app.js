(() => {
  // Start page: show the chosen file.
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

  // Decision card and bank-change card share one dialog; the content comes from a <template>.
  const why = document.getElementById("why-dialog");
  const order = Array.from(document.querySelectorAll(".row")).map(r => r.dataset.row);
  let current = null;
  function openCard(kind, rowNumber, opener) {
    const tpl = document.getElementById(`${kind}-${rowNumber}`);
    if (!tpl || !why) return;
    const inner = why.querySelector(".dlg-inner");
    inner.replaceChildren(tpl.content.cloneNode(true));
    why.setAttribute("aria-labelledby", kind === "change" ? "change-title" : "why-title");
    current = String(rowNumber);
    document.querySelectorAll(".row").forEach(r => r.setAttribute("aria-selected", String(r.dataset.row === current)));
    const errorBox = inner.querySelector("[data-change-error]");
    const errorText = document.querySelector("[data-change-error-text]");
    if (errorBox && errorText && errorText.dataset.changeErrorText && location.hash === `#change-${rowNumber}`) {
      errorBox.textContent = errorText.dataset.changeErrorText;
      errorBox.hidden = false;
      errorText.dataset.changeErrorText = "";
    }
    if (opener !== undefined) why.returnFocus = opener;
    if (!why.open) why.showModal();
    history.replaceState(null, "", `#${kind}-${rowNumber}`);
    const focusable = inner.querySelector("input[type='text'], .dlg-actions .btn:not([data-step])");
    if (focusable) focusable.focus();
  }
  const openRow = (n, opener) => openCard("why", n, opener);
  if (why) {
    why.addEventListener("click", e => {
      const step = e.target.closest("[data-step]");
      const change = e.target.closest("[data-open-change]");
      const back = e.target.closest("[data-open-row]");
      if (step && current) {
        const i = order.indexOf(current);
        const next = order[(i + Number(step.dataset.step) + order.length) % order.length];
        openRow(next);
      } else if (change) {
        e.preventDefault();
        openCard("change", change.dataset.openChange);
      } else if (back) {
        openRow(back.dataset.openRow);
      }
    });
    why.addEventListener("keydown", e => {
      if (e.target.closest("input, textarea, select")) return;
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        const btn = why.querySelector(`[data-step="${e.key === "ArrowRight" ? 1 : -1}"]`);
        if (btn) { e.preventDefault(); btn.click(); }
      }
    });
    why.addEventListener("close", () => {
      current = null;
      history.replaceState(null, "", location.pathname + location.search);
    });
  }
  document.querySelectorAll("[data-open-row]").forEach(btn => {
    if (btn.closest("template")) return;
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

  const linked = location.hash.match(/^#(why|change)-(\d+)$/);
  if (linked) openCard(linked[1], linked[2], null);

  // Toast: dismiss on click, fade out after a few seconds.
  const toast = document.querySelector(".toast");
  if (toast) {
    const hide = () => { toast.classList.add("is-leaving"); setTimeout(() => toast.remove(), 200); };
    toast.querySelector("[data-toast-close]").addEventListener("click", hide);
    setTimeout(hide, 6000);
    const url = new URL(location.href);
    ["done", "n", "change_error"].forEach(k => url.searchParams.delete(k));
    history.replaceState(null, "", url.pathname + url.search + location.hash);
  }

  // Copy buttons.
  document.querySelectorAll("[data-copy]").forEach(btn => {
    btn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(btn.dataset.copy);
        btn.classList.add("is-copied");
        btn.setAttribute("aria-label", "Copied");
        setTimeout(() => { btn.classList.remove("is-copied"); btn.setAttribute("aria-label", "Copy the SHA-256 fingerprint"); }, 1600);
      } catch { /* clipboard blocked: the full value stays in the title attribute */ }
    });
  });

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
    // Hold to sign: the fill is a progress indicator, so it runs linear; release snaps back.
    const hold = sign.querySelector("[data-sign-submit]");
    const holdLabel = hold.querySelector("[data-hold-label]");
    const holdMs = Number(hold.dataset.holdMs || 1200);
    hold.style.setProperty("--hold-ms", `${holdMs}ms`);
    let holdTimer = null;
    const finishHold = () => {
      hold.classList.remove("is-holding");
      hold.classList.add("is-done");
      holdLabel.textContent = "Signing…";
      sign.querySelector("form").submit();
    };
    const startHold = () => {
      if (hold.classList.contains("is-done")) return;
      hold.classList.add("is-holding");
      holdLabel.textContent = "Keep holding…";
      holdTimer = setTimeout(finishHold, holdMs);
    };
    const cancelHold = () => {
      if (hold.classList.contains("is-done")) return;
      clearTimeout(holdTimer);
      hold.classList.remove("is-holding");
      holdLabel.textContent = "Hold to sign";
    };
    hold.addEventListener("pointerdown", e => {
      if (e.button !== 0) return;
      hold.setPointerCapture(e.pointerId);
      startHold();
    });
    ["pointerup", "pointercancel", "lostpointercapture"].forEach(ev => hold.addEventListener(ev, cancelHold));
    hold.addEventListener("keydown", e => {
      if ((e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); startHold(); }
    });
    hold.addEventListener("keyup", e => { if (e.key === " " || e.key === "Enter") cancelHold(); });
    hold.addEventListener("contextmenu", e => e.preventDefault());
    sign.addEventListener("close", () => { hold.classList.remove("is-done"); cancelHold(); });
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
