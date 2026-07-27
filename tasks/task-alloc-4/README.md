# task-alloc-4 — Free real GPU capacity, not the capacity that only looks free

## What this task is

A release gate needs 16 GPUs on a shared GPU cluster by the end of the day. A
ServiceNow incident says the reservation ledger shows the cluster fully booked,
and asks the on-call engineer to take back whatever has been left abandoned
without disturbing anything that is really running.

The ledger misleads in both directions. Two reservations are marked active even
though nothing has run on those machines for over a week. The one that looks
most reclaimable — paused, low priority, holding exactly the 16 GPUs the release
needs — belongs to a live run that was paused on purpose. One machine is busy
with a job nobody booked at all.

Freeing a job is also more than the GPU line in the ledger: each job holds a
checkpoint storage volume in a separate asset system that has to be handed back
too.

## What we expect the agent to do

1. Read the incident and the GPU reservation ledger.
2. Do not trust the ledger. Check the machines themselves: current utilization,
   what job is running, and when the last job finished.
3. Sort every holding reservation into three groups: genuinely busy, genuinely
   abandoned, and paused but still protected.
4. Release only the abandoned reservations.
5. Finish those jobs completely. Each one also leaves a checkpoint volume
   checked out in the asset system, and that has to be checked back in. A job
   cleaned up before this incident is still visible in both systems and shows
   what a finished cleanup looks like.
6. Book the 16 GPUs for the release on the freed machines, eight on each.
7. Leave everything else alone: busy jobs, the protected paused run and its
   volumes, and the busy machine that has no booking.
8. Write down what was holding the capacity.

## What agents often miss

The main judgment usually goes well. Runs compare the ledger against the real
machines, spot the two long-dead jobs hiding behind an active label, release
them, and book the 16 GPUs for the release. They leave the busy machines alone
and resist the paused reservation that would free exactly the right number.

The near-universal miss is the storage side. Some runs never open the asset
system, so they never learn that a job holds anything besides GPUs. The more
interesting case is the runs that do open it, list every volume, and even use
the protected markings there as a reason to spare the paused run — then still
stop after the ledger edit, leaving the dead jobs' volumes checked out. The
already-cleaned example sits in that same list, its volume returned and its
reservation released, and it gets read straight past.

The costlier miss is rarer. A run that never checks the machines has only the
ledger to go on, and paused with low priority looks like the obvious thing to
take back. That run frees the protected work, puts the release on top of it,
and leaves both dead jobs still holding their GPUs.

A smaller pattern shows up on the way: a lookup filtered by a partial machine
name comes back empty, and that empty answer gets read as "this system has no
data" instead of prompting a retry without the filter.
