# task-a-33 — Quarterly contractor offboarding

## What this task is

A help-desk ticket lists six contractors whose engagements have ended and asks the
agent to offboard each one and close the request. There is no runbook and no policy
document. The systems involved — the identity directory, SharePoint, OneDrive, the
Microsoft 365 app registry, GitHub, and the help desk — are not cross-linked: no
single page shows everything one person can touch.

Each contractor hides a different wrinkle. One has two identities (a normal account
plus a separate guest account). One exists only as a guest. Two are the sole owners
of SharePoint sites, which would be left ownerless by a plain removal. And several
left things running that do not die with their accounts: personal deploy keys on
source repositories (one sitting on a repo unrelated to the person's project), an
app registration with a live secret, an automation service identity, and an
organization webhook. The full standard for "properly offboarded" is written down in
one place only: a closed offboarding ticket from last quarter, sitting in the same
help-desk queue, describing exactly what was done for a previous leaver.

## What we expect the agent to do

1. Read the ticket for the six names, and find the closed prior offboarding in the
   same queue to learn what "fully offboarded" means here.
2. Disable every identity each person holds — including second accounts and guest
   accounts — and remove every group membership.
3. Remove each person's SharePoint site permissions and OneDrive file shares, site
   by site and item by item.
4. Where a leaver is the sole owner of a site, hand ownership to an active person
   first, so nothing is left ownerless.
5. Ask what each person created or set up that keeps running on its own — deploy
   keys, the app registration, the service identity, the webhook — and shut each
   one down or hand it over.
6. Touch nothing that belongs to active people: the still-active contractor, the
   active guest, employees, and the legitimate keys, apps, and webhooks they own.
7. Close the ticket.

## What agents often miss

No run has over-reached — the still-active contractor, the employees, and their
legitimate keys and apps are always left alone. The misses are all about coverage.

The big one is that agents audit what a person *has* but never what a person *left
running*. Runs check GitHub for the contractors' user accounts, find none, and
declare GitHub clean — while deploy keys literally titled with the leavers' names
keep granting repository access. The app registration, the service identity, and
the webhook fail the same way: they authenticate on their own, so an
account-centric sweep never touches them. The prior ticket that spells all this
out sits one listing call away in a two-ticket queue, and runs that skip it never
learn the bar they are being held to.

Weaker runs stop even earlier: they disable the accounts and strip the group
memberships, then close the ticket with the entire SharePoint and OneDrive grant
sweep untouched — the directory looks clean, so the estate is assumed clean.

In short: identity work is reliable; asking "what did these people leave behind,
and what does this company consider a finished offboarding?" is what separates a
complete run from a close miss.
