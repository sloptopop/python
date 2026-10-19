# Contributing

Thank you for helping to improve sloptopop.

## Before you start

- Security problems: follow [SECURITY.md](SECURITY.md). Never open a
  public issue for them.
- For anything larger than a small fix, open an issue first, so we can
  agree on the approach before you spend time on it.
- Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).

## Licence of contributions

This repository is licensed under either of the Apache License, Version
2.0 ([LICENSE-APACHE](LICENSE-APACHE)) or the MIT license
([LICENSE-MIT](LICENSE-MIT)), at your option.

Unless you explicitly state otherwise, any contribution intentionally
submitted for inclusion in the work by you, as defined in the Apache-2.0
license, shall be dual licensed as above, without any additional terms or
conditions. There is no contributor licence agreement. Submit only work
you have the right to license this way.

## Quality gate

Every change must pass the repository's quality gate, `scripts/gate.sh`. [LANGUAGE.md](LANGUAGE.md) lists the pinned tools and versions and anything still pending. The quality standard every open-source sloptopop repository
follows is in
[sloptopop/cli docs/quality-standard.md](https://github.com/sloptopop/cli/blob/main/docs/quality-standard.md).

- Write the tests with the code. Nothing is skipped, and a missing tool
  fails the gate.
- Add dependencies only under a licence on the allow-list of the quality
  standard (item 8). Copyleft code is never linked in.
- Never put real credentials, customer code or personal data in code,
  fixtures, tests or commit messages. Fixtures are synthetic.

## Pull requests

- Keep each pull request focused on one change, and explain what it
  changes and why.
- State that the gate passed, or what failed and why.
- A maintainer reviews every change before it is merged.

## Name and logo

The code licences do not grant rights to the name "sloptopop" or its logo
(Apache-2.0, section 6). Forks are welcome under the code licences, but
must not present themselves as sloptopop.
