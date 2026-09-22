# Contributing

Development setup, test, and lint commands live in the
[Development](README.md#development) section of the README. CI runs
`ruff check`, `ruff format --check`, and `pytest` on every push and pull
request — run all three locally before opening a PR.

## Developer Certificate of Origin

Every commit must be signed off, certifying the
[Developer Certificate of Origin](https://developercertificate.org/):

```bash
git commit -s
```

This appends a `Signed-off-by:` trailer with your name and email, which must
match the commit author. Commits without a sign-off are rejected by the DCO
check on pull requests.

## AI-assisted commits

Commits produced with AI assistance carry an `Assisted-By:` trailer instead
of `Co-Authored-By:`:

```
Assisted-By: Claude <noreply@anthropic.com>
```

The DCO sign-off is a certification only the human author can make, so the
tool is credited as assistance, not authorship. The sign-off remains yours.
