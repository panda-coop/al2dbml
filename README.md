# AL-to-DBML

[![PyPI version](https://img.shields.io/pypi/v/al2dbml.svg)](https://pypi.org/project/al2dbml/)
[![Python versions](https://img.shields.io/pypi/pyversions/al2dbml.svg)](https://pypi.org/project/al2dbml/)
[![CI](https://github.com/panda-coop/al2dbml/actions/workflows/ci.yml/badge.svg)](https://github.com/panda-coop/al2dbml/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

`al2dbml` turns a compiled Microsoft Dynamics 365 Business Central AL package (`.app`) into a [DBML](https://dbml.dbdiagram.io/) schema you can paste straight into [dbdiagram.io](https://dbdiagram.io) or push to [dbdocs.io](https://dbdocs.io). It reads `SymbolReference.json` from the archive (tolerating AL's 40-byte header and Ready-To-Run wrappers), normalises tables, table extensions, enums, and `TableRelation`s, and emits one valid DBML document with `Project`, `Table`, `Ref`, `Enum`, and `TableGroup` blocks.

Sample output:

```dbml
Project "MyApp" {
    database_type: 'MSSQL'
    Note { '''MyApp 1.0.0.0 by ACME''' }
}

Table "dbo"."Customer" {
    "No." varchar(20) [pk, note: '"No."']
    "Name" varchar(100)
    "Customer Posting Group" varchar(20)
}

Ref { "dbo"."Customer"."Customer Posting Group" > "dbo"."Customer Posting Group"."Code" }

TableGroup "Sales" { "Sales Header" "Sales Line" }
```

Release notes live in [CHANGELOG.md](CHANGELOG.md).

## Install

Python 3.10+. Runtime depends only on [`click`](https://click.palletsprojects.com/), [`pydbml`](https://github.com/Vanderhoof/PyDBML), and [`PyYAML`](https://pyyaml.org/) (for the optional aldoc overlay).

```bash
uv tool install al2dbml     # recommended — isolated environment, on PATH
pipx install al2dbml        # also fine
pip install al2dbml         # works inside an activated venv
```

If you don't have `uv`:

```bash
sudo dnf install uv                              # Fedora / RHEL
brew install uv                                  # macOS
curl -LsSf https://astral.sh/uv/install.sh | sh  # anywhere
```

Upgrade with `uv tool upgrade al2dbml`. Verify with `al2dbml --version`.

## Quickstart

```bash
al2dbml MyApp.app -o schema.dbml
```

That's the whole workflow. Drop `schema.dbml` into <https://dbdiagram.io>, or push it to dbdocs:

```bash
npx -y dbdocs build schema.dbml
```

Without `-o` the DBML streams to stdout so you can pipe it anywhere.

## CLI options

Run `al2dbml --help` for the full list. The flags group by purpose:

**Output**

- `-o, --output FILE` — write DBML to `FILE` instead of stdout.
- `--stats` — print object counts (tables, enums, refs, groups) to stderr. With no `-o`, skips the (expensive) render entirely for a fast probe.

**Filtering**

- `--include PATTERN` — keep only tables matching `PATTERN` (fnmatch). Repeatable.
- `--exclude PATTERN` — drop tables matching `PATTERN`. Applied after `--include`. Repeatable.

**Grouping**

Tables are bucketed into `TableGroup`s by the last segment of their AL namespace (so `Microsoft.Finance.GeneralLedger` → group `GeneralLedger`); un-namespaced tables fall back to their first whitespace-separated word (`Sales Header` + `Sales Line` → `Sales`).

- `-g, --group NAME=PATTERN[,PATTERN...]` — explicit rule. Repeatable.
- `--group-by namespace|word|none` — change the auto-source (default `namespace`).
- `--no-groups` — emit no `TableGroup` blocks at all.
- `--min-group-size N` — drop groups smaller than `N` tables (default 2; use `1` to keep singletons).

**Schemas**

- `--table-schema NAME` — schema for `Table` blocks (default `dbo`, matching BC's SQL Server).
- `--enum-schema NAME` — schema for `Enum` blocks (default `meta`, since BC enums are AL-language metadata, not SQL objects).

**dbdocs header**

- `--database-type NAME` — value for the DBML `Project { database_type: ... }` line (default `MSSQL`). Pass `""` to omit it. dbdocs.io uses this as the engine label on the rendered schema.

**Extensions**

- `--no-merge-extensions` — emit `TableExtensions` as separate `<Target> (Extension)` tables instead of merging their fields into the base table.

**Rich descriptions**

- `-d, --docs DIR` — overlay aldoc-generated YAML field descriptions and table summaries onto the diagram (see next section).

## Rich field descriptions (aldoc overlay)

Default column notes come from the AL `Caption` property — usually just the field name. The actual BC documentation (the "Specifies the customer number..." sentences from [Microsoft Learn](https://learn.microsoft.com/dynamics365/business-central/dev-itpro)) lives in the AL `ToolTip` property and `/// <summary>` XML doc comments, neither of which the compiled `.app` keeps.

Microsoft's [`aldoc`](https://learn.microsoft.com/dynamics365/business-central/dev-itpro/developer/devenv-al-doc) tool (bundled with the AL Language VS Code extension) does keep them. Run it once per release, then point `al2dbml` at the output:

```bash
aldoc generate MyApp.app -o ./myapp-docs/                       # slow, once per release
al2dbml MyApp.app --docs ./myapp-docs/ -o schema.dbml            # fast
```

You get:

- Each `Table` block gains a `Note { ... }` body from the AL `/// <summary>` of the table.
- Each column note leads with the AL `ToolTip` text instead of the bare caption.
- Existing `**Condition:**` / `**References**` sections still follow.

Coverage is uneven. Active-document tables (Customer, Item, Sales Header) are richly documented; history and buffer tables often have nothing. Missing entries fall back to the Caption-based note.

## Python API

```python
from al2dbml import Diagram, generate, GroupingConfig

# One-shot
dbml = generate("MyApp.app", output_path="schema.dbml", database_type="MSSQL")

# Step-by-step with custom config
diagram = Diagram.from_app(
    "MyApp.app",
    grouping=GroupingConfig(rules={"Documents": ["Sales*", "Purch*"]}),
    includes=["Sales*", "Customer"],
    docs=...,  # optional AldocDocs from al2dbml.aldoc.load_docs
)
print(diagram.dbml())  # build + render
print(diagram.stats())  # {'tables': N, 'columns': N, ...}
print(diagram.context.tables.keys())  # inspect the live BuildContext
```

`Diagram` is a single-shot dataclass: `build()` is cached, so mutating its fields after the first call has no effect. Construct a new instance to rebuild with different settings.

A second console script, `al2dbml-validate FILE.dbml`, parse-checks a DBML file via pydbml. Useful as a smoke test in CI, though it doesn't match dbdiagram.io's parser exactly — see Limitations.

## Limitations

- **Render time scales quadratically with table count** inside pydbml. Up to a few hundred tables: sub-second. Microsoft's full Base Application (~1,500 tables) currently takes several minutes. A custom emitter is on the roadmap.
- **FlowFields** are treated as regular fields; the underlying `CalcFormula` is not interpreted.
- **Obsolete fields** are emitted alongside active ones; no filtering by `ObsoleteState`.
- **Multi-field primary keys** become multiple `[pk]` flags (DBML's single-PK convention) rather than a composite index.
- **Multi-column secondary keys** are not yet emitted as DBML `indexes` blocks; only single-column secondary keys surface (as `[unique]`).
- **Cross-package references** (relations pointing outside the current `.app`) degrade to `**References** \`Target\` (cross-package)` notes on the source column, since the target table is absent from the diagram.
- **Conditional `IF`/`ELSE` `TableRelation`s** produce one `Ref` per resolved branch, with the branch's condition recorded as a `// when (...)` comment on the Ref. Branches whose target is missing degrade to a column note.
- **`al2dbml-validate` uses pydbml's parser**, which is not byte-identical to dbdiagram.io's parser. For an authoritative check matching dbdiagram exactly: `dbml2sql FILE --postgres` from [`@dbml/cli`](https://www.npmjs.com/package/@dbml/cli).

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Contributions require a DCO sign-off — see [CONTRIBUTING.md](CONTRIBUTING.md).

Man pages (`al2dbml(1)`, `al2dbml-validate(1)`) live as podman-style Markdown under
[`docs/`](docs/) and build with `go-md2man`; the `man` CI job verifies they compile.
Read one locally with `go-md2man -in docs/al2dbml.1.md | man -l -`.

Tags matching `v*` trigger a PyPI Trusted Publisher upload via `.github/workflows/publish.yml`.
