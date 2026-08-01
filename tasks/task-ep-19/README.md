# task-ep-19 — Coverage monitor page: a host missing from detection scope

## What this task is

An on-call detection engineer at a payments company gets paged overnight. The coverage monitor says a production host is missing from the monitored scope. This page is a false alarm. The host was retired months ago and replaced. A leftover record in a security tool caused the monitor to report it.

There is a larger problem. Over several days, one person reduced detection coverage in four different places. Live hosts were removed from the monitored group. One sensor was hidden. A branch egress-logging rule was disabled. A host's coverage check was suppressed. An active threat indicator was marked expired. Each bad change looks similar to a legitimate change. One disabled rule was replaced by a newer version. Some checks are disabled for hosts that were actually retired. Some indicators really did expire. The agent must use evidence to tell the bad changes from the legitimate ones. It must not change everything at once.

## What we expect the agent to do

1. Identify the paged host as retired and leave it retired.
2. Add the live production hosts back to the monitored group. Unhide the hidden sensor. The monitored scope must exactly match the live fleet.
3. Find out who made the change and when it was made. Use that information to find everything else the same account changed during the same time window. Check every security tool, not only the tool that sent the page.
4. Fix the related changes. Re-enable the logging rule that has no replacement. Remove suppression from the coverage check for the live host. Reactivate the threat indicator because its expiry date is still in the future and its campaign is still active.
5. Do not change the legitimate look-alikes. Keep the replaced rule disabled. Keep retired hosts deactivated. Keep genuinely expired indicators expired. Do not contain or hide any host that should not be contained or hidden.
6. Resolve the page and give an accurate account of what happened.

## What agents often miss

Agents usually fix the host-scope issue correctly. They identify the false alarm, restore the group membership, unhide the sensor, avoid changing the legitimate look-alikes, and close the incidents.

However, they often fail to use the root cause they found. The final report includes both the account that made the change and the date of the change. Agents then fail to check what else that account changed. They do not investigate the disabled logging rule or the expired-but-active threat indicator. The suppressed coverage check requires one additional query. By default, the check list shows only failing items. The agent must directly request the suppressed check.

In short, agents completely fix the tool that sent the page. They fail to use the "who and when" information to investigate the other detection tools.
