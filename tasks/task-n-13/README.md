# task-n-13 — Internal apps unreachable, working fine from outside

## What this task is

A P1 incident says corporate users cannot reach a range of internal apps, while
the same apps work fine from outside the company. The incident blames the
previous evening's app deploy. The deploy is a decoy — it changed no DNS and no
network. The real cause is an overnight DNS migration that closed as "successful,
validation deferred" and quietly broke the company's internal name resolution.

The company runs split-horizon DNS: an internal view for staff and an external
view for the public. The migration damaged the internal view in several ways at
once — some app records are missing entirely, some resolve to the wrong address,
some point at hosts that no longer exist, aliases still chain through a retired
domain, and a whole sub-zone is delegated to dead nameservers. The reason the
apps work from outside is that the external view was never touched, which makes
the "it works out there" symptom misleading rather than helpful.

## What we expect the agent to do

1. Confirm the blamed deploy is not the cause and move on.
2. Recognise the split-horizon design: internal and external views differ on
   purpose, so "works from outside" is expected, not a clue that DNS is fine.
3. Restore internal resolution across every broken form: create the missing app
   records at their live internal address, repoint the ones aimed at the wrong or
   a dead address, fix the aliases that still chain through the retired domain,
   and repoint the sub-zone delegation to the live nameservers.
4. Remove the genuinely dangling records that point at nothing.
5. Leave the external view alone, leave the services that legitimately have no
   internal record alone, and leave the healthy peer records alone.
6. Resolve the incident.

## What agents often miss

Runs split sharply on this one. The strongest work the whole chain — they reject
the decoy, restore the missing app records, repoint the aliases off the retired
domain, fix the delegation, and clear the dangling records. Weaker runs stall
early instead: they investigate at length and then write almost nothing, leaving
internal resolution broken across the board.

What makes it hard is that the damage is spread across record types that do not
cross-reference each other. The direct app records are only the first layer;
behind them sit aliases chaining through a retired domain and a sub-zone
delegated to dead nameservers, and neither shows up while you are looking at the
first layer. Each is discoverable from the healthy peer records, which show what
a working entry looks like — but only if a run keeps going after the obvious
records resolve again.

The other recurring slip is the close-out: marking the incident with a status
label instead of the value the system actually stores, so it reads as done
without ever reaching a closed state.

In short: the diagnosis is the easy half. Carrying the repair through every layer
of the name estate — and finishing the paperwork correctly — is what separates a
complete run from one that looks busy.
