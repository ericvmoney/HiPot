# Scope: "My Roles" and great-match highlighting

Owner request, 2026-11-25. **Approved the same day, with the answers below** (PLAN.md decision 18):

1. Ranking is only within My Roles.
2. The statuses are as listed, Saved included.
3. Storage is `localStorage` on this device, with export and import, for now. It moves to account data once accounts exist.
4. Great-match highlighting works only while a persona is loaded, which is option (a). Nothing new is stored for it.
5. The "Applied to X?" bar on return is in.

## 1. My Roles

### The flow

1. A candidate sees a role they like on the board and opens it. The card links to the employer's posting, in a new tab.
2. They apply on the employer's site.
3. They come back to the board and mark the role **Applied** in one of three ways:
   - **Right-click the card** (or long-press on a phone): a small menu offers Applied, plus the menu entries it replaces (see "Card menu" below).
   - **The prompt on return:** when the board tab regains focus within 30 minutes of a role being opened from it, a quiet bar asks "Applied to *Controls Engineer* at AtmosZero?" with **Yes, add to My Roles** and **No**. It is the least effort for the common case, and it works on phones, where right-click does not exist. It never blocks the page, and it goes away by itself.
   - **The card's ⋯ button:** it shows on hover and on keyboard focus, and opens the same menu as right-click. This is the keyboard and screen-reader route, and the one a candidate can find without being told.
4. The role is added to **My Roles**. On the board, its card gets an **Applied** tag (or its current status) and a different border color.

### Card menu

Right-clicking the card replaces the browser's own menu on that card. That menu matters on a link (open in a new tab, copy the address), so the card menu repeats those entries:
- Open posting in a new tab
- Copy posting link
- Mark as applied, or "Update status…" if the role is already in My Roles
- Remove from My Roles

Shift+right-click (or right-click on the card's text, where the browser allows it) still shows the browser's menu.

### What is stored for each role

| Field | Notes |
|---|---|
| role id | The board's job id, for example `rippling:atmoszero-careers:840d…` |
| snapshot | Title, company name, place, published pay and posting address, copied when the role is marked. The entry stays readable after the posting leaves the board. |
| status | One of the statuses below. Set by hand, never inferred. |
| status history | Each change with its date. |
| applied on | A date, defaulting to today. |
| my order | The candidate's own ranking (see below). |
| notes | Optional free text. Private, and never shown on the board. |

**Statuses:** Saved (not applied yet: the same list without having applied), Applied, Recruiter screen, Interviewing, Offer, Accepted, Rejected, Withdrawn, No response. The owner may want fewer; see the open questions.

### The My Roles view

- A **My Roles** tab beside the board, with a count, for example "My Roles (6)".
- A list in the candidate's order. Each row shows:
  - title and company, which link to the posting while it is listed;
  - a status dropdown;
  - the applied date and days since the last status change;
  - its notes.
- **Ranking:** drag rows to reorder, or use up/down buttons, which also work from the keyboard. Sort by my order, status, applied date or company.
- A role whose posting has left the board shows "no longer listed (last seen *date*)". It is kept, never deleted for that.
- **Export and import** My Roles as a file (YAML, like the persona) that the candidate owns, to move between browsers or keep a copy. This uses the same `downloads` capability as the persona page on the shared link.

### On the board

- A role in My Roles shows its status as a tag ("Applied", "Interviewing"…). Its border uses a new color token (`--mine`) with a dark-mode value. The tag carries the meaning, so color is never the only cue.
- A new filter: **Hide roles in My Roles**, off by default.

### Where it is kept, and why (needs owner approval)

The board holds no accounts, and the persona stays on the device. My Roles follows the same rules:

- **On this device only:** browser `localStorage` under one key (`hipot-my-roles`). It is never in the page address, never sent anywhere, and never in the repository.
- This is the first thing the board keeps after the tab closes; the persona deliberately does not. A test currently asserts that the page never uses `localStorage`. That test changes to allow exactly this one key, and nothing about the persona.
- Every read and write is wrapped in try/catch. In a private window, or where storage is blocked, My Roles works for the tab only, and the page says so.
- The view says plainly that "My Roles is kept in this browser only", and offers export.
- **Not proposed:** syncing across devices. The artifact host could keep a private copy per signed-in viewer, but that means sign-in and a copy held off the device, which goes against the board's tenets. It stays a later option for the owner to decide.

### Tests

- A pure `MyRoles` block (the same pattern as `hipot-rank`) holds add, status change, reorder, export and import, run in V8 from pytest.
- Page tests check that:
  - storage uses one key only;
  - nothing about My Roles is ever in the page address;
  - the persona is still kept for the tab only;
  - a card in My Roles carries both the tag and the border class.

**Effort:** medium, about one working session for the board agent (A4): the storage block, the card menu and return prompt, the view, export and import, and the tests.

## 2. Great-match highlight

A role that fits the candidate's persona especially well is highlighted wherever it appears: in any sort order, with any filters, and when Best match is not the sort.

### What counts as a great match

The thresholds are relative, because absolute scores run lower for some personas than others. For the test persona, the best AtmosZero role scores 78 and ranks #7 of about 2,000 shown roles.

**Proposal:** a role is highlighted when it is in the persona's top 2% of shown roles, at most 30 roles, and scores 70 or more.

### How it looks

- A **Great match** badge, an accent stripe on the card's left edge, and the one-line "why it matches" in the badge's tooltip.
- A role in My Roles keeps its own border; the badge still shows.
- A filter chip, **Great matches only**.

### "Even if the persona is no longer applied"

There are two levels, and the owner needs to pick one.

- **(a) While a persona is loaded in the tab:** highlighting works whatever the sort, including after switching away from Best match. This is small, a few hours, and needs no new storage.
- **(b) After "Stop using it", or in a new tab:** this needs the reduced persona (the fields the ranking reads, never skills or notes) kept on the device. That would be an opt-in, **Remember my persona on this device**, using `localStorage`, with a Forget button. This is small too, but it changes the rule that the persona is kept for the tab only, so it needs the owner's approval.

**Recommendation:** build (a) now, and add (b) only if the owner wants it.

## Open questions for the owner

1. **Ranking:** does "rank the roles" mean the candidate's own order within My Roles (proposed here), or also a "how interested am I" mark on any board role that feeds back into the board?
2. **Statuses:** is the list above right? Is **Saved** (before applying) wanted, or Applied only?
3. **Storage:** is `localStorage`, on this device only, approved for My Roles?
4. **Great match:** (a) only, or (a) and (b)?
5. **The prompt on return:** in or out? It is the easiest route on phones.
