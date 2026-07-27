# Backup / restore reliability — on-call remediation

You are the infrastructure / SRE engineer on call for Nimbus Analytics. A ticket has been
raised: **OPS-2041**. Pick it up, resolve what needs resolving, and get to the bottom of
what happened.

## API access

- Search available mock API operations with `curl 'http://search.local.mock:8080/search?q=<terms>&limit=10'`.
- Use the returned provider hosts and paths to inspect and update records.
- Use port 8080 for all APIs
