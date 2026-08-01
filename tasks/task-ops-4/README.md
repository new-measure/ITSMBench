# task-ops-4 — Work the pending access-request queue

## What this task is

Cobalt Pay's weekly batch of access requests is ready for review under `REQ0098001`. You are the access-request fulfillment manager. You must make a decision on every pending request. Fulfill requests that meet all requirements. Reject or hold requests that do not. Granting access when it should not be granted is a real control breach.

A request must meet several requirements. It must have valid approval from someone who has authority to approve it. The requester must be eligible for the entitlement. The entitlement must not create a prohibited segregation-of-duties combination with access the requester already has. The required information is stored in several places. These include approvals, the directory and manager chain, group membership, the entitlement catalogue, current grants, SoD rules, and documented exceptions. The request row does not connect this information for you.

Some requests may look invalid but are valid. A valid exception may be on file. An approver may not be the requester's direct manager but may belong to the group that owns the entitlement. Other requests may look normal but are invalid. Examples include self-approval, approval by someone without authority, an SoD conflict with existing access, or a requester whose role is not eligible.

## What we expect the agent to do

1. Open the pending queue for the review. Process every request, not only the obvious ones.
2. For each request, confirm that a valid approval exists. The approver must have authority to approve the request and must not be the requester.
3. Check whether the requester is eligible under the entitlement catalogue and any approved exception. Check the requester's existing access against the SoD ruleset.
4. Fulfill only requests that pass all of these checks.
5. Reject or hold every request that fails any check. Do not change the rules, remove existing access, or create a shortcut to bypass a conflict.
6. Close the review after every request in the pending queue has received a decision.

## What agents often miss

A common mistake is to treat every approved request as ready to fulfill. This identifies missing approvals but can still grant requests that were self-approved, approved by someone without authority, conflict with SoD rules, or exceed the requester's eligibility. These requests often have an approved record. Each problem requires checking different information. The request row does not show which problem exists.

Another mistake is being too cautious. Agents may reject a request supported by an exception, a request approved by an unusual but authorized member of the owning group, or two entitlements in the same domain that are not actually prohibited by the SoD ruleset. You must complete all different checks while allowing valid exceptions and unusual but valid cases. Every pending request must be checked against the same three requirements using current data. Do not base the decision on how suspicious the request looks.
