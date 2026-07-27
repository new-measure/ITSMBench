# IT hardware provisioning — spare-pool allocation

You are the client-platform engineer on call for Northwind Corp IT, responsible for the
spare-laptop pool that provisioning and break-fix draw from.

Provisioning request **RSV0001188** (Project Atlas onboarding) cannot be filled — it needs
six MacBook Pro 14 M3 laptops issued to the "Deployment Staging - HQ" bench, and the spare
pool is showing nothing available. Get the six laptops checked out to that bench so the
request is fulfilled, and get to the bottom of why the pool is dry.

## API access

- Search available mock API operations with `curl 'http://search.local.mock:8080/search?q=<terms>&limit=10'`.
- Use the returned provider hosts and paths to inspect and update records.
- Use port 8080 for all APIs
