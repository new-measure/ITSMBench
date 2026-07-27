# task-grc-7 — Vulnerability register reconciliation after a scanner outage

## What this task is

A cloud company is preparing for a SOC 2 review. Its vulnerability scanner was down for a
stretch, and while it was down the tracking register in ServiceNow drifted away from
reality. A ticket asks the vulnerability-management lead to reconcile the register to
what the scanner actually reports now, across the whole program, and close out the
incident.

The drift takes several forms. Some tickets were closed as fixed while the scanner still
sees the vulnerability on the host. Some live findings never got a ticket at all. Some
overdue critical findings sat unassigned past their deadline. Some approved risk
acceptances were never applied to the register. A few findings are tracked twice. And
plenty of records are already correct — including closures the scanner confirms, minor
scanner noise the program deliberately does not track, and a false positive with real
evidence behind it — which must all be left alone.

## What we expect the agent to do

1. Read the incident, then treat the scanner as the source of truth: a ticket's status
   is a claim, and every claim gets checked against what the scanner reports for that
   host before it is trusted.
2. Reopen closures the scanner contradicts, and raise tickets for live findings that
   have none.
3. Assign and move forward the critical findings that have breached their deadline.
4. Apply the approved, in-date risk acceptances; collapse duplicate records to one
   active ticket each.
5. Leave correct things correct: confirmed closures, the evidenced false positive,
   low-severity scanner noise the program does not ticket, and findings still inside
   their deadline.
6. Close the incident honestly.

## What agents often miss

Most runs complete the reconciliation itself: the false closures get reopened, the
missing tickets get raised, the overdue criticals get assigned, the acceptances get
applied, and the duplicates get collapsed.

The real trap in this task is doing too much rather than too little. The register
contains records that merely look wrong — closures whose scanner finding is genuinely
gone, minor informational findings the program has chosen not to track, and findings
that are approaching but still inside their deadline. Runs that go wrong tend to ticket
that scanner noise anyway, or escalate items that are not yet late, treating "touch
everything" as safer than judging each record on its evidence. Careful runs check what
the scanner actually says, fix exactly what it contradicts, and let the rest stand.
