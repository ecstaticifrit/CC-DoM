# How the team works in this repo

Goal: nobody waits on a pull, nobody overwrites anybody, and every working increment is on `main` within minutes.

## 1. Trunk-based, short branches

- `main` is always runnable. The organizers watch it.
- One branch per ticket: `t<NN>-<slug>`, for example `t04-review-five-bills`.
- Keep branches under about 45 minutes of work. Split the ticket if it grows.
- Before you start: `git switch main && git pull --rebase`.
- Finish with one pull request and squash-merge it yourself:

```bash
git push -u origin HEAD
gh pr create --fill --base main
gh pr merge --squash --delete-branch --auto
```

- After any merge lands, everyone runs `git pull --rebase` on their branch. Rebase, never merge `main` into a branch.

## 2. Claim tickets on `main` (the lock)

1. Pick the lowest-numbered ticket in `.scratch/friday-payment-run/issues/` whose `Blocked by` tickets are all done.
2. Set `**Status:** claimed by <name>` in the ticket, commit with `claim: <NN>`, and push straight to `main`.
3. If the push is rejected, someone else claimed first: pull and pick again.
4. When the pull request merges, tick the ticket's boxes and add a line under `## Comments` with the PR link.

Agents (Devin sessions) follow the same claim rule. One agent session per ticket.

## 3. Two lanes so we rarely touch the same files

After ticket 02 lands, work splits into two lanes that own different folders:

| Lane | Tickets | Owns |
| --- | --- | --- |
| A: pay bills | 03, 04, 05, 06, 07, 08 | `kavach/payouts/`, `kavach/sources/` |
| B: post charges | 09, 10, 11, 12 | `kavach/postings/`, `kavach/legal_payee/` |
| Shared (one owner at a time) | 02, 13, 14, 16 | `kavach/web/`, `kavach/store/`, `kavach/receipt/` |

Folder names are a proposal. Ticket 02 fixes them; update this table in the same PR.

Changes to shared files (database schema, page layout, config) go in their own tiny PR, merged first, so the other lane can rebase onto them.

## 4. Pairing without push and pull

When two people must work on the same code at the same time (ticket 02, the hour-3 change, the final rehearsal), use VS Code Live Share or one shared screen on the same machine instead of two branches.

## 5. Shared words and decisions

- Use the words in `GLOSSARY.md` in code, tickets, tests and the UI. If a word is missing, add it in the same PR.
- Hard-to-reverse decisions live in `docs/adr/`. Read them before changing payouts, the page architecture or legal-payee sourcing.
- The spec is `.scratch/friday-payment-run/spec.md`.

## 6. Secrets

- Never commit keys. Put them in `.env` (git-ignored). `.env.example` lists the names only.
- Each person keeps their own `.env`. Share values person to person, never in the repo, tickets, logs or chat history that gets committed.

## 7. Cadence on event day

- Every 45 minutes: 2-minute stand-up. What merged, what is claimed, what is blocked.
- Hour 3: stop, read the organizer's change, assign it, then resume.
- Hour 6.5: feature freeze. Only fixes and rehearsal.
