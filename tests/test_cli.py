from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from al2dbml.__main__ import main

from .fixtures.sample_symbols import sample_symbols


def _make_app(tmp_path: Path, name: str = "sample.app") -> Path:
    payload = json.dumps(sample_symbols()).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SymbolReference.json", payload)
    app = tmp_path / name
    app.write_bytes(buf.getvalue())
    return app


def test_help_mentions_group_option() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "--group" in result.output
    assert "APP" in result.output


def test_help_sections_appear_in_podman_order() -> None:
    # The Red Hat CLI layout: one-line summary first, then the
    # Description / Usage / Examples / Options sections in that order.
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    lines = result.output.splitlines()
    assert lines[0] == "Convert a compiled Business Central AL package (.app) into DBML"
    headers = ("Description:", "Usage:", "Examples:", "Options:")
    positions = [result.output.index(h) for h in headers]
    assert positions == sorted(positions)
    assert "  al2dbml [options] APP" in lines


def test_help_lists_every_option() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for flag in (
        "--database-type",
        "-d, --docs",
        "--enum-schema",
        "--exclude",
        "-g, --group",
        "--group-by",
        "-h, --help",
        "--include",
        "--merge-extensions",
        "--min-group-size",
        "--no-groups",
        "-o, --output",
        "--stats",
        "--table-schema",
        "--version",
    ):
        assert flag in result.output, f"missing from --help: {flag}"


def test_help_options_are_alphabetical_and_aligned() -> None:
    # Long-only options indent to the long-flag column (6 spaces) so every
    # '--' lines up under the short-flag entries, and the flat list sorts
    # alphabetically by long name — both podman conventions.
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    options_block = result.output.split("Options:\n", 1)[1]
    flags = []
    for line in options_block.splitlines():
        if line.startswith("  -") and not line.startswith("      "):
            flags.append(line.split(", --", 1)[1].split()[0])
        elif line.startswith("      --"):
            flags.append(line.strip().split()[0].lstrip("-"))
    assert flags == sorted(flags)
    assert len(flags) == 15


def test_help_shows_defaults() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    for default in ("(default: MSSQL)", "(default: dbo)", "(default: meta)", "(default: 2)"):
        assert default in result.output


def test_output_to_file_prints_to_stderr(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    out = tmp_path / "schema.dbml"
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "-o", str(out)])
    assert result.exit_code == 0, result.stderr
    assert result.stdout == ""
    assert f"wrote {out}" in result.stderr
    body = out.read_text(encoding="utf-8")
    assert 'Table "dbo"."Customer"' in body


def test_default_output_goes_to_stdout(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app)])
    assert result.exit_code == 0, result.stderr
    assert 'Enum "meta"."Customer Type"' in result.stdout
    assert 'TableGroup "Sales"' in result.stdout
    # POSIX convention: end with exactly one newline. Without it, zsh shows
    # a trailing '%' marker. With two, we'd be producing extra blank lines.
    assert result.stdout.endswith("\n")
    assert not result.stdout.endswith("\n\n")


def test_file_output_ends_with_single_newline(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    out = tmp_path / "schema.dbml"
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "-o", str(out)])
    assert result.exit_code == 0, result.stderr
    body = out.read_text(encoding="utf-8")
    assert body.endswith("\n")
    assert not body.endswith("\n\n")


def test_explicit_group_rule(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "-g", "Sales=Sales*"])
    assert result.exit_code == 0
    assert 'TableGroup "Sales"' in result.stdout


def test_no_groups_flag(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "--no-groups"])
    assert result.exit_code == 0
    assert "TableGroup" not in result.stdout


def test_no_merge_extensions(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "--no-merge-extensions"])
    assert result.exit_code == 0
    assert 'Table "dbo"."Customer (Extension)"' in result.stdout


def test_invalid_group_rule_exits_nonzero(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "-g", "noequals"])
    assert result.exit_code != 0
    assert "group" in result.stderr.lower()


def test_missing_input_file_exits_nonzero(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, [str(tmp_path / "missing.app")])
    assert result.exit_code != 0


def test_version_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "al2dbml" in result.output


def test_min_group_size_zero_rejected(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "--min-group-size", "0"])
    assert result.exit_code != 0


def test_include_flag_filters_tables(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "--include", "Sales*"])
    assert result.exit_code == 0, result.stderr
    assert 'Table "dbo"."Sales Header"' in result.stdout
    assert 'Table "dbo"."Customer"' not in result.stdout
    assert 'Table "dbo"."Purchase Header"' not in result.stdout


def test_exclude_flag_drops_tables(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "--exclude", "Purchase*"])
    assert result.exit_code == 0, result.stderr
    assert 'Table "dbo"."Sales Header"' in result.stdout
    assert 'Table "dbo"."Purchase Header"' not in result.stdout


def test_docs_flag_overlays_aldoc_descriptions(tmp_path: Path) -> None:
    # The fixture's aldoc tree describes 'Test Table.No.' as 'Specifies the
    # unique number of the record.'. Pair it with an .app fixture that has
    # the same table/field shape and the rendered DBML carries that prose.
    payload = json.dumps(
        {
            "Tables": [
                {
                    "Name": "Test Table",
                    "Fields": [
                        {
                            "Name": "No.",
                            "TypeDefinition": {"Name": "Code", "TypeArguments": [20]},
                        }
                    ],
                    "Keys": [{"FieldNames": ["No."]}],
                }
            ]
        }
    ).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SymbolReference.json", payload)
    app = tmp_path / "tt.app"
    app.write_bytes(buf.getvalue())

    aldoc_dir = Path(__file__).parent / "fixtures" / "aldoc_sample"

    runner = CliRunner()
    result = runner.invoke(main, [str(app), "--docs", str(aldoc_dir)])
    assert result.exit_code == 0, result.stderr
    assert "Specifies the unique number of the record." in result.stdout
    # And the table summary lands as the Table Note
    assert "A test table for fixtures." in result.stdout
    # Stderr summary line announces what we loaded
    assert "loaded docs for" in result.stderr


def test_docs_short_flag_dash_d_works(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    aldoc_dir = Path(__file__).parent / "fixtures" / "aldoc_sample"
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "-d", str(aldoc_dir)])
    assert result.exit_code == 0, result.stderr
    assert "loaded docs for" in result.stderr


def test_docs_flag_missing_directory_fails_with_clean_error(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "--docs", str(tmp_path / "nope")])
    assert result.exit_code != 0
    # click validates --docs with exists=True, so the error comes from click
    # itself rather than our load_docs.
    assert "does not exist" in result.stderr.lower() or "no such" in result.stderr.lower()


def test_stats_flag_prints_counts_to_stderr(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "--stats"])
    assert result.exit_code == 0, result.stderr
    # counts go to stderr so they don't pollute the DBML on stdout
    assert "tables=" in result.stderr
    assert "enums=" in result.stderr
    assert "refs=" in result.stderr
    assert "tables=" not in result.stdout


def test_stats_alone_skips_dbml_render(tmp_path: Path) -> None:
    # When --stats is the only output mode (no -o), we should not pay the cost
    # of pydbml's O(n^2) render; stdout stays empty and only stderr gets used.
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "--stats"])
    assert result.exit_code == 0
    assert result.stdout == ""  # no DBML on stdout in stats-only mode
    assert "tables=" in result.stderr


def test_stats_with_output_still_writes_file(tmp_path: Path) -> None:
    # If -o is given alongside --stats, we still need the rendered DBML.
    app = _make_app(tmp_path)
    out = tmp_path / "schema.dbml"
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "--stats", "-o", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    body = out.read_text(encoding="utf-8")
    assert 'Table "dbo"."Customer"' in body
    assert "tables=" in result.stderr


def test_empty_output_emits_warning(tmp_path: Path) -> None:
    # An .app that defines no tables and no enums (e.g. a codeunit-only
    # extension like Microsoft's Sales and Inventory Forecast).
    payload = json.dumps({"Codeunits": [{"Name": "X"}]}).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SymbolReference.json", payload)
    empty_app = tmp_path / "empty.app"
    empty_app.write_bytes(buf.getvalue())

    runner = CliRunner()
    result = runner.invoke(main, [str(empty_app)])
    assert result.exit_code == 0, result.stderr
    assert "warning:" in result.stderr.lower()
    assert "0 tables" in result.stderr.lower()


def test_no_warning_when_tables_present(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app)])
    assert result.exit_code == 0, result.stderr
    assert "warning" not in result.stderr.lower()


@pytest.mark.parametrize("ext", ["badapp"])
def test_bad_archive_reports_useful_error(tmp_path: Path, ext: str) -> None:
    bad = tmp_path / f"{ext}.app"
    bad.write_bytes(b"not a real zip")
    runner = CliRunner()
    result = runner.invoke(main, [str(bad)])
    assert result.exit_code != 0


def test_database_type_flag_overrides_default(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app), "--database-type", "PostgreSQL"])
    assert result.exit_code == 0, result.stderr
    assert "database_type: 'PostgreSQL'" in result.stdout
    assert "database_type: 'MSSQL'" not in result.stdout


def test_database_type_default_is_mssql(tmp_path: Path) -> None:
    # MSSQL is the right default for any BC .app — confirm we don't
    # silently drop the database_type item when the flag is left out.
    app = _make_app(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, [str(app)])
    assert result.exit_code == 0, result.stderr
    assert "database_type: 'MSSQL'" in result.stdout
