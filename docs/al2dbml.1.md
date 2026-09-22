% al2dbml 1

## NAME
al2dbml - convert a compiled Business Central AL package (.app) into DBML

## SYNOPSIS
**al2dbml** [*options*] *app*

## DESCRIPTION
**al2dbml** turns a compiled Microsoft Dynamics 365 Business Central AL
package (**.app**) into a DBML schema ready to paste into dbdiagram.io or
push to dbdocs.io. It reads **SymbolReference.json** from the archive
(tolerating AL's 40-byte header and Ready-To-Run wrappers), normalises
tables, table extensions, enums, and TableRelations, and emits one valid
DBML document with **Project**, **Table**, **Ref**, **Enum**, and
**TableGroup** blocks.

Without **--output** the DBML streams to stdout; diagnostics (stats, the
docs-loaded summary, warnings) go to stderr, so the document can be piped
cleanly.

## OPTIONS

#### **--database-type**=*name*

Value for the DBML **Project { database_type: ... }** header line. BC's
underlying storage is SQL Server, so the default is **MSSQL**. Pass an empty
string to omit the line; dbdocs.io uses it as the engine label on the
rendered schema.

#### **--docs**, **-d**=*dir*

Overlay aldoc-generated YAML documentation onto the diagram: each Table
block gains a **Note { ... }** body from the table's AL summary, and column
notes lead with the AL ToolTip text instead of the bare caption. Produce the
directory once per release with **aldoc generate** *app* **-o** *dir*.
Coverage is uneven in real BC packages; missing entries fall back to the
caption-based note.

#### **--enum-schema**=*name*

Schema to render **Enum** declarations under (default **meta**). BC enums
are AL-language metadata, not SQL objects, so by default they live apart
from the table schema.

#### **--exclude**=*pattern*

Drop tables whose name matches *pattern* (fnmatch glob). Applied after
**--include**; exclude wins over include. May be specified multiple times.

#### **--group**, **-g**=*name*=*pattern*[,*pattern*...]

Add an explicit grouping rule: tables matching any *pattern* land in
TableGroup *name*. May be specified multiple times. Explicit rules win over
the automatic source selected by **--group-by**.

#### **--group-by**=*namespace* | *word* | *none*

How to derive group names when no explicit **--group** rule matches
(default **namespace**). **namespace** uses the last segment of the AL
namespace path, falling back to the first word for un-namespaced tables;
**word** uses the first whitespace-separated word; **none** disables
auto-grouping entirely.

#### **--help**, **-h**

Print usage statement.

#### **--include**=*pattern*

Keep only tables whose name matches at least one *pattern* (fnmatch glob).
May be specified multiple times. References into a filtered-out table
degrade to cross-package notes on the source column.

#### **--merge-extensions**, **--no-merge-extensions**

Merge TableExtensions into their target tables (the default), or emit them
as separate *Target* **(Extension)** stub tables.

#### **--min-group-size**=*n*

Drop TableGroups containing fewer than *n* tables (default **2**; use **1**
to keep singletons).

#### **--no-groups**

Do not emit any **TableGroup** blocks.

#### **--output**, **-o**=*file*

Write the DBML document to *file* instead of stdout. A short confirmation
with the byte count goes to stderr.

#### **--stats**

Print object counts (tables, columns, enums, refs, groups) to stderr. When
used without **--output**, the expensive DBML render is skipped entirely,
making this a fast probe for any .app.

#### **--table-schema**=*name*

Schema to render **Table** declarations under (default **dbo**, matching
BC's SQL Server).

#### **--version**

Print the version.

## EXAMPLES

Convert a package and write the schema next to it:

```
al2dbml MyApp.app -o schema.dbml
```

Probe a package without rendering:

```
al2dbml MyApp.app --stats
```

Only the sales tables, grouped by first word:

```
al2dbml MyApp.app --include "Sales*" --group-by word -o sales.dbml
```

Enrich column notes with the real BC documentation:

```
aldoc generate MyApp.app -o ./myapp-docs/
al2dbml MyApp.app -d ./myapp-docs/ -o schema.dbml
```

## SEE ALSO
**al2dbml-validate**(1), **aldoc**(1)

Project home: https://github.com/panda-coop/al2dbml
