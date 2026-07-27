# task-ep-10 — Release that lied

## What this task is

A release engineer at Orbitware gets escalated Jira ticket **RLY-2301**: a customer upgraded to Relay 4.7.0 and says a claimed CSV formula-injection security fix is still broken. The ticket floats a false lead (maybe it was caught in a rollback) and asks the agent to make it right and check what else in the 4.7.0 notes cannot be trusted.

Release automation had cut 4.7.0 from Jira metadata while the release manager was out: it marked every `4.7.0`-tagged issue Done and published notes from that list. Four of the eight claimed fixes really shipped. Four did not — one PR approved but never merged (the disputed security fix), one merged then reverted, one merged after the cut, and one never built at all. A ninth real fix shipped in the window but is filed under a stray unreleased Jira version named `4.7`, so it is missing from both the notes and the 4.7.0 issue list.

## What we expect the agent to do

1. Investigate RLY-2301 and reject the rollback false lead where the evidence says otherwise.
2. Actually merge the approved, CI-green security PR — not just edit Jira/Confluence records.
3. Ship a patch release for the fixes that are now (or later) real: released Jira version, published GitHub release, and patch notes that document them.
4. Correct the lying 4.7.0 notes and issue states: remove false claims, reopen/detag the never-shipped items, and surface the stray-version fix that did ship.
5. Leave alone the four true fixes, the bad “reland” PR (changes-requested + failing CI), older releases, and noise records.
6. Close the trigger once the customer-facing fix is actually shippable.

## What agents often miss

Agents usually diagnose the release well: they find which claimed fixes are real, merge the disputed security PR, reopen the reverted / never-built items, avoid merging the bad reland PR, and correct a lot of the notes.

Where they fall short is finishing the ship:

- Nearly every run merges the security fix into `main` but never publishes a patch release (no released Jira version, no GitHub release, no patch notes). The customer stays on vulnerable 4.7.0 — a live exposure, not paperwork.
- Because they know they have not shipped, they often leave RLY-2301 In Progress on purpose.
- The stray-version fix (RLY-2172 under `4.7`) is a secondary miss: some runs find it, some never retag it into 4.7.0 / the notes.

In short: “PR merged” looks done; “fix actually shipped to the customer” is the hard part, and that is what most trials miss.

Full calibration detail lives in `workspace/CALIBRATION.md`.
