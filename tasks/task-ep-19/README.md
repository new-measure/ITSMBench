# task-ep-19 — Coverage monitor page: a host missing from detection scope

## What this task is

The on-call detection engineer at a payments company gets paged overnight: the
coverage monitor says a production host is missing from the monitored scope. The paged
host is a false alarm — it was retired months ago and replaced, and only its leftover
security-tool record made the monitor complain.

The real problem is wider. Over a few days, one person quietly turned detection down
in four different places: live hosts were removed from the monitored group, one sensor
was hidden, a branch egress-logging rule was disabled, a host's coverage check was
suppressed, and an active threat indicator was marked expired. Each bad change sits
next to a legitimate look-alike — a rule that is off because a newer version replaced
it, checks that are off for genuinely retired hosts, indicators that really did expire
— so telling them apart takes evidence, not a bulk sweep.

## What we expect the agent to do

1. Recognize the paged host as retired and leave it retired.
2. Put the live production hosts back in the monitored group and unhide the hidden
   sensor, so scope exactly matches the live fleet.
3. Ask who made the change and when — then use that answer: check what else the same
   account changed in the same window, in every security tool, not just the one that
   paged.
4. Fix what that turns up: re-enable the logging rule that has no replacement,
   un-suppress the coverage check for the live host, and reactivate the threat
   indicator whose expiry date is still in the future and whose campaign is still
   active.
5. Leave the look-alikes alone: the replaced rule stays off, retired hosts stay
   deactivated, genuinely expired indicators stay expired, and no host gets contained
   or hidden that shouldn't be.
6. Resolve the page with an honest account.

## What agents often miss

The host-scope work goes well. Runs spot the false alarm, restore the group
membership, unhide the sensor, avoid every look-alike trap, and close the incidents.

What they miss is using their own root cause. Both the account that made the change
and the date appear in the run's final report — and then nobody asks what else that
account touched. The disabled logging rule and the expired-but-active threat indicator
are never looked at. The suppressed coverage check is one query away: the check list
only shows failing items by default, and the suppressed one has to be asked for
directly.

In short: the tool that paged gets fixed completely; carrying the "who and when" into
the other detection tools is what every run so far has missed.
