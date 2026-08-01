# task-iam-13 — Analytics team locked out of Power BI

## What this task is

This is a P1 incident at a financial company. The entire analytics team lost access to Power BI overnight.

The ticket says a connector update caused the problem. The update did not cause it. The app is healthy. It still works for two analysts who have direct assignments.

The real cause is a quarterly access review that ran overnight. The review made several incorrect changes:

- It removed the analysts' group assignment from the app.
- It removed several people from that group.
- It incorrectly suspended three active analysts.
- It deleted MFA enrollment for three people.
- It removed Power BI licenses from three people.

All of these access requirements must work together. The review broke each one.

The review also made valid cleanup changes. Contractors whose engagements had ended were correctly deprovisioned and had their licenses removed. These changes must remain.

There is also a closed incident from a sister team that had the same problem before. Its notes describe the complete restoration performed at that time.

## What we expect the agent to do

1. Test the reported cause and rule it out. The connector update did not cause the incident.
2. Find the real cause in the identity logs. It was the access-review run that occurred minutes after the update.
3. Restore the complete access setup for only the affected people:
   - Reassign the group to the app.
   - Add the removed members back to the group.
   - Reactivate the accounts that were suspended by mistake.
   - Give users whose MFA enrollment was deleted a working sign-in factor.
   - Restore the Power BI license for the three analysts who still do not have it, while all their teammates do.
4. Do not change the review's valid work:
   - Do not restore access for deprovisioned former contractors.
   - Do not change the healthy sister team.
   - Do not remove or roll back the suspected update.
5. Resolve the incident with an accurate account of what happened.

## What agents often miss

Agents usually investigate the incident well. They rule out the blamed update. They identify the access review as the real cause. They restore the group assignment to the app, restore the group memberships, and reactivate the suspended accounts. They do not affect unrelated users or restore access for people who actually left.

A complete fix must also restore two requirements that are not visible when checking app access directly: MFA enrollment and licenses.

Agents often read the change record that says the review "reclaimed unused licenses". They may also notice that three current group members do not have the license that every teammate has. However, some agents treat this as a data-quality issue for the app owner or say that licensing is out of scope.

Agents sometimes handle the deleted MFA enrollment in the same incomplete way. Some say the users should re-enroll at their next sign-in. One agent used the factor-reset call as the fix, but that call removes enrollment.

The company's record for the earlier identical incident describes the full restoration. This includes factors and licenses. Agents that follow this example complete the task.

In short, agents usually find the root cause. Partial fixes fail to restore every requirement in the entitlement chain, especially the requirements that are not visible from the app.
