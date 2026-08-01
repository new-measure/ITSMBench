# task-n-7 — Expired TLS certificate across customer endpoints

## What this task is

A P1 incident alerts the on-call engineer. Several customer-facing HTTPS endpoints have failed since overnight. Browsers show security warnings. The incident suggests load-balancer maintenance or a firewall change as possible causes. Neither is the cause. A shared wildcard TLS certificate at the edge has expired.

A valid replacement certificate is already staged. Some endpoints already use it, but the remaining endpoints do not. To fix the outage, rotate every affected endpoint to the replacement certificate. The certificate information also exists outside the load balancer. It appears in DNS validation records, the certificate inventory, and the certificate binding field on each service. If these records still point to the expired certificate, the environment remains inconsistent even after the endpoints work again.

## What we expect the agent to do

1. Ignore the load-balancer and firewall decoys. Find the expired wildcard certificate.
2. Move every affected endpoint to the valid replacement. This includes the endpoint served through a certificate list instead of a direct bind.
3. Do not change endpoints that are already correct. Keep the internal admin endpoint on its own dedicated certificate. Do not move it to the public wildcard certificate.
4. Update the stale DNS validation records so they no longer point to the decommissioned validator.
5. Update the certificate inventory. Mark the expired certificate as retired and the replacement as deployed. Rebind every affected service record to the valid certificate.
6. Ignore the drained maintenance host. It is an intentional decoy.
7. Resolve the incident and clearly state the root cause.

## What agents often miss

Agents usually fix the visible outage. They find the expired certificate, move the load-balancer endpoints to the valid certificate, update the DNS validation records, and close the incident.

They often fail to update the systems of record. Each service has a field that identifies its bound certificate. The certificate inventory also stores the status of each certificate. Agents fix the serving path so the endpoints work again, but they do not update these records. As a result, the inventory still lists the expired certificate as live, and the services still report that they are bound to it. The required information is already available. Agents query the certificate inventory often and can see which certificate is valid. However, they do not use that information to update the service bindings. The endpoints work, but the systems of record still say that the expired certificate is in use.

Restoring traffic is only part of the task. The agent must also update the certificate inventory and the service bindings. Every system must show the same valid live certificate.
