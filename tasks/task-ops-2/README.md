# task-ops-2 — Drive a checkout outage to true root cause

## What this task is

Meridian Pay's monitoring opened problem `PRB0041001`: customers cannot complete
checkout. The configuration item named on the problem looks healthy on its own. Whatever
broke checkout sits somewhere in what that service **depends on**, and the outage has
already rippled out to everything that **depends on** it.

This is a root-cause and footprint task, not a board-wide cleanup. A flat look at changes
and incidents on the named service is misleading: there is a recent deploy on checkout
itself that looks tempting but does not line up with when the outage began. The real
cause is upstream in the dependency graph. The full set of related incidents is
downstream — including services several hops away that only fail because checkout failed
under them.

## What we expect the agent to do

1. Trace the affected service's CMDB dependencies upstream and find the change whose
   timing and CI actually explain the outage — not the decoy change on checkout itself.
2. Point the problem's investigation at that root-cause change.
3. Walk the dependency graph downstream and find every open incident that is this same
   outage across the affected service and its dependents.
4. Attach each of those incidents to `PRB0041001` and close them as duplicates; leave
   unrelated lookalikes, other problems' children, and pre-outage tickets alone.
5. Advance the problem out of its initial state and record it as a known error.

## What agents often miss

The usual incomplete RCA stops at the front door. Agents query changes on the named
checkout CI, link the recent deploy, and close a handful of same-CI incidents. That
answers the ticket the problem was opened with, but it is the wrong cause and an
incomplete footprint.

Recovering the rest requires both directions of the graph: upstream for the change that
fits the onset window, and a full transitive walk downstream for incidents that only
appear on kiosks, SDKs, partner checkouts, and other dependents. Stopping after one hop
leaves several true children unlinked. Sweeping by symptom text without the graph pulls
in the wrong problem's tickets or older same-CI noise. In short: the named service is the
symptom; the dependency map is the investigation.
