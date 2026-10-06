# Print Library plugin for Claude Code

The `print-library` Claude Code plugin: the `3d-print-project` skill with its own copy of the library tool. It designs, verifies and records 3D-printable models. Inside a [Print Library](https://print-library.alexcarvalho.me), a GitHub repository made from the template, it adds models and versions through pull requests; it never merges or pushes to the default branch.

## Install

```sh
claude plugin marketplace add AlexMC/print-library-plugin && claude plugin install print-library@print-library
```

## What it needs

- Claude Code.
- Node 24, for the library tool.
- The GitHub CLI (`gh`), signed in with write access to your library.
- Python 3.8–3.11, only for the design and slicing helpers (`plugins/print-library/skills/3d-print-project/requirements.txt`).

Make a library at <https://print-library.alexcarvalho.me/start>; more about Print Library at <https://print-library.alexcarvalho.me>.

## Licence

MIT, see [LICENSE](LICENSE). The tool bundles npm packages under their own licences: [THIRD_PARTY_NOTICES.md](plugins/print-library/tool/THIRD_PARTY_NOTICES.md).

This repository is synced from a private repository; issues are welcome here.
