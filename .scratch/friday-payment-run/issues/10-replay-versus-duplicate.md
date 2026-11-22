# 10: Distinguish a replay from a duplicate charge

**What to build:** Reopening the same statement returns its saved results. Encountering a similar charge on another row preserves both rows and holds the possible duplicate for review.

**Blocked by:** 09

**Status:** ready-for-agent

- [ ] Identify each row by client ID, SHA-256 of the statement input, and original row number. For a file, hash the original bytes, not its filename. Renaming and reuploading it returns the existing outcomes and posting IDs.
- [ ] For JSON requests, hash the canonical UTF-8 statement payload with sorted object keys and no formatting whitespace. Exclude transport metadata and preserve row order and repeated rows.
- [ ] Replay a JSON request after changing its spacing, object-key order, and transport metadata. It returns the saved outcomes. Two identical source rows still have two distinct row identities.
- [ ] Compare payee, amount, currency, and date within and across statements for the same client. Keep a possible duplicate visible with a reason and no new posting; do not merge it into the first charge.
- [ ] Verify replay after an interrupted write and verify isolation across clients. Neither an incomplete write nor a different client's statement can supply this row's saved outcome.
