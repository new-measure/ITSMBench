# task-n-7 — Expired TLS certificate across customer endpoints

## What this task is

A P1 incident pages the on-call engineer: several customer-facing HTTPS endpoints
have been failing since overnight, with browser security warnings. The incident
hints at load-balancer maintenance or a firewall change, but neither is the
cause. A shared wildcard TLS certificate on the edge has expired.

A valid replacement certificate is already staged, and some of the estate has
already moved to it. The rest has not. Fixing the outage means finishing the
rotation across every affected endpoint — but the certificate lives in more
places than the load balancer: the DNS validation records, the certificate
inventory, and the record on each service that says which certificate it is
bound to. Leaving those pointing at the dead certificate leaves the environment
inconsistent even after the pages stop erroring.

## What we expect the agent to do

1. See past the load-balancer and firewall decoys and find the expired wildcard
   certificate.
2. Move every affected endpoint onto the valid replacement, including the one
   served through a certificate list rather than a direct bind.
3. Leave the endpoints that are already correct, and keep the internal admin
   endpoint on its own dedicated certificate rather than the public wildcard.
4. Repoint the stale DNS validation records off the decommissioned validator.
5. Update the certificate inventory — mark the expired one retired, the
   replacement deployed — and rebind each affected service record to the valid
   certificate.
6. Ignore the drained maintenance host, which is a deliberate decoy.
7. Resolve the incident with a clear root cause.

## What agents often miss

Runs handle the visible outage well: they find the expired certificate, rotate
the load-balancer endpoints onto the valid one, fix the DNS validation records,
and close the incident.

Where they stop short is the record of truth. Each service carries a field naming
the certificate it is bound to, and the certificate inventory carries each
certificate's status. Runs fix the serving path so the endpoints load again, then
never go back to update those records — so the inventory still lists the expired
certificate as live and the services still claim to be bound to it. The
information needed is in hand: runs query the certificate inventory heavily and
can see exactly which certificate is valid. They just never connect that to
rebinding the service records. The endpoints work, but the systems of record
still describe a world running on a dead certificate.

In short: restoring the traffic is only half the job. Following the certificate
through the inventory and the service bindings — so every system agrees on which
certificate is live — is what runs leave undone.
