# task-iam-12 — Segregation-of-duties conflicts in effective access

## What this task is

An IAM / access-governance engineer at Meridian Trade & Finance is working a Q3 access
review finding: users hold toxic segregation-of-duties entitlement combinations in the
finance and procurement Salesforce org. The finding asks for genuine conflicts to be
resolved in the least-disruptive way, then closed against the SoD control matrix.

A user's real permissions are the union of three layers — the profile's baseline
permission set, directly assigned permission sets, and permission sets inherited through
an assigned permission-set group. For every real conflict, the two halves of the toxic
pair arrive through different layers, so a single-layer audit sees nothing wrong.

The finding names no users. Across a large population, only a minority are in genuine
conflict. Some conflicts sit next to approved compensating-control exceptions, and some
toxic grants are bundled in the same supplementary permission set as a legitimate
add-on duty that clean role-peers also hold. Clearing the conflict by bluntly unassigning
that set also strips work the user is supposed to keep.

## What we expect the agent to do

1. Read the GRC finding and load the SoD control matrix and any compensating-control
   exceptions — without assuming every rule has a violator.
2. Audit effective permissions across the full user population by computing the union of
   profile, direct assignments, and group-inherited permission sets.
3. Confirm each apparent conflict is real against the matrix, and leave approved
   exception holders intact.
4. Resolve each genuine conflict in the least-disruptive way: remove the supplementary
   toxic half, not the profile-conferred primary duty that defines the role.
5. Where the toxic capability is bundled with a legitimate add-on (for example forecast
   management that peers also hold), clear the toxic grant without stripping that add-on —
   unassign at a finer grain or re-grant the clean duty.
6. Prefer per-user fixes over mutating a shared permission-set group that an exception
   holder also uses.
7. Leave non-conflicting dual holders, benign extras, and clean peers alone; do not
   deactivate users as a shortcut.
8. Record the outcome and close the finding.

## What agents often miss

Computing the effective-permission union and finding the conflicts is usually within
reach. The judgment tail is where runs fail.

The recurring over-fix is the bundle trap: the toxic capability rides in the same
supplementary permission set as a legitimate non-conflicting duty. Unassigning that
whole set clears the SoD pair and also strips work the user's clean peers still have.
The finding asks for least-disruptive remediation; preserving the add-on (or re-granting
it cleanly) is part of finishing.

A related miss is fixing a shared permission-set group that both a real violator and an
approved exception user sit in. Changing the group "fixes" the violator and breaks the
exception. The correct move is per-user. Incomplete population sweeps that stop after
the first handful of conflicts leave other violators live — the finding is about the
estate, not a sample.
