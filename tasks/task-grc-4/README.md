# task-grc-4 — Certification campaign says done; the access says otherwise

## What this task is

A payments company has just finished its quarterly certification of privileged access.
Every reviewer submitted their decisions and the campaign platform shows the campaign as
complete. Ahead of audit fieldwork, a ticket asks the access-certification manager to
make sure the environment genuinely reflects what the campaign decided.

The catch is that a recorded decision is not an enacted decision. Across the campaign's
review instances, many "remove" decisions were written down but never carried out: denied
admin roles, privileged group memberships, and application assignments are all still live
in the identity provider, and two entitlement packages that reviewers voted to restrict
are still open to every employee. One review really was fully applied — the platform's
status is true for some things and false for others, so each decision has to be checked
against live access, not against the campaign's own bookkeeping.

## What we expect the agent to do

1. Read the ticket and work out the campaign's full scope: every review instance and
   every decision in it.
2. Verify each decision against the live system it governs instead of trusting the
   recorded status.
3. Enact every decision that was recorded but never applied: remove the denied admin
   roles, group memberships, and application assignments.
4. Carry out the restriction decisions properly: narrow who the two entitlement
   assignment policies allow, so the packages are genuinely limited — not merely hidden
   or relabeled.
5. Leave approved and out-of-scope access exactly as it is.
6. Close the ticket with an honest record of what was found and fixed.

## What agents often miss

Most runs handle the core well: they refuse to take the campaign status at face value,
sweep all the review instances, find the decisions that were never enacted, and cleanly
remove the denied roles, groups, and app assignments without touching approved access.

The recurring stumble is the restriction decision. Removing access is a familiar
operation with an obvious API; genuinely restricting an entitlement is not. A run may
hide the entitlement package from the catalog and report it "restricted" — but the
assignment policy underneath still allows every member of the company, so nothing about
who can get the access actually changed. The decision was acted on, just on the wrong
surface, and the run's own summary claims success. Verifying the specific field the
decision governs — who is allowed, not how visible the package is — is what separates a
complete closeout from a nearly complete one.
