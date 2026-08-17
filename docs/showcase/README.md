# Interactive showcase

`openagentos-showcase.html` is a self-contained interactive page that replays six
production patterns from **real recorded runs** — audit trails, approvals,
rollbacks, and diffs pulled from the runtime's Postgres.

Regenerate with fresh data:

1. Run the demos (`apps.*.demo`) so Postgres holds recent runs.
2. Re-export `rundata.json` (see the query script in the session history) or edit it.
3. `python3 build.py` — assembles `openagentos-showcase.html` from
   `page.css` + `page.js` + the data.

Open the HTML directly in a browser, or publish it anywhere static.
