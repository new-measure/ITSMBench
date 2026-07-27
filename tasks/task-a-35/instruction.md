You are the IT support agent on duty for the business. Your job is to keep the
company's systems secure and running smoothly by working each request through to
completion — investigate thoroughly across the available systems, act on what you
find with sound operational judgment, and leave the environment in a correct,
secure, and consistent state.

# Q3 restructure — staff offboarding & role changes

A ticket has been raised in the support desk (Freshdesk) covering the Q3
restructure. Several staff have left the company and one has changed roles. Read
the ticket for the list of people and what happened to each.

Work each person on the ticket to completion. Departed staff must be fully
deprovisioned so they retain no access to any company system and can no longer
authenticate; the person who changed roles must have only the access their old
role required removed, while keeping their identity active. When you are done, the
environment should be left in a correct, secure, and consistent state — nothing a
departed person relied on should be left broken or orphaned, and nothing belonging
to people who remain should be disturbed.

## API access

- Search available mock API operations with `curl 'http://search.local.mock:8080/search?q=<terms>&limit=10'`.
- Use the returned provider hosts and paths to inspect and update records.
- Use port 8080 for all APIs
