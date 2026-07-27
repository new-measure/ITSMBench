# task-ep-20 — External readers on a restricted document site

## What this task is

A security review at a company finds that a restricted document site is readable by an
external group that should not have any access. The finding is filed as a wiki page, and
the agent — the documentation governance operator — is asked to close out whatever
access should not be there and get to the bottom of how it happened.

The named site is only the first symptom. The external group came from a bulk import
during an acquisition, and the same import spread access much wider: the group can read
three more restricted sites, one site still grants access to an offboarded individual,
another has an anonymous view link, and a confidential site carries a grant to a
directory group whose members are all offboarded. On top of that, the contractors behind
the group were offboarded in the identity system months ago — but their accounts in the
company's separate knowledge-base workspace are still active. Nothing lists all of this;
it has to be found by sweeping every site and every directory.

## What we expect the agent to do

1. Remove the external group's access from the named site.
2. Keep going: sweep the other restricted sites and remove every grant that traces to
   the same import — the group grants, the offboarded individual's grant, the anonymous
   link, and the grant to the fully-offboarded directory group.
3. Find the root cause: a bulk access grant made by an integration account during the
   acquisition, never cleaned up when the contractors were offboarded.
4. Follow the cohort into the second directory: the contractors' knowledge-base
   workspace accounts are still active even though their main identities were
   deprovisioned. Deactivate them — but do not delete them.
5. Leave legitimate access alone: the approved partner site, the public help center,
   internal staff, and retained vendor accounts must stay exactly as they are.
6. Update the finding page with what was found and done.

## What agents often miss

The permission sweep goes well. Every run removes the external group from the named
site, expands to the sibling restricted sites, finds the anonymous link and the
group-of-offboarded-users grant, traces the root cause to the acquisition import, and
writes it up — without touching any legitimate access.

What every run misses is the second directory. The contractors look fully offboarded in
the main identity system, and that is where runs check — so the still-active accounts
in the knowledge-base workspace are never touched. Most runs never open that directory
at all. One run did list it, saw the active external accounts, and still left them,
reasoning that the records should be kept for audit — but deactivating an account keeps
the record; leaving it active keeps the access.

In short: the visible permissions get cleaned up; the offboarded people who can still
log in to the knowledge base are what runs miss.
