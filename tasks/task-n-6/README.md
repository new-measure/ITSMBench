# task-n-6 — Payment outage after a network migration

## What this task is

A P1 incident reports that payment processing is failing across the platform. The incident blames the app deploy from the previous evening. This is a decoy. The app is working correctly.

During an overnight maintenance window, the peering between the production network and the shared-services network was rebuilt. Segmentation was also re-applied. Two app tiers were fixed correctly and can be used as references. The payments tier was left only partly connected.

The failure affects both directions. A connection across the peering works only if every hop allows it. The near side must have the correct outbound rules and route. The far side must have the correct inbound rules and return route. The stateless network ACLs on both subnets must also allow traffic in both directions.

The incident mentions only payments. This may lead an agent to fix only the near side and stop. If the far side is not fixed, the shared endpoints' inbound rules and the return path remain blocked. Payments will still fail.

Some DNS records also point to hosts that were retired during the migration. These records must be cleaned up.

## What we expect the agent to do

1. Confirm that the app deploy did not cause the incident, then move on.
2. Restore the complete payments path in both directions. Add the outbound rules for each dependency, replace the route that uses the dead peering, and fix both directions of the network ACLs on the payments subnet.
3. Fix the far side as well. Add the return route to payments, fix the shared subnet's ACLs, and add an inbound rule for the payments subnet to each shared endpoint.
4. Use the working reference tiers as the model for the fix. Give payments only the access that those tiers have. Do not grant wider access.
5. Clean up the DNS records that still point to retired hosts.
6. Do not change the reference tiers, the decoy, or anything that is already correct. Resolve the incident.

## What agents often miss

Current runs usually handle the main issue well. They reject the claim that the deploy caused the incident. They identify the broken peering path and restore both sides.

The difficult part is that the fix must cover both directions, while the incident mentions only one side. The ticket is about payments, so the most obvious changes are on the payments side: its outbound rules and its route.

However, the connection works only if the destination also allows the traffic and its return traffic. The shared endpoints must allow the payments subnet. The shared network must have a return route. The network ACLs are stateless, so both subnets must allow both directions.

If an agent stops after fixing the near side, payments still cannot complete a round trip. This remains true even if everything on the side named in the incident is correct.

The required configuration does not need to be guessed. The two reference tiers were fixed correctly during the same maintenance window. They show exactly how payments should be configured.

The task is to copy that configuration to payments completely, without giving payments more access than the reference tiers. The agent must then remove the DNS records that still point to retired hosts.

In short, the incident names only the visible payments side. The task tests whether the agent also completes the far-side changes and the return path.
