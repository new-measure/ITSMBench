# task-ep-9 — Overnight page that nobody answered

## What this task is

This is an on-call ticket at a payments company. A high-urgency page for the checkout API was not claimed for 47 minutes overnight. Merchants noticed the problem before the team did. The ticket asks the agent to complete all outstanding work related to the incident and find out how it happened.

The direct cause is easy to find. The checkout API still uses an obsolete escalation policy from an old team split. The page went to an engineer who moved to another team long ago. But there is also a deeper cause. After an alert storm the previous month, the team wrote a postmortem with cleanup actions. The actions were to reroute the service, add a backup escalation level, fix the on-call Slack group, re-enable a silenced service, and remove a temporary alert-suppression window. These actions were marked done, but they were not actually completed. All of these problems still exist. No record says this directly. The agent must compare the real system state with the claims in the tickets and follow-ups.

## What we expect the agent to do

1. Find why the page was not answered. The service uses a stale escalation policy instead of the staffed team rotation. Fix the routing.
2. Find out why the routing was still broken weeks after the team split. Locate the postmortem cleanup actions that were marked complete but were never finished.
3. Check every claimed cleanup item against the real system state. Complete all unfinished items. Add the missing backup escalation level. Point the on-call Slack group to the current on-call engineer. Re-enable alerting on the silenced service. Remove the remaining suppression window that is still muting a payments database.
4. Change nothing else. Do not change other teams' policies, schedules, groups, open incidents, a valid future maintenance window, or the postmortem records.
5. Resolve the incident that triggered the ticket. Close the ticket with an accurate explanation of what happened.

## What agents often miss

Agents usually find and fix the direct cause. Every run correctly finds the stale routing, points the service to the right policy, confirms that the rotation is staffed, resolves the incident, records a clear root cause, and closes the ticket. They also avoid changing anything unrelated.

But they miss the deeper problem. After finding that the service still used the old policy, no run asks why it was still using that policy six weeks after the team split. They do not read the postmortem follow-ups and tickets. Those records say that the required fixes were complete, even though the fixes were never made. As a result, the silenced service remains silenced. The suppression window continues to mute the database. The on-call Slack group still pages the engineer who left the team. The backup escalation level is also usually still missing. One run added the backup level after finding an unused secondary rotation. This shows that the missing level can be found without reading the postmortem. However, no run completed every cleanup item.

The repeated problem is that agents stop after finding a correct and convincing root cause. Sometimes the evidence is already present in information they retrieved. For example, a full service list may show that a payments service is disabled, but the agent does not act on it. Agents diagnose the direct cause correctly. They fail to use that diagnosis as a reason to check every cleanup item that was claimed to be complete.
