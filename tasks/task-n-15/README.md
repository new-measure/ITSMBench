# task-n-15 — Subdomain-takeover audit of a DNS zone

## What this task is

A security finding flags records in the corporate DNS zone as possible
subdomain-takeover risks: they appear to resolve to targets that are no longer
live. The finding blames a recent cloud migration — a decoy — and names no
specific records. The job is to audit the whole zone and, for each record, decide
whether its target is genuinely dead or still live, then remove or repoint the
dead ones while leaving the live ones exactly as they are, and resolve the
finding.

The catch is that "dead" is not obvious from the name. A record's target is live
only if something still owns it: an attached network interface holding that
address (on its primary *or* a secondary address), an allocated public IP, or an
in-service host. A detached interface does not count. For alias, mail, and
nameserver records, you have to follow the chain — an alias may point at another
alias several hops deep — and see whether it ends at something live or at an
approved external dependency. The dead records are scattered across every record
type, and several live records look external or unclaimed but must be kept.

## What we expect the agent to do

1. Dismiss the blamed migration and audit every record in the zone, of every type
   — not just the address and alias records.
2. For each record, check its target against live infrastructure: an attached
   interface (any of its addresses), an allocated public IP, or an in-service
   host. Follow alias, mail, and nameserver chains hop by hop to a live end.
3. Remove or repoint every genuinely dangling record.
4. Leave the live records alone — including ones that look external but are
   approved dependencies, addresses that live as a secondary on an attached
   interface, and aliases that resolve live only after several hops.
5. Leave the out-of-scope zone and unrelated records untouched, and resolve the
   finding.

## What agents often miss

Current runs handle this task well, and the reason it is hard is that every quick
rule for "is this target dead" is wrong in a way the zone is built to expose.

Deciding by address range keeps dead hosts in the internal range and deletes live
public ones. Treating "an interface exists at this address" as live keeps records
whose interface is actually detached. Checking only an interface's primary
address wrongly deletes records that live as a secondary. Resolving an alias one
hop deep deletes live aliases that need several hops to reach a live target. And
listing only address and alias records never reaches the mail and nameserver
records that are also dangling. Each shortcut produces a confident, wrong answer
on a different slice of the zone.

The other half is restraint. Several records look external or unclaimed but are
approved dependencies that must survive, and there is an entire out-of-scope zone
that must not be touched. A run that sweeps broadly to "clean up" fails as surely
as one that stops early — and because the dangling and live records are mixed
together throughout the zone, there is no positional or bulk shortcut that
substitutes for checking each target.

In short: this is per-record judgment, not a sweep. Checking each target against
what actually owns it — following the chains, honouring secondary addresses and
attachment state, and sparing the live look-alikes — is the whole task.
