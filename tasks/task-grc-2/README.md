# task-grc-2 — Vendor register review before board sign-off

## What this task is

The CISO at a logistics software company creates a ticket before next week's board risk-committee meeting. The third-party vendor register is about to be signed off. It must be accurate.

The agent is the vendor-risk manager and is responsible for the entire register. This includes every vendor, its risk rating, its security assessments, its findings, and its actual access.

Most of the register is green, and most entries are accurate. However, it contains these problems:

- Five vendors failed their most recent security review but are still recorded as approved.
- Five vendors are recorded as clean even though each has an open high-severity finding.
- Four vendors have live access to company systems but have no security diligence on file.
- Four vendors are months overdue for reassessment.

Some vendors may look suspicious but must not be changed:

- One vendor was recently reviewed again and passed.
- One vendor has a formally accepted and documented risk.
- One vendor is archived.

These vendors must be left exactly as they are.

## What we expect the agent to do

1. Read the ticket and review the entire register. Review every vendor, not only the vendors named in the ticket or those that appear problematic.
2. Check every recorded status against the supporting information. Review the actual assessments, findings, and access held by each vendor. Do not assume that a green status is accurate.
3. Correct the records for vendors whose latest review failed. They must no longer be shown as fully approved.
4. Ensure that no vendor with an open high-severity finding is shown to the board as clean and approved.
5. Record vendors with live access and no diligence as risks. Also address overdue reassessments by flagging them or genuinely rescheduling them.
6. Do not change healthy vendors. This includes the re-approved vendor, the accepted-risk vendor, the archived vendor, and all vendors that are current and low-risk.
7. Close the ticket after the register is accurate and reliable.

## What agents often miss

Incomplete runs usually follow the same pattern. They identify and correct the clearly false records where a vendor failed its review but is still approved. They correctly leave all exception vendors unchanged. They then close the ticket. However, they describe the remaining risks without updating the register.

A vendor with an open high-severity finding remains recorded as clean and approved because the finding is already visible to anyone who reviews the details. Vendors with live access and no diligence are mentioned in the closing summary, but their register entries are not changed. Overdue reassessments are described as requiring another review, but they remain overdue.

The written explanation is accurate, but the register still gives the board the old information.

The recorded state is the required deliverable. The board signs off on the register, not the ticket comment. If a risk appears only in written comments, the board may miss it during sign-off.
