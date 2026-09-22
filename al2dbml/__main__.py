from __future__ import annotations

from pathlib import Path
from typing import cast

import click
from click.formatting import wrap_text

from . import __version__
from .aldoc import AldocDocs, load_docs
from .diagram import Diagram
from .grouping import GroupingConfig, GroupSource, parse_rule_strings

_SUMMARY = "Convert a compiled Business Central AL package (.app) into DBML"

_DESCRIPTION = (
    "Reads SymbolReference.json from the .app archive and emits one valid "
    "DBML document with Project, Table, Ref, Enum and TableGroup blocks, "
    "ready to paste into dbdiagram.io or push to dbdocs.io."
)

_EXAMPLES = [
    "al2dbml MyApp.app -o schema.dbml",
    'al2dbml MyApp.app --include "Sales*" --stats',
    "al2dbml MyApp.app -d ./myapp-docs/ -o schema.dbml",
]


class _RedHatHelpCommand(click.Command):
    """Render ``--help`` in the section layout Red Hat CLIs use.

    Mirrors the Cobra help format of podman/buildah/skopeo: a one-line
    summary, then ``Description:`` / ``Usage:`` / ``Examples:`` /
    ``Options:`` sections, with the options as one flat alphabetical
    two-column list — short flags aligned left, long-only flags indented
    to the long-flag column, defaults appended in parentheses. Only
    ``format_help`` is overridden; usage lines in error messages keep
    click's default rendering.
    """

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        width = formatter.width or 80
        formatter.write(f"{_SUMMARY}\n\n")
        formatter.write("Description:\n")
        formatter.write(wrap_text(_DESCRIPTION, width, initial_indent="  ", subsequent_indent="  "))
        formatter.write("\n\nUsage:\n")
        formatter.write(f"  {ctx.command_path} [options] APP\n\n")
        formatter.write("Examples:\n")
        for example in _EXAMPLES:
            formatter.write(f"  {example}\n")
        formatter.write("\nOptions:\n")
        self._write_options(ctx, formatter, width)

    def _write_options(
        self, ctx: click.Context, formatter: click.HelpFormatter, width: int
    ) -> None:
        rows = sorted(
            (
                self._option_row(param)
                for param in self.get_params(ctx)
                if isinstance(param, click.Option)
            ),
            key=lambda row: row[2],
        )
        # Description column: 3 spaces past the widest flag cell, podman-style.
        help_col = max(len(flags) for flags, _, _ in rows) + 3
        for flags, help_text, _ in rows:
            wrapped = wrap_text(
                help_text,
                width,
                initial_indent=" " * help_col,
                subsequent_indent=" " * help_col,
            )
            formatter.write(f"{flags:<{help_col}}{wrapped.lstrip()}".rstrip() + "\n")

    @staticmethod
    def _option_row(opt: click.Option) -> tuple[str, str, str]:
        """Build one (flag-cell, help-text, sort-key) row for the Options list."""
        shorts = [o for o in opt.opts if not o.startswith("--")]
        longs = [o for o in opt.opts if o.startswith("--")]
        # Short+long options start at column 2; long-only options indent to
        # the long-flag column so every '--' lines up (podman's alignment).
        cell = f"  {shorts[0]}, {longs[0]}" if shorts else f"      {longs[0]}"
        if opt.metavar and not opt.is_flag:
            cell += f" {opt.metavar.lower()}"

        help_text = opt.help or ""
        if opt.show_default and not opt.is_flag and opt.default is not None:
            help_text = f"{help_text} (default: {opt.default})"
        return cell, help_text, longs[0].lstrip("-")


@click.command(
    "al2dbml", cls=_RedHatHelpCommand, context_settings={"help_option_names": ["-h", "--help"]}
)
@click.argument(
    "app",
    type=click.Path(exists=True, dir_okay=False, file_okay=True, path_type=Path),
)
@click.option(
    "-o",
    "--output",
    "output",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    default=None,
    metavar="FILE",
    help="Write DBML to FILE instead of stdout.",
)
@click.option(
    "--merge-extensions/--no-merge-extensions",
    default=True,
    help=(
        "Merge TableExtensions into their target tables; "
        "--no-merge-extensions emits separate stub tables (default: merge)."
    ),
)
@click.option(
    "-g",
    "--group",
    "groups",
    multiple=True,
    metavar="NAME=PATTERN",
    help="Add an explicit grouping rule; patterns comma-separated. Repeatable.",
)
@click.option(
    "--no-groups",
    is_flag=True,
    default=False,
    help="Do not emit any TableGroup blocks.",
)
@click.option(
    "--group-by",
    "group_by",
    type=click.Choice(["namespace", "word", "none"], case_sensitive=False),
    default="namespace",
    show_default=True,
    metavar="SOURCE",
    help=(
        "Group-name source when no explicit --group rule matches: "
        "'namespace' uses the last AL namespace segment (first-word "
        "fallback for un-namespaced tables), 'word' the first "
        "whitespace-separated word, 'none' disables auto-grouping."
    ),
)
@click.option(
    "--min-group-size",
    type=click.IntRange(min=1),
    default=2,
    show_default=True,
    metavar="N",
    help="Drop groups containing fewer than N tables.",
)
@click.option(
    "--table-schema",
    "table_schema",
    metavar="NAME",
    default="dbo",
    show_default=True,
    help="Schema to render Table declarations under; BC's SQL Server uses 'dbo'.",
)
@click.option(
    "--enum-schema",
    "enum_schema",
    metavar="NAME",
    default="meta",
    show_default=True,
    help="Schema to render Enum declarations under; BC enums are AL metadata, not SQL objects.",
)
@click.option(
    "-d",
    "--docs",
    "docs_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    metavar="DIR",
    help=(
        "Overlay field descriptions and table summaries from an "
        "'aldoc generate <app> -o DIR' output directory."
    ),
)
@click.option(
    "--include",
    "includes",
    multiple=True,
    metavar="PATTERN",
    help="Only keep tables whose name matches at least one PATTERN (fnmatch). Repeatable.",
)
@click.option(
    "--exclude",
    "excludes",
    multiple=True,
    metavar="PATTERN",
    help="Drop tables whose name matches any PATTERN (fnmatch), after --include. Repeatable.",
)
@click.option(
    "--database-type",
    "database_type",
    metavar="NAME",
    default="MSSQL",
    show_default=True,
    help=(
        "Engine label for the DBML 'Project { database_type: ... }' header; "
        "pass an empty string to omit the line."
    ),
)
@click.option(
    "--stats",
    "show_stats",
    is_flag=True,
    default=False,
    help=(
        "Print object counts (tables, enums, refs, groups) to stderr; "
        "without -o, skips the DBML render entirely for a fast probe."
    ),
)
@click.version_option(__version__, prog_name="al2dbml")
def main(
    app: Path,
    output: Path | None,
    merge_extensions: bool,
    groups: tuple[str, ...],
    no_groups: bool,
    group_by: str,
    min_group_size: int,
    table_schema: str,
    enum_schema: str,
    docs_dir: Path | None,
    includes: tuple[str, ...],
    excludes: tuple[str, ...],
    database_type: str,
    show_stats: bool,
) -> None:
    """Convert a compiled AL package APP into a DBML schema."""
    try:
        rules = parse_rule_strings(groups)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="-g/--group") from exc

    # Safe cast: click.Choice(['namespace', 'word', 'none']) above
    # constrains group_by to one of those three strings before we get
    # here, so .lower() always yields a valid GroupSource literal.
    source = cast(GroupSource, group_by.lower())
    grouping = GroupingConfig(
        enabled=not no_groups,
        rules=rules,
        source=source,
        min_group_size=min_group_size,
    )

    docs = AldocDocs()
    if docs_dir is not None:
        try:
            docs = load_docs(docs_dir)
        except FileNotFoundError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(
            f"loaded docs for {len(docs.table_summaries)} tables, "
            f"{len(docs.field_descriptions)} fields",
            err=True,
        )

    # If the user only wants stats (no -o and no DBML stream to consumers),
    # skip the expensive DBML render entirely; build() alone is O(n) while
    # the pydbml render path is O(n^2) on table count.
    needs_render = output is not None or not show_stats

    # Only the from_app() call can raise FileNotFoundError (.app missing)
    # or KeyError (SymbolReference.json missing from the archive); keep the
    # try-block scoped to it so a hypothetical exception from the build or
    # render phases bubbles up instead of being misreported as a load error.
    try:
        diagram = Diagram.from_app(
            app,
            merge_extensions=merge_extensions,
            grouping=grouping,
            table_schema=table_schema,
            enum_schema=enum_schema,
            includes=list(includes),
            excludes=list(excludes),
            docs=docs,
            database_type=database_type,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc

    if needs_render:
        rendered: str | None = diagram.dbml()
    else:
        diagram.build()
        rendered = None

    counts = diagram.stats()
    if show_stats:
        click.echo(
            ", ".join(f"{name}={value}" for name, value in counts.items()),
            err=True,
        )
    if counts["tables"] == 0 and counts["enums"] == 0:
        click.echo(
            "warning: parsed 0 tables and 0 enums — output is effectively empty",
            err=True,
        )

    if rendered is None:
        return

    # POSIX text-file convention: terminate output with a newline. Without it,
    # zsh shows a trailing '%' marker after stdout output. pydbml's renderer
    # does not append one itself.
    if not rendered.endswith("\n"):
        rendered = rendered + "\n"

    if output is not None:
        output.write_text(rendered, encoding="utf-8")
        click.echo(f"wrote {output} ({len(rendered)} bytes)", err=True)
    else:
        click.echo(rendered, nl=False)


if __name__ == "__main__":
    main()
