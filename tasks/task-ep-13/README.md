# task-ep-13 — External sharing applied beyond partner scope

## What this task is

A robotics company runs Zoom, Slack, Microsoft Teams, and Outlook. To onboard partners
for one project, an automation applied external-collaboration settings — but it ran
wider than intended. A security-review record asks the agent, the collaboration-platform
administrator, to find every internal resource the run wrongly exposed to outside
parties, put each one back to internal-only, leave the sanctioned partner resources
alone, and record the root cause.

The damage is spread across all four platforms: Slack channels shared with outside
companies and their guest accounts, a Teams guest and an unauthorized shared channel, a
Zoom meeting with an external co-host and no sign-in requirement, a recurring Outlook
meeting with an outside attendee — and one Slack app the same run approved into the
workspace. Sitting next to all of it are the legitimate partner resources, which look
almost identical and must not be touched.

## What we expect the agent to do

1. Read the record and work out what the bad run actually did. Its actions all carry
   the same service account and the same timestamp — that is the test for what to undo.
2. Sweep all four platforms and revert every exposure that matches: unshare the
   channels, remove the guest accounts, delete the unauthorized shared channel, strip
   the external co-host and require sign-in on the meeting, remove the outside attendee
   from the calendar event, and restrict the app the run approved.
3. Use the same test to spare things: the sanctioned partner channels, guests, webinar,
   and app were set up on purpose and must stay exactly as they are.
4. Record the root cause and close the record.

## What agents often miss

The core sweep goes well. Runs correctly separate the wrongly-shared resources from the
sanctioned partner ones, fix Slack and Teams cleanly, and never harm anything that
should be kept.

The consistent miss is the app registry. Runs state the rule themselves — "everything
this run touched carries its service account and timestamp" — but only apply it to the
places they have already looked. Nobody asks what else the account touched. The
workspace app list, where the run approved an outside app under exactly that account
and timestamp, goes unchecked; one run even had the list open, saw the app, and moved
on. The world also shows what the right end-state looks like: another unwanted app is
already sitting in the restricted list.

A second pattern is checking the wrong surface and declaring the platform clean. One
run audited six corners of Zoom — chat, spaces, whiteboards, files — but never the
meetings, where the real exposure was, and reviewed calendar sharing permissions but
never the events, then reported both platforms had no outstanding exposure.

In short: agents find the rule but do not finish applying it; auditing every surface
the rogue account could reach — not just the familiar ones — is what separates a full
solve from a near miss.
