# Issue tracker: Local markdown

## Specs and implementation tickets

- Publish each feature's spec at `.scratch/<feature-slug>/spec.md`.
- Publish each ticket in its own file at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`. Start numbering at `01` within each feature.
- Create directories when you publish the first file that needs them.
- To fetch a ticket, read its file. For a ticket number, look in the relevant feature's `issues/` directory.
- Record triage state near the top as `Status: <label>`. Use the strings in `docs/agents/triage-labels.md`.
- Append comments under `## Comments` in the ticket file.

## Wayfinder

- Keep the map in `.scratch/<effort>/map.md` with sections for Notes, Decisions-so-far, and Fog.
- Keep each child ticket in `.scratch/<effort>/issues/<NN>-<slug>.md`. Put the question in the body.
- Record `Type: research`, `Type: prototype`, `Type: grilling`, or `Type: task`.
- List dependencies near the top as `Blocked by: 01, 02`. A ticket is unblocked when every listed ticket is resolved.
- Select the lowest-numbered open, unblocked, unclaimed ticket. Record `Status: claimed` before starting work.
- To resolve it, append the answer under `## Answer` and set `Status: resolved`. Add a short answer and a ticket link to Decisions-so-far in the map.
