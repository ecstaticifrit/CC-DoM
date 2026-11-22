# 02: Open and resume a saved run

**What to build:** Let a controller upload a file, inspect one honest row outcome, and return to it after a restart. The browser and organizer output must describe the same saved run.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] One FastAPI process serves the run page with server-rendered HTML, CSS, and minimal JavaScript. Before submission, it shows both jobs, the selected mode, the budget, and the sandbox label.
- [ ] A valid upload creates a stable run URL backed by SQLite. An unsupported row stays visible with its missing fact; review neither posts it nor pays it.
- [ ] A malformed upload shows a readable, masked error rather than an empty successful receipt. No browser response or application log contains a full account number, email address, or raw email body.
- [ ] The ledger aligns amounts on the right and identifies rows on the left. Evidence appears beside the selection on desktop and beneath it on mobile. Status text makes sense without color.
- [ ] Stop the backend while the page is open. The page shows "Connection lost" and the last update time. After restart, reconnect or refresh returns the same run and row without resubmitting the file.
- [ ] Download the organizer-format result. Its mode, run ID, and row outcome agree with the page, including after restart.
