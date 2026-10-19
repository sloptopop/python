# Security policy

## Reporting a vulnerability

Please report security problems privately. Do not open a public issue,
discussion or pull request for them.

Use GitHub private vulnerability reporting: open the **Security** tab of
this repository and choose **Report a vulnerability**.

Please include:

- the affected component and version (for the CLI: `sloptopop --version`);
- the steps to reproduce, ideally with a small synthetic repository;
- the impact you expect.

Do not include real credentials, customer code or other people's personal
data in a report.

## Scope

This policy covers the Python client package in this repository. The `sloptopop` binary this library starts (or bundles) is covered by [sloptopop/cli](https://github.com/sloptopop/cli/security); report problems in the binary or the engine there.

Problems in third-party analyzers that `sloptopop collect` runs belong to
those projects; we are glad to hear about them if sloptopop's use of a tool
makes them worse.

## What happens next

- We acknowledge a report within 5 working days and keep you informed
  until it is resolved.
- We fix confirmed vulnerabilities in the latest release and publish a
  GitHub security advisory. We credit you, unless you prefer otherwise.
- Please keep the details private until a fix is released, or for at most
  90 days from your report.

## Supported versions

sloptopop is before version 1.0. Only the latest release receives security
fixes.
