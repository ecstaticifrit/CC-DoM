(() => {
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
    if (!evidence) return;
    evidence.hidden = false;
    panel.innerHTML = `<h2>${row.querySelector("th").textContent}</h2>` + evidence.querySelector("dl").outerHTML;
  }
  document.querySelectorAll(".row").forEach(row => {
    row.addEventListener("click", () => select(row));
    row.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(row); } });
  });

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
