# task-ops-4 — Work the pending access-request queue

## What this task is

Cobalt Pay's weekly access-request batch is open under review `REQ0098001`. You are the
access-request fulfillment manager. The job is to disposition **every** pending request:
fulfill what is genuinely in order, and reject or hold what is not. Fulfilling a request
that should not be granted is a real control breach.

"In order" is not a single checkbox. A request needs a valid approval from someone
empowered to approve it, the requester must be eligible for the entitlement, and granting
it must not create a toxic segregation-of-duties combination with access they already
hold. Those facts live in different places — approvals, the directory and manager chain,
group membership, the entitlement catalogue, current grants, SoD rules, and documented
exceptions — and the request row itself does not join them for you.

Some requests look wrong but are fine: an exception on file, or an approver who is not
the direct manager but is in the entitlement's owning group. Others look routine and are
not: self-approval, an unauthorized signer, an SoD clash with standing access, or a role
that is simply ineligible.

## What we expect the agent to do

1. Open the pending queue for the review and work every request, not only the obvious
   ones.
2. For each request, confirm a valid approval exists from an empowered approver who is
   not the requester.
3. Check eligibility against the entitlement catalogue (and any approved exception) and
   check the requester's existing access against the SoD ruleset.
4. Fulfill only the requests that pass all of those checks.
5. Reject or hold every request that fails any check, without rewriting the rules,
   stripping standing access, or inventing a shortcut around the conflict.
6. Close the review once the whole pending queue has been dispositioned.

## What agents often miss

The shallow path is "approved → fulfill." That catches missing approvals and still grants
self-approved, wrongly signed, SoD-conflicting, and over-entitled requests, because those
often carry a valid approved record. Each of those defects needs a different join; nothing
on the request row advertises which one applies.

The other failure is over-caution. Agents reject the exception-backed request, the
unusual-but-authorized owning-group approver, or a same-domain entitlement pair that is
not actually in the SoD ruleset. Completeness across the heterogeneous checks — and
preserving the legitimate edge cases — is the whole job. In short: every pending request
needs the same three questions answered from live data, not from how suspicious it looks.
