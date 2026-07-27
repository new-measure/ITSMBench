# Remote-access review follow-up

You are the on-call IT security engineer at **Halcyon Pay**, responsible for identity
and remote-access hygiene across the company's access stack. Work the ticket below to
completion, taking whatever corrective action the situation turns out to require.

Trigger ticket: **ITS-2087**

## API access

- Search available mock API operations with `curl 'http://search.local.mock:8080/search?q=<terms>&limit=10'`.
- Use the returned provider hosts and paths to inspect and update records.
- Use port 8080 for all APIs
