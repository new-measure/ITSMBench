# task-grc-6 — Data oversharing cleanup before a compliance review

## What this task is

A company is preparing for a SOC 2 and privacy review, and its compliance monitor is
failing data-protection checks. A ticket asks the data-protection analyst to make the
real exposure of the SharePoint estate correct: stop the genuine oversharing, leave
legitimate sharing alone, and close the ticket out.

Sensitive workspaces are leaking through four independent doors: a site-level setting
that allows external sharing, external people holding write access, anonymous
"anyone" links on documents, and document libraries whose default link type is
anonymous. No door tells you about the others, and there is no clean list of what is
wrong. Which workspaces count as sensitive, and which shares were formally approved,
lives in two registers in the ticket system. The estate is full of look-alikes: a
public workspace that is legitimately wide open, an approved external share, internal
links and grants that only look risky, and one workspace that was half locked down —
clean on the settings everyone checks, still leaking through its document links.

## What we expect the agent to do

1. Work out what "sensitive" means here: read the classification register and the
   approved-share register instead of judging by names or appearances.
2. Sweep every workspace on all four doors: turn off external sharing where it
   should not be on, remove or downgrade unapproved external write access, kill
   anonymous document links (including ones whose approval expired or was rejected),
   and fix libraries that hand out anonymous links by default.
3. Trust state, not settings: a workspace locked down at the top can still leak
   through its documents. Check what is actually exposed before calling it safe.
4. Leave the right things alone: the public workspace, the approved unexpired
   external share, and every internal grant and link.
5. Close the ticket honestly.

## What agents often miss

Judgment is consistently good. Every run reads the registers, spares the public
workspace and the approved share, removes the unapproved external access and the
anonymous links, and touches nothing it shouldn't.

The recurring miss is the quietest of the four doors: the library default link type.
Runs disable external sharing at the site level, clean up permissions and existing
links, and then treat the estate as fixed — leaving three sensitive libraries still
set to hand out anonymous links by default. This happens even with the proof on
screen: runs have fetched every library's settings, had the anonymous defaults for
the sensitive libraries in their own output, and still reported the estate verified.
A lockdown at the top of the workspace reads as proof that everything under it is
safe — which is exactly the assumption the task punishes.

In short: three of the four sharing surfaces get fixed reliably; the fourth —
the default that quietly re-creates the problem for every future document — is what
separates a finished run from an almost-finished one.
