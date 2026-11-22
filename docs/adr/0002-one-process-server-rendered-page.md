# One FastAPI process serves a server-rendered page, not a separate frontend app

The run page is server-rendered HTML from the same FastAPI process that owns the run, with a little JavaScript for selection and status. We dropped the earlier Next.js plan because the judges kill the process on stage: one process restarts cleanly, the browser and the organizer output read the same saved run, and there is no second service to fall out of sync. Revisit only if the product needs a rich client after the event.
