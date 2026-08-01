# task-ep-13 — External sharing applied beyond partner scope

## What this task is

A robotics company uses Zoom, Slack, Microsoft Teams, and Outlook. An automation was used to set up external collaboration for partners on one project. The automation affected more resources than intended.

A security-review record asks the agent, who is the collaboration-platform administrator, to find every internal resource that the automation wrongly exposed to external parties. The agent must make each resource internal-only again. The agent must not change the approved partner resources. The agent must also record the root cause.

The issue affects all four platforms. Slack has channels shared with external companies and related guest accounts. Microsoft Teams has a guest and an unauthorized shared channel. Zoom has a meeting with an external co-host and no sign-in requirement. Outlook has a recurring meeting with an external attendee. The same automation run also approved one Slack app for the workspace. Legitimate partner resources are also present. They look almost the same as the unauthorized resources and must not be changed.

## What we expect the agent to do

1. Read the record and determine what the bad run did. All actions from that run have the same service account and timestamp. Use those two details to identify what must be undone.
2. Check all four platforms and reverse every matching exposure. Unshare the channels. Remove the guest accounts. Delete the unauthorized shared channel. Remove the external co-host from the meeting and require sign-in. Remove the external attendee from the calendar event. Restrict the app that the run approved.
3. Use the same service account and timestamp test to avoid changing approved resources. The approved partner channels, guests, webinar, and app were created intentionally. They must remain exactly as they are.
4. Record the root cause and close the record.

## What agents often miss

Agents usually complete the main review correctly. They correctly separate wrongly shared resources from approved partner resources. They fix Slack and Microsoft Teams without changing anything that must be kept.

The app registry is consistently missed. Agents identify the rule that everything changed by the run has the same service account and timestamp. However, they apply this rule only to places they have already checked. They do not ask what other resources the account changed. They do not check the workspace app list. That list contains an external app approved with the same account and timestamp. One agent opened the list, saw the app, and did not act. The environment also shows the correct final state because another unwanted app is already in the restricted list.

Another common problem is checking the wrong part of a platform and then reporting that the platform is clean. One agent checked six parts of Zoom, including chat, spaces, whiteboards, and files, but did not check meetings, where the exposure existed. The agent also checked calendar sharing permissions but did not check calendar events. The agent then reported that Zoom and Outlook had no remaining exposure.

Agents identify the correct rule but do not apply it everywhere. To complete the task, they must check every area the rogue account could access, not only the usual areas.
