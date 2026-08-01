# task-ops-2 — Drive a checkout outage to true root cause

## What this task is

Meridian Pay's monitoring created problem `PRB0041001`. Customers cannot complete checkout. The configuration item listed on the problem appears healthy by itself. The failure is somewhere in the services that it depends on. The outage has also affected everything that depends on the checkout service.

This task is about finding the root cause and the full impact. It is not a general cleanup of the board. Looking only at changes and incidents on the listed service is misleading. There is a recent deployment on checkout that may look like the cause, but its timing does not match the start of the outage. The real cause is in a service that checkout depends on. The complete set of related incidents is on services that depend on checkout. This includes services several levels away that fail only because checkout failed.

## What we expect the agent to do

1. Follow the affected service's CMDB dependencies toward the services it depends on. Find the change whose timing and CI explain the outage. Do not select the unrelated change on checkout itself.
2. Link the problem's investigation to that root-cause change.
3. Follow the full dependency graph toward every service that depends on the affected service. Find every open incident caused by this outage on the affected service and all of its dependent services.
4. Attach each related incident to `PRB0041001` and close it as a duplicate. Do not change unrelated incidents with similar symptoms, incidents already linked to other problems, or tickets created before the outage.
5. Move the problem out of its initial state and mark it as a known error.

## What agents often miss

A common incomplete RCA stops at the listed checkout service. Agents search for changes on the checkout CI, link the recent deployment, and close a few incidents on the same CI. This addresses the ticket that caused the problem to be opened, but it identifies the wrong cause and does not include the full impact.

To find all related records, search the graph in both directions. Search upstream to find the change that matches the outage start time. Search the full downstream graph to find incidents on kiosks, SDKs, partner checkouts, and other dependent services. Searching only one level downstream leaves several real child incidents unlinked. Searching by symptom text without using the dependency graph can include tickets from another problem or older unrelated tickets on the same CI. The listed service shows the symptom. The dependency map identifies the cause and the full impact.
