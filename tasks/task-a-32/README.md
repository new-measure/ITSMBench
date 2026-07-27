# task-a-32 — Identity Administrators access audit

## What this task is

A routine-looking ticket asks the IT support agent to audit the members of the
Identity Administrators group and remove any admin access that is not legitimately
authorized. No policy, runbook, or list of names says what "legitimate" means —
that has to be worked out from the environment itself.

The real story is a chain. An employee left the company, but an offboarding gap
left their account active. That account granted admin access to one person, who
granted it to others, who granted it further — four levels deep. The identity
log holds every grant, and a small register records which admins were set up
legitimately at the start. Tracing any member's chain of grants ends in one of
two places: the legitimate root, or the terminated account. While they had
admin, the illegitimate accounts also created things — two service accounts, an
app, and a privileged group stuffed with members — none of it approved anywhere.
A closed incident from months earlier shows how the same kind of cleanup was
handled before.

## What we expect the agent to do

1. Not take the group list at face value: trace each member's grant back through
   the log until it reaches the legitimate root or the terminated account.
2. Remove admin access from everyone whose chain traces to the terminated
   account, at every depth — and keep everyone whose chain is clean.
3. Notice the terminated employee is still active in the identity system and
   shut that account down.
4. Ask what else the illegitimate accounts did with their access: find the
   service accounts, the app, and the group they created, and disable or remove
   each one — without touching the ordinary user accounts that were put into
   that group.
5. Record the decisions and close the ticket.

## What agents often miss

Finding and removing the illegitimate admins is usually done well: agents read
the grant log, build the chain, and clear all four levels while sparing the
legitimate members.

Where runs have fallen short is everything past the membership list. The
terminated account itself gets left active — the audit is about the group, so
the account behind the whole problem escapes notice. And almost no run asks the
follow-up question: what did these accounts create while they had admin? The
rogue service accounts keep running, the app stays enabled, and the stuffed
group keeps its access, because the cleanup stopped at "remove the bad members"
instead of "undo what the bad members did."

In short: revoking access is the easy half; sweeping up what the revoked
accounts left behind is what separates a complete run from a partial one.
