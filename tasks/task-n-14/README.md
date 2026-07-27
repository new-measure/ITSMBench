# task-n-14 — Botched tuning push on the API edge tier (not a capacity problem)

## What this task is

A P1 incident says the customer API keeps refusing some connections and dropping
others under normal load, while the customer web service is fine. The on-call's
theory, written into the ticket, is that the API pool is under-provisioned or that a
member has gone bad, and asks whether to add hardware. That theory is the trap.

An overnight "capacity and health-check tuning" change was applied to the API edge
tier only, and it left the four API pools full of wrong settings of several kinds.
The web tier was out of scope and still carries the normal values, so the correct
settings are visible in the environment rather than something to invent. The job is
to disprove the reported cause, restore what drifted, put the wrongly parked members
back in service, and resolve the incident — without adding capacity and without
disturbing the one member deliberately out of service.

## What we expect the agent to do

1. Read the incident, then check the change records and the host inventory before
   touching anything. The hosts are healthy and a recent tuning change covers exactly
   the affected tier, so this is configuration, not hardware.
2. Work out the normal profile by comparing the API tier with the untouched web tier
   and with the API members left alone: front-door limit, per-member limit, weight,
   health-check interval and failure count, and balancing method.
3. Repair every drifted setting across all four API pools:
   - the front end's connection limit, set far too low, refusing new connections;
   - members left at weight zero, which take no traffic;
   - members whose own connection limit is tiny, resetting connections under load;
   - members whose health checks are so aggressive that healthy members flap;
   - members with health checking switched off entirely;
   - pools switched to a non-distributing balancing method, so one member absorbs
     everything while its siblings idle.
4. Fix the live state as well as the stored configuration: several members were left
   drained or in maintenance and must be returned to service, and some of them also
   carry one of the faults above, so both halves need fixing.
5. Leave the one member drained for approved host maintenance where it is. The change
   record and the inventory both say that work is still open.
6. Resolve or close the incident and write down what was actually wrong.

## What agents often miss

The judgment call goes well. Runs read the ticket's capacity theory, check the hosts,
find them healthy, and refuse to add hardware or replace a member. They also spot the
approved maintenance drain and leave it alone.

What costs runs is breadth. The damage is deliberately uneven: different pools carry
different faults, some members carry two at once, and a member can look healthy in the
stored configuration while still being parked out of rotation in the live state.
Checking one pool, or one kind of fault, or only the configuration, leaves the service
broken.

A recurring time sink is hunting for an authoritative answer that does not exist. Runs
search for a configuration backup, a knowledge article with the standard profile, a
change audit log, or a repository holding the old file. None of that is there. The
only baseline is the peer tier and the members the change did not mangle.

The last trap is over-correction: raising limits far past the fleet norm, or pulling
the sanctioned maintenance member back into service, is not a stronger fix. Least
change back to the known-good profile is the answer.
