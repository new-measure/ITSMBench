# task-n-14 — Botched tuning push on the API edge tier (not a capacity problem)

## What this task is

A P1 incident reports that the customer API refuses some connections and drops others during normal load. The customer web service works normally. The on-call wrote in the ticket that the API pool may not have enough capacity or that one member may be faulty. The on-call asks whether to add hardware. That theory is wrong.

An overnight "capacity and health-check tuning" change was applied only to the API edge tier. It left all four API pools with several types of incorrect settings. The web tier was not part of the change and still has the normal values. The correct settings are therefore available in the environment and do not need to be invented. The task is to disprove the reported cause, restore all changed settings, return the incorrectly parked members to service, and resolve the incident. Do not add capacity. Do not change the state of the one member that is deliberately out of service.

## What we expect the agent to do

1. Read the incident. Then check the change records and the host inventory before making any changes. The hosts are healthy. A recent tuning change applies to exactly the affected tier. This shows that the problem is configuration, not hardware.
2. Determine the normal profile by comparing the API tier with the unchanged web tier and the API members that were not modified. Identify the correct front-door limit, per-member limit, weight, health-check interval, failure count, and balancing method.
3. Repair every changed setting across all four API pools:
   - Restore the front end's connection limit. It was set much too low and is refusing new connections.
   - Restore members that were set to weight zero. A weight of zero prevents them from receiving traffic.
   - Restore members whose own connection limit was set very low. This causes connection resets under load.
   - Restore members whose health checks were made too aggressive. This causes healthy members to move in and out of service.
   - Turn health checking back on for members where it was disabled.
   - Restore pools that were changed to a balancing method that does not distribute traffic. The incorrect method sends all traffic to one member while the other members remain idle.
4. Fix both the stored configuration and the live state. Several members were left drained or in maintenance and must be returned to service. Some of these members also have one of the configuration faults listed above, so both problems must be fixed.
5. Leave the one member that was drained for approved host maintenance in its current state. The change record and the inventory both show that this maintenance work is still open.
6. Resolve or close the incident. Record the actual cause of the problem.

## What agents often miss

Agents usually make the correct initial decision. They read the ticket's capacity theory, check the hosts, confirm that the hosts are healthy, and do not add hardware or replace a member. They also identify the approved maintenance drain and leave that member out of service.

The common problem is incomplete coverage. The damage is different across the pools. Different pools have different faults, and some members have two faults at the same time. A member can have a correct stored configuration but still be parked out of rotation in the live state. The service remains broken if an agent checks only one pool, only one type of fault, or only the stored configuration.

Agents also often spend too much time looking for an authoritative source that does not exist. They search for a configuration backup, a knowledge article that defines the standard profile, a change audit log, or a repository containing the old file. None of these exists. The only baseline is the peer tier and the API members that the change did not modify.

The final risk is making unnecessary changes. Do not raise limits above the normal fleet values. Do not return the approved maintenance member to service. The correct fix is the smallest change that restores the known-good profile.
