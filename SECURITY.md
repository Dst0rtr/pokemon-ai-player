# Security Policy

## Supported versions

Only the `main` branch is supported. Fixes are made there; there are no maintained release branches.

## Reporting a vulnerability

Please do not open a public issue for security problems. Report them privately through GitHub's security
advisories: on this repository, open the **Security** tab and choose **Report a vulnerability**.

Include what is affected (file, tool or command), steps to reproduce, and the impact you expect. You should get
a reply within a week. Once a fix is on `main`, the advisory will be published with credit unless you prefer
otherwise.

## Scope

The server runs Game Boy ROMs locally through PyBoy and talks to an MCP client over stdio. Issues in PyBoy,
the MCP SDK or other dependencies should also be reported to those projects.
