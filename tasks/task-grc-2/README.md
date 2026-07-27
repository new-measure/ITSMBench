# task-grc-2 — Vendor register review before board sign-off

## What this task is

The CISO at a logistics software company files a ticket ahead of next week's board
risk-committee meeting: the third-party vendor register is about to be signed off, and
it needs to be actually true. The agent is the vendor-risk manager and owns the whole
register — every vendor, its risk rating, the security assessments behind it, the
findings raised against it, and the access it really holds.

The register looks mostly green, and most of it honestly is. Behind the green, though:
five vendors whose most recent security review failed are still recorded as approved;
five more are recorded as clean while carrying an open high-severity finding; four hold
live access to company systems with no security diligence on file at all; four are
months overdue for reassessment. Mixed in are vendors that only look suspicious — one
was recently re-reviewed and passed, one has its risk formally accepted and documented,
one is archived — and they must be left exactly as they are.

## What we expect the agent to do

1. Read the ticket and review the whole register — every vendor, not just the ones
   named or the ones that look bad.
2. Verify each recorded status against what stands behind it: the actual assessments,
   the findings, and the access the vendor really holds. A green status is a claim,
   not a fact.
3. Correct the record for the vendors whose latest review failed — they must no longer
   read as cleanly approved.
4. Make sure no vendor with an open high-severity finding is presented to the board as
   a clean approved vendor.
5. Put vendors with live access and no diligence on the record as a risk, and deal
   with the overdue reassessments — flag them or genuinely reschedule them.
6. Leave the healthy vendors alone: the re-approved one, the accepted-risk one, the
   archived one, and everyone current and low-risk.
7. Close the ticket once the register is trustworthy.

## What agents often miss

Runs that fall short show one consistent shape. They find the outright falsified
records — failed review, still approved — and fix those correctly. They spare every
trap vendor. They close the ticket. And then they describe the rest of the risk
instead of recording it.

A vendor carrying an open high finding stays recorded as clean-approved, on the
reasoning that the finding is "already visible" to anyone who looks. Vendors with live
access and no diligence get a sentence in the closing summary but no change in the
register. Overdue reassessments are "noted for re-review" and left overdue. The
write-up is accurate; the register still tells the board the old story.

The gap is treating the recorded state as the deliverable. The board signs the
register, not the ticket comment — a risk that is only in prose is a risk the sign-off
will miss.
