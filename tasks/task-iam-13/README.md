# task-iam-13 — Analytics team locked out of Power BI

## What this task is

A P1 incident at a financial company: the whole analytics team lost access to Power BI
overnight. The ticket blames a connector update that shipped the same day. The update is
innocent — the app is healthy and still works for two analysts who happen to hold direct
assignments. The real cause is a quarterly access review that ran overnight and
over-reached: it detached the analysts' group from the app, dropped several people out of
that group, wrongly suspended three active analysts, erased three people's MFA
enrollment, and took back three people's Power BI licenses. Access is a chain, and the
review broke it at every link.

The world also holds honest cleanup by the same review — contractors whose engagements
really ended were correctly deprovisioned and de-licensed — and a closed incident from a
sister team that hit the exact same failure before, whose notes describe the full
restoration done that time.

## What we expect the agent to do

1. Test the reported cause and clear it: the connector update did not do this.
2. Find the real culprit in the identity logs: the access-review run, minutes after the
   update.
3. Restore the whole chain for exactly the affected people: re-attach the group to the
   app, re-add the dropped members, reactivate the wrongly suspended accounts, give the
   MFA-wiped users a working sign-in factor again, and re-grant the reclaimed license to
   the three analysts who still lack it while their teammates all hold it.
4. Leave the review's legitimate work alone: deprovisioned ex-contractors stay gone, the
   healthy sister team stays untouched, the suspected update stays in place.
5. Resolve the incident with an honest account.

## What agents often miss

The investigation is consistently strong. Runs reject the blamed update, name the access
review as the real cause, restore the group-to-app assignment and the memberships, and
reactivate the suspended accounts. Nobody harms bystanders or resurrects real leavers.

What separates a full fix from a partial one is the two links that do not show up when
you look at app access directly: MFA enrollment and licenses. Runs read the change record
that says the review "reclaimed unused licenses", even notice that three current group
members are missing the license every teammate holds — and then explain it away as a
data-quality question for the app owner, or declare licensing out of scope. The wiped
MFA gets similar treatment: some runs decide the users should just re-enroll themselves
at next sign-in, and one used the factor-reset call — which removes enrollment — as if
it were the fix. The company's own record of the earlier identical incident spells out
the full restoration, factors and licenses included; runs that follow that example
finish the job.

In short: the root cause gets found; restoring every link of the entitlement chain —
not just the links that are visible from the app — is what partial runs leave undone.
