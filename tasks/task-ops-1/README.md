# task-ops-1 — End-of-shift handoff on a chaotic incident board

## What this task is

An overnight wave left Northwind Pay's service desk in a mess. You are the duty manager
handing the desk to the next shift, and the job is to leave the **entire** open board
coherent — not only the headline outage. Monitoring has already opened problem
`PRB0040100` for the emerging major issue; dozens of similar-looking tickets sit around
it, many mislabeled, mistagged, or parked with the wrong team.

The hard part is that "same outage" is not a single field. Some true children sit on the
broken service, others on services that depend on it (including through more than one
hop in the CMDB), and a few only share a monitoring correlation id because their CI was
typed wrong or left blank. Nearby tickets look related — same wording, same service at
the wrong time, a separate reporting outage with its own problem — but are not this
incident. Routing and priority are also wrong across the board: keyword auto-assignment
dropped tickets with the wrong support group, and at least one business-critical breach
is still sitting at a routine priority.

## What we expect the agent to do

1. Identify which open incidents are the same underlying outage as `PRB0040100`, using
   the CMDB dependency graph, timing, and correlation signals — not keyword similarity.
2. Attach those incidents to the problem and close them as duplicates; leave lookalike
   tickets and unrelated clusters alone.
3. Point the problem's investigation at the change that actually caused the outage, and
   advance the problem out of its initial state.
4. Re-route every open ticket whose assignment group does not match the support group of
   its affected configuration item.
5. Raise priorities where real business impact and breached service commitments demand
   it — especially a critical service whose resolution SLA has already breached.

## What agents often miss

Agents usually find the obvious payment-auth children and link a plausible change. The
common incomplete close is cluster membership: they stop at the named CI, miss dependents
reached only through a multi-hop CMDB path, or drop the dirty tickets that only join via
the shared correlation id. The opposite failure is over-merge — folding in the reporting
distractor cluster, older same-CI tickets from before the window, or keyword landmines
that merely say "payment."

Even when the outage is handled, board-wide work gets skipped. Runs treat the handoff as
major-incident triage only and leave mis-routed tickets and the SLA-breach priority as
they found them. Change attribution is another trap: the tickets often blame an app
deploy, but the change that lines up with the onset is the signing-cert rotation on the
auth service. In short: consolidating the headline outage is not enough; the board has
to be coherent when the next shift sits down.
