# task-a-40 — Security team offboarding

## What this task is

A ServiceNow incident at a security company lists several staff members and contractors who have left the security organization. The agent is the on-duty IT/security operations engineer. The agent must offboard every person on the list and then close the incident.

The people have accounts and records in different systems. Some are in the identity platform. Some are only in the single-sign-on system. They also have records in endpoint protection, the asset inventory, and detection configuration. Offboarding requires more than disabling accounts. Some people were the only owners of active production servers. Some created antivirus exclusions that still prevent scanning of their old paths. A closed incident for an earlier leaver shows all the steps required for complete offboarding, including the antivirus exclusion cleanup.

## What we expect the agent to do

1. Read the incident and process every person listed in it. This includes people who exist only in the single-sign-on system.
2. Disable each leaver's accounts and remove them from every group in both identity systems. This includes sensitive groups such as building access.
3. Remove leavers from the VPN application that they could still use to sign in.
4. Reassign production servers when the person who left was their only owner. Do not delete the machines.
5. Clean up detection configuration. Delete antivirus exclusions created by departed people because those exclusions still prevent scanning of their old paths. Do not remove the legitimate exclusion created by a current employee.
6. Do not change protective security content or current staff. Existing threat indicators, blocklists, active accounts, and current staff group memberships must remain unchanged.
7. Close the incident after completing all work.

## What agents often miss

Agents usually complete the account-related work. Different models disable every account, remove every group membership, remove VPN access, reassign servers that no longer have an owner, and close the incident. They do not harm unrelated people or protective controls.

However, they consistently miss the detection-configuration cleanup. Agents check the endpoint-protection system, but they look only at users, devices, and threats. When they find nothing to change in those areas, they decide that no endpoint-protection work is needed. They do not list the antivirus exclusions created by the departed people, even when the relevant API already appeared in their own search results. These exclusions are still active and still prevent scanning. The closed incident for an earlier leaver states that removing these exclusions is part of complete offboarding. Agents who read only the current ticket do not see that instruction.

In short, agents treat offboarding only as an account-access task. They miss configuration left behind by departed people. Every run so far has missed this point.
