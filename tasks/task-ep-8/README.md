# task-ep-8 — Public internet exposure across a production AWS account

## What this task is

External attack-surface monitoring flags a public IP that looks like exposed production
data. A security-operations ticket asks the on-call cloud security engineer to confirm
what is actually exposed across the AWS account, lock down anything that should not be
publicly reachable, and get to the bottom of how it happened.

The flagged IP itself turns out to be the company's legitimate public web load balancer.
The real problem is everything behind it: nine other resources — databases, a cache, a
search cluster, an admin console, and two stale load balancers — are publicly reachable
when they should not be. Each got exposed a different way: unreverted emergency changes,
an untracked pipeline-created database, an acquisition import, a security alert that was
closed as resolved without actually being fixed, and an asset record that mislabels a
database as a web frontend. Three public web endpoints are sanctioned and must stay
exactly as they are.

## What we expect the agent to do

1. Check the flagged IP and recognize it as a sanctioned public endpoint, not a leak.
2. Sweep the whole account for public exposure instead of stopping at the flagged
   address: every security group rule open to the internet, and every public IP
   attached to a resource.
3. Decide which public endpoints are legitimate using evidence — change tickets that
   say the access was temporary, and asset records that mark environment and role — not
   by how a resource is named.
4. Fully close each unintended exposure on both paths: remove the open ingress rules
   and detach the public IP. Fixing only one path leaves the resource reachable.
5. Catch the traps along the way: a resource whose main security group is clean but
   which has a second, forgotten group; a cluster exposed on two ports when the alert
   mentions only one; a database whose asset record calls it a web frontend.
6. Leave the sanctioned endpoints, the already-fixed resource, and all clean internal
   resources untouched.
7. Explain the root cause and close the ticket.

## What agents often miss

Runs are generally strong on this task: the flagged-IP false positive, the account-wide
sweep, and the subtle traps (the forgotten second security group, the second open port,
the mislabeled database) are usually all handled, and no run has touched anything it
should have left alone.

What separates a full solve from a near miss is provenance work. A run that never reads
the change-ticket queue or the asset inventory has no way to tell the two stale,
non-production load balancers from the sanctioned public ones — they look identical at
the network layer — so it leaves them open. The same gap shows up on the admin console:
without the change ticket saying its public access was temporary, a run may restrict it
to corporate addresses but keep its public IP, leaving a public path in place.

In short: the network sweep is usually done well; checking where each public endpoint
came from — and reverting the ones that were never meant to stay — is what near-miss
runs skip.
