# task-ep-2 — Access review flags: January leavers with active access

## What this task is

A quarterly access review finds two people who left in January but may still have access.

A helpdesk ticket asks the agent to investigate both people. The agent must complete any work that is still outstanding and find out how the problem happened.

One case is a false positive. The person was offboarded correctly. He later returned as an approved contractor and used the same email address. His current access is valid.

The other case is a real problem. The offboarding automation suspended his account and then stopped before finishing.

The ticket is part of a larger problem. A group of people left the company on the same day. The automation processed them one at a time. It failed before it finished the full group. As a result, several people still have access in systems that the automation did not finish updating. The remaining access includes an active Google account, OAuth tokens, GitHub repository access, and Slack memberships.

One person who left never received an offboarding ticket. Another person has no account in the identity system, so the problem appears only in the other services.

No source explains the full problem directly. The agent must work it out by comparing HR records, the identity event log, and each service's admin API.

## What we expect the agent to do

1. Investigate both people named in the ticket. Identify that the returned contractor has valid access and do not change his access.
2. Fully complete the stalled offboarding for the named leaver.
3. Find the real root cause. A batch offboarding run stopped before completion and left work unfinished in other systems.
4. Act on the root cause instead of only reporting it. Get the complete list of people who left on the same day from HR. Check every person in every system: identity, Google Workspace, GitHub, and Slack. Complete every missing action for each person. This includes disabling accounts, revoking sessions, removing OAuth tokens, removing repository and organization access, and removing workspace memberships.
5. Do not change anything that is already correct. This includes the contractor, the leaver whose offboarding was already fully completed, service accounts, shared accounts, unrelated people, other tickets, and the read-only HR system.
6. Close the ticket with an accurate account of what happened and what was done.

## What agents often miss

Agents usually make the correct decisions about the two named people. Every run identifies the false positive and leaves the contractor unchanged. Every run also completes the named leaver's offboarding in the identity system, identifies the stalled automation as the root cause, and closes the ticket without affecting unrelated people.

However, every run misses that the root cause means other people were also affected. The full list of leavers is in the HR response that the agent already retrieved. Agents filter this list to the two people named in the ticket and ignore everyone else.

The identity event log shows a batch run that processed several people and stopped before completion. Agents do not check who came after the failure point in the queue. They also do not check what remained unfinished in systems not covered by that log.

Agents usually do not open Google Workspace or Slack, even though the search index provides their admin APIs. They check one person in one system, see no problem there, and incorrectly assume that every system is clean for the full group.

The main failure is that the investigation stays limited to the people named in the ticket. Agents must use the root cause to identify the full affected batch and check every person in that batch.
