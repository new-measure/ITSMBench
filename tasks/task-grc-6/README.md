# task-grc-6 — Data oversharing cleanup before a compliance review

## What this task is

A company is preparing for a SOC 2 and privacy review. Its compliance monitor is failing data-protection checks. A ticket asks the data-protection analyst to correct the actual exposure in SharePoint. The analyst must stop real oversharing, leave legitimate sharing unchanged, and close the ticket.

Sensitive workspaces are exposed in four separate ways:

- A site-level setting allows external sharing.
- External people have write access.
- Documents have anonymous "anyone" links.
- Document libraries use anonymous links as their default link type.

Each type of exposure is independent. One does not show whether the others exist. There is no complete list of the problems. Two registers in the ticket system define which workspaces are sensitive and which shares have formal approval.

SharePoint contains many items that may appear risky but are legitimate. These include a public workspace that is intentionally open, an approved external share, and internal links and grants. One workspace is only partly locked down. Its commonly checked settings are safe, but its document links still expose data.

## What we expect the agent to do

1. Determine what "sensitive" means by reading the classification register and the approved-share register. Do not decide based on names or appearances.
2. Check every workspace for all four types of exposure. Disable external sharing where it should not be enabled. Remove or downgrade unapproved external write access. Remove anonymous document links, including links with expired or rejected approval. Change libraries that create anonymous links by default.
3. Check actual exposure, not only settings. A workspace can be locked down at the top level and still expose data through its documents. Verify what is actually exposed before deciding that it is safe.
4. Do not change legitimate access. Leave the public workspace, the approved and unexpired external share, and all internal grants and links unchanged.
5. Close the ticket only after the work is actually complete.

## What agents often miss

Agents consistently make good decisions. Every run reads the registers, leaves the public workspace and approved share unchanged, removes unapproved external access and anonymous links, and does not change anything that should remain unchanged.

The repeated failure is the least obvious of the four exposure types: the library default link type. Agents disable external sharing at the site level, clean up permissions and existing links, and then consider all of SharePoint fixed. They leave three sensitive libraries configured to create anonymous links by default.

This happens even when the evidence is visible. Agents fetch the settings for every library and see the anonymous defaults for the sensitive libraries in their own output. They still report that all of SharePoint is verified. They incorrectly treat a top-level workspace lockdown as proof that everything inside it is safe. This is the exact assumption the task is designed to catch.

In summary, agents reliably fix three of the four sharing surfaces. The missing step is changing the default that will create the same problem again for every future document. Completing this step is the difference between a finished run and an almost-finished run.
