(() => {
  // Start page: show chosen filename and toggle expected columns by job mode.
  const fileInput = document.querySelector(".dropzone input[type='file']");
  const dropzone = document.querySelector(".dropzone");
  const chosen = document.querySelector(".file-chosen");
  if (fileInput && chosen) {
    const showFile = () => {
      const f = fileInput.files && fileInput.files[0];
      chosen.textContent = f ? `Selected: ${f.name}` : "";
    };
    fileInput.addEventListener("change", showFile);
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

  // Run page: evidence drawer, batch selection, and reconnect banner.
  const head = document.querySelector(".run-head");
  if (!head) return;
  const runId = head.dataset.runId;
  const panel = document.querySelector(".panel");
  const conn = document.querySelector(".conn");
  let lastUpdate = head.dataset.updated;
  let lost = false;

  function select(row) {
    document.querySelectorAll(".row").forEach(r => r.setAttribute("aria-selected", "false"));
    document.querySelectorAll(".evidence").forEach(e => { e.hidden = true; });
    row.setAttribute("aria-selected", "true");
    const evidence = document.querySelector(`.evidence[data-for="${row.dataset.row}"]`);
    if (!evidence || !panel) return;
    evidence.hidden = false;
    const title = row.querySelector("th").textContent.trim();
    const amount = row.querySelector(".num").textContent.trim();
    panel.innerHTML = `<h2><span>${title}</span><span class="mono">${amount}</span></h2>` + evidence.querySelector("dl").outerHTML;
  }

  const allRows = document.querySelectorAll(".row");
  allRows.forEach(row => {
    row.addEventListener("click", () => select(row));
    row.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(row); }
    });
  });
  if (allRows.length > 0) select(allRows[0]);

  const selected = document.querySelector(".selected");
  const reviewBtn = document.querySelector(".batch button[type='submit']");
  const selectAll = document.querySelector("[data-select-all]");
  const rowBoxes = Array.from(document.querySelectorAll('input[name="row"]'));

  function updateSelection() {
    if (!selected) return;
    let n = 0, total = 0;
    rowBoxes.forEach(box => {
      if (box.checked) {
        n += 1;
        total += parseFloat(box.closest("tr").dataset.amount || "0");
      }
    });
    selected.textContent = `${n} bill${n === 1 ? "" : "s"} selected · Rs ${total.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
    if (reviewBtn) reviewBtn.disabled = n === 0;
    if (selectAll) selectAll.checked = rowBoxes.length > 0 && n === rowBoxes.length;
  }

  rowBoxes.forEach(box => {
    box.addEventListener("click", e => e.stopPropagation());
    box.addEventListener("change", updateSelection);
  });
  if (selectAll) {
    selectAll.addEventListener("change", () => {
      rowBoxes.forEach(box => { box.checked = selectAll.checked; });
      updateSelection();
    });
  }
  updateSelection();

  async function poll() {
    try {
      const res = await fetch(`/runs/${runId}/status.json`, { cache: "no-store" });
      if (!res.ok) throw new Error(String(res.status));
      const status = await res.json();
      if (lost) { conn.hidden = true; lost = false; }
      if (status.updated_at !== lastUpdate) location.reload();
    } catch {
      lost = true;
      conn.querySelector("time").textContent = lastUpdate;
      conn.hidden = false;
    }
  }
  setInterval(poll, 3000);
})();
