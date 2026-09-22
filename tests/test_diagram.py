from __future__ import annotations

import pytest

from al2dbml import relations
from al2dbml._build.context import PendingRef
from al2dbml.diagram import Diagram
from al2dbml.grouping import GroupingConfig

from .fixtures.sample_symbols import sample_symbols


def _build(**kwargs) -> str:
    gen = Diagram(symbols=sample_symbols(), **kwargs)
    return gen.dbml()


def test_enum_includes_extension_values() -> None:
    dbml = _build()
    assert 'Enum "meta"."Customer Type"' in dbml
    assert "Person" in dbml
    assert "Company" in dbml
    assert "Government" in dbml


def test_customer_table_contains_merged_extension_field() -> None:
    dbml = _build()
    # The extension field appears as a column on the base Customer table
    assert '"Loyalty Points" int' in dbml
    # And the Customer table block exists (schema-qualified, dbo by default)
    assert 'Table "dbo"."Customer"' in dbml


def test_sales_header_references_customer_no() -> None:
    dbml = _build()
    # pydbml emits each reference as a ``Ref { ... }`` block
    assert "Ref {" in dbml
    assert '"dbo"."Sales Header"."Sell-to Customer No." > "dbo"."Customer"."No."' in dbml


def test_sales_line_references_sales_header_no() -> None:
    dbml = _build()
    assert '"dbo"."Sales Line"."Document No." > "dbo"."Sales Header"."No."' in dbml


def test_table_groups_emitted_for_sales_and_purchase() -> None:
    dbml = _build()
    assert 'TableGroup "Sales"' in dbml
    assert '"Sales Header"' in dbml
    assert '"Sales Line"' in dbml
    assert 'TableGroup "Purchase"' in dbml
    assert '"Purchase Header"' in dbml
    assert '"Purchase Line"' in dbml


def test_no_table_group_for_lone_customer() -> None:
    dbml = _build()
    assert 'TableGroup "Customer"' not in dbml


def test_conditional_relation_note_strips_where_keyword() -> None:
    dbml = _build()
    # Note renders as Markdown: bold label, code-spanned expression
    assert '**Condition:** `("Blocked"=CONST(" "))`' in dbml
    assert "WHERE(WHERE" not in dbml
    assert 'WHERE("Blocked"' not in dbml  # raw WHERE form should not survive


def test_merge_extensions_false_emits_stub_table() -> None:
    dbml = _build(merge_extensions=False)
    assert 'Table "dbo"."Customer (Extension)"' in dbml
    assert '"Loyalty Points"' in dbml
    # The base Customer table should not have Loyalty Points
    customer_block_start = dbml.index('Table "dbo"."Customer" ')
    customer_block_end = dbml.index("}", customer_block_start)
    customer_block = dbml[customer_block_start:customer_block_end]
    assert "Loyalty Points" not in customer_block


def test_cross_package_reference_does_not_crash_and_is_noted() -> None:
    dbml = _build()
    # Sales Line.Vendor No. -> Vendor (Vendor table is not in this fixture).
    # Note renders as Markdown: bold 'References' label and code-spanned target.
    assert '"Vendor No."' in dbml
    assert '**References** `Vendor."No."` (cross-package)' in dbml


def test_if_else_emits_one_ref_per_branch_with_if_condition_comment() -> None:
    # Each conditional branch produces its own Ref block, and the IF condition
    # is carried as a pydbml '//' comment so the diagram explains why each
    # arrow exists. WHERE clauses (per-branch filters) attach to the same line.
    dbml = _build()
    # Item branch — no per-branch WHERE
    assert "// when (Type=CONST(Item))" in dbml
    assert '"dbo"."Sales Line"."Source No." > "dbo"."Item"."No."' in dbml
    # Resource branch — also no per-branch WHERE
    assert "// when (Type=CONST(Resource))" in dbml
    assert '"dbo"."Sales Line"."Source No." > "dbo"."Resource"."No."' in dbml


def test_non_conditional_ref_has_no_comment() -> None:
    # Sales Header.Sell-to Customer No. -> Customer is a plain TableRelation
    # (no IF, just a WHERE). The Ref's comment carries only the WHERE.
    dbml = _build()
    # Sample fixture has WHERE("Blocked"=CONST(" ")) on Sell-to Customer No.
    assert 'where ("Blocked"=CONST(" "))' in dbml
    # And a plain Document No. -> Sales Header.No. ref has NO WHERE and NO IF,
    # so no '//' comment line precedes its Ref block.
    document_no_ref = 'Ref {\n    "dbo"."Sales Line"."Document No." > "dbo"."Sales Header"."No."\n}'
    assert document_no_ref in dbml


def test_if_else_branches_render_with_html_line_breaks() -> None:
    dbml = _build()
    # IF/ELSE branches each go on their own visual line via <br>; dbdiagram
    # and dbdocs render that as a real line break while pydbml's textwrap
    # indent (which would break a real \n) doesn't touch a single-line note.
    assert (
        "**Conditional reference:**<br>"
        '• `IF (Type=CONST(Item))` → `Item."No."`<br>'
        '• `IF (Type=CONST(Resource))` → `Resource."No."`'
    ) in dbml


def test_cross_package_references_are_deduped_per_column() -> None:
    # A multi-branch IF/ELSE whose branches all point to the SAME missing
    # target should leave one cross-package note, not N. Real example from
    # Base Application: a 6-branch IF chain all resolving to 'Bin Content'.
    symbols = {
        "Tables": [
            {
                "Name": "S",
                "Fields": [
                    {
                        "Name": "ref",
                        "TypeDefinition": {"Name": "Integer"},
                        "Properties": [
                            {
                                "Name": "TableRelation",
                                "Value": (
                                    'IF (a = const(1)) Missing."x" '
                                    'ELSE IF (a = const(2)) Missing."x" '
                                    'ELSE IF (a = const(3)) Missing."x"'
                                ),
                            }
                        ],
                    }
                ],
                "Keys": [{"FieldNames": ["ref"]}],
            }
        ]
    }
    dbml = Diagram(symbols=symbols).dbml()
    # The 'References Missing."x" (cross-package)' string should appear once,
    # not three times, even though three branches independently target Missing.
    assert dbml.count("(cross-package)") == 1


def test_aldoc_table_summary_becomes_table_note() -> None:
    from al2dbml.aldoc import AldocDocs

    docs = AldocDocs(table_summaries={"Customer": "Stores customer master data."})
    dbml = Diagram(symbols=sample_symbols(), docs=docs).dbml()
    # The Table block gains a Note { ... } body sourced from aldoc, replacing
    # the bare 'Customer' caption that was used before.
    assert "Stores customer master data." in dbml


def test_aldoc_field_description_replaces_caption_in_column_note() -> None:
    from al2dbml.aldoc import AldocDocs

    docs = AldocDocs(field_descriptions={("Customer", "Email"): "Primary contact email."})
    dbml = Diagram(symbols=sample_symbols(), docs=docs).dbml()
    # The aldoc description takes the column-note slot
    assert "Primary contact email." in dbml


def test_aldoc_description_takes_priority_over_caption() -> None:
    from al2dbml.aldoc import AldocDocs

    # Email field in the fixture has caption that differs from name; without
    # aldoc it would render as the caption. With aldoc the description wins.
    symbols = {
        "Tables": [
            {
                "Name": "T",
                "Fields": [
                    {
                        "Name": "x",
                        "TypeDefinition": {"Name": "Integer"},
                        "Properties": [{"Name": "Caption", "Value": "Caption text"}],
                    }
                ],
                "Keys": [{"FieldNames": ["x"]}],
            }
        ]
    }
    docs = AldocDocs(field_descriptions={("T", "x"): "Description text from aldoc."})
    dbml = Diagram(symbols=symbols, docs=docs).dbml()
    assert "Description text from aldoc." in dbml
    assert "Caption text" not in dbml


def test_no_aldoc_docs_preserves_existing_caption_behaviour() -> None:
    # When docs is the default empty AldocDocs, captions still appear when
    # they differ from the field name (existing behaviour, not regressed).
    dbml = Diagram(symbols=sample_symbols()).dbml()
    # Customer is the only fixture table with a caption that equals its name
    # for every field; the rendered DBML should be unchanged from pre-aldoc.
    assert "Customer" in dbml
    # And we have NOT accidentally pulled in any aldoc description text.
    assert "Description text from aldoc" not in dbml


def test_column_note_section_order_caption_then_condition_then_references() -> None:
    # When a single column triggers multiple note sections (caption that
    # differs from name + WHERE condition + cross-package reference), they
    # join with the '<br><br>' paragraph separator in a stable order:
    #   caption  →  Condition  →  References
    # If a future refactor reorders the sections, this catches it.
    symbols = {
        "Tables": [
            {
                "Name": "T",
                "Fields": [
                    {
                        "Name": "fld",
                        "TypeDefinition": {"Name": "Code", "TypeArguments": [20]},
                        "Properties": [
                            {"Name": "Caption", "Value": "Friendly Label"},
                            {
                                "Name": "TableRelation",
                                "Value": 'Missing."x" WHERE("y"=CONST(true))',
                            },
                        ],
                    }
                ],
                "Keys": [{"FieldNames": ["fld"]}],
            }
        ]
    }
    dbml = Diagram(symbols=symbols).dbml()
    # Extract just this field's note line and verify all three sections
    # appear in that order on one physical line.
    note_line = next(line for line in dbml.splitlines() if '"fld"' in line)
    caption_pos = note_line.index("Friendly Label")
    condition_pos = note_line.index("**Condition:**")
    refs_pos = note_line.index("**References**")
    assert caption_pos < condition_pos < refs_pos, note_line
    # And the separators between sections are the paragraph '<br><br>'
    assert note_line.count("<br><br>") >= 2


def test_caption_equal_to_name_is_not_emitted_as_note() -> None:
    # 96% of Base Application fields have caption == name; emitting that as
    # a note is pure noise. Only different captions should appear.
    symbols = {
        "Tables": [
            {
                "Name": "T",
                "Fields": [
                    {
                        "Name": "MatchesCaption",
                        "TypeDefinition": {"Name": "Integer"},
                        "Properties": [{"Name": "Caption", "Value": "MatchesCaption"}],
                    },
                    {
                        "Name": "DifferentCaption",
                        "TypeDefinition": {"Name": "Integer"},
                        "Properties": [{"Name": "Caption", "Value": "Different label"}],
                    },
                ],
                "Keys": [{"FieldNames": ["MatchesCaption"]}],
            }
        ]
    }
    dbml = Diagram(symbols=symbols).dbml()
    assert "[note: 'MatchesCaption']" not in dbml
    assert "[note: 'Different label']" in dbml


def test_disabled_grouping_emits_no_table_groups() -> None:
    dbml = _build(grouping=GroupingConfig(enabled=False))
    assert "TableGroup" not in dbml


def test_pending_refs_are_collected() -> None:
    gen = Diagram(symbols=sample_symbols())
    gen.build()
    targets = {(r.source_table, r.source_field, r.target_table) for r in gen.context.pending_refs}
    assert ("Sales Header", "Sell-to Customer No.", "Customer") in targets
    assert ("Sales Line", "Document No.", "Sales Header") in targets
    assert ("Sales Line", "Vendor No.", "Vendor") in targets


def test_from_app_classmethod_has_docstring() -> None:
    # Smoke check: the public API is importable and documented.
    assert Diagram.from_app.__doc__ is not None
    assert "compiled" in Diagram.from_app.__doc__.lower()


def test_parse_relation_string_dict_form() -> None:
    table, field, cond = relations.parse_relation_string(
        {"Table": "Customer", "Field": "No.", "Condition": '("Blocked"=CONST(""))'}
    )
    assert (table, field, cond) == (
        "Customer",
        "No.",
        '("Blocked"=CONST(""))',
    )


def test_parse_relation_string_quoted_qualified_with_where() -> None:
    table, field, cond = relations.parse_relation_string(
        '"Customer"."No." WHERE("Blocked"=CONST(" "))'
    )
    assert table == "Customer"
    assert field == "No."
    assert cond == '("Blocked"=CONST(" "))'


def test_parse_relation_string_bare_table_only() -> None:
    table, field, cond = relations.parse_relation_string("Customer")
    assert (table, field, cond) == ("Customer", None, None)


def test_parse_relation_string_nested_parens_in_condition() -> None:
    table, field, cond = relations.parse_relation_string(
        'Item."No." WHERE(Type=CONST(Item),Blocked=CONST(FALSE))'
    )
    assert table == "Item"
    assert field == "No."
    assert cond == "(Type=CONST(Item),Blocked=CONST(FALSE))"


def test_pending_ref_dataclass_is_internal() -> None:
    # Sanity: the helper dataclass is exposed for tests only.
    ref = PendingRef("A", "a", "B", "b", None)
    assert ref.target_table == "B"


def test_generate_forwards_kwargs_to_diagram_from_app(tmp_path) -> None:
    # The module-level generate() should accept the same kwargs as
    # Diagram.from_app(). Smoke-test by passing table_schema and asserting
    # it lands on the rendered output.
    import io
    import json
    import zipfile

    from al2dbml import generate

    payload = json.dumps({"Tables": [{"Name": "T", "Fields": [], "Keys": [{"FieldNames": []}]}]})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SymbolReference.json", payload.encode())
    app = tmp_path / "tiny.app"
    app.write_bytes(buf.getvalue())

    rendered = generate(app, table_schema="custom")
    assert 'Table "custom"."T"' in rendered


def test_context_property_is_lazy_and_cached() -> None:
    # First access lazily creates the BuildContext; second access returns
    # the same instance so all phases of the pipeline see the same state.
    diagram = Diagram(symbols=sample_symbols())
    ctx1 = diagram.context
    ctx2 = diagram.context
    assert ctx1 is ctx2
    # And build() must reuse the same context so context.tables matches up.
    diagram.build()
    assert diagram.context is ctx1
    assert "Customer" in diagram.context.tables


def test_context_property_has_no_setter() -> None:
    # diagram.context is a read-only inspection surface; reassigning it
    # should raise AttributeError so callers can't accidentally swap the
    # build state out from under the Diagram.
    diagram = Diagram(symbols=sample_symbols())
    with pytest.raises(AttributeError):
        diagram.context = None  # type: ignore[misc]


def test_dbml_is_idempotent() -> None:
    gen = Diagram(symbols=sample_symbols())
    first = gen.dbml()
    second = gen.dbml()
    assert first == second


def test_default_table_schema_is_dbo() -> None:
    gen = Diagram(symbols=sample_symbols())
    gen.build()
    for name in ("Customer", "Sales Header", "Sales Line"):
        assert gen.context.tables[name].schema == "dbo"


def test_table_schema_override_is_respected() -> None:
    gen = Diagram(symbols=sample_symbols(), table_schema="custom")
    gen.build()
    assert gen.context.tables["Customer"].schema == "custom"


def test_extension_stub_carries_configured_table_schema() -> None:
    gen = Diagram(symbols=sample_symbols(), merge_extensions=False, table_schema="dbo")
    gen.build()
    assert gen.context.tables["Customer (Extension)"].schema == "dbo"


def test_table_and_enum_schemas_are_independent() -> None:
    # Renaming the table schema must not bleed into the enum schema and
    # vice versa. They are deliberately separate dataclass fields.
    gen = Diagram(symbols=sample_symbols(), table_schema="alpha", enum_schema="beta")
    gen.build()
    assert gen.context.tables["Customer"].schema == "alpha"
    assert gen.context.enums["Customer Type"].schema == "beta"


def test_not_null_flag_set_when_notblank_true() -> None:
    gen = Diagram(symbols=sample_symbols())
    gen.build()
    assert gen.context.columns[("Customer", "Email")].not_null is True


def test_not_null_flag_not_set_for_pk_field() -> None:
    gen = Diagram(symbols=sample_symbols())
    gen.build()
    pk_col = gen.context.columns[("Customer", "No.")]
    assert pk_col.pk is True
    # PKs imply not-null in DBML; we deliberately leave the flag off
    assert pk_col.not_null is False


def test_secondary_single_column_key_marks_column_unique() -> None:
    gen = Diagram(symbols=sample_symbols())
    gen.build()
    assert gen.context.columns[("Customer", "Email")].unique is True


def test_multi_column_secondary_key_does_not_mark_unique() -> None:
    gen = Diagram(symbols=sample_symbols())
    gen.build()
    # Sales Header's only key is the multi-field PK; nothing should be unique.
    for fname in ("Document Type", "No.", "Sell-to Customer No."):
        col = gen.context.columns[("Sales Header", fname)]
        assert col.unique is False, f"{fname} should not be marked unique"


def test_notnull_property_alternative_spelling() -> None:
    # The canonical AL spelling is NotBlank but tolerate NotNull too.
    symbols = {
        "Tables": [
            {
                "Name": "T",
                "Fields": [
                    {
                        "Name": "x",
                        "TypeDefinition": {"Name": "Integer"},
                        "Properties": [{"Name": "NotNull", "Value": True}],
                    }
                ],
                "Keys": [{"FieldNames": ["x"]}],
            }
        ]
    }
    gen = Diagram(symbols=symbols)
    gen.build()
    # x is PK so not_null stays False (PK implies not-null in DBML already)
    assert gen.context.columns[("T", "x")].not_null is False

    # Same with a non-PK field
    symbols["Tables"][0]["Fields"].append(
        {
            "Name": "y",
            "TypeDefinition": {"Name": "Integer"},
            "Properties": [{"Name": "NotNull", "Value": True}],
        }
    )
    gen2 = Diagram(symbols=symbols)
    gen2.build()
    assert gen2.context.columns[("T", "y")].not_null is True


def test_if_else_emits_one_ref_per_branch() -> None:
    gen = Diagram(symbols=sample_symbols())
    gen.build()
    targets = {(r.source_table, r.source_field, r.target_table) for r in gen.context.pending_refs}
    assert ("Sales Line", "Source No.", "Item") in targets
    assert ("Sales Line", "Source No.", "Resource") in targets


def test_if_else_branches_carry_conditions_in_note() -> None:
    dbml = Diagram(symbols=sample_symbols()).dbml()
    # The Source No. column on Sales Line should carry per-branch notes
    assert "IF (Type=CONST(Item))" in dbml
    assert "IF (Type=CONST(Resource))" in dbml


def test_if_else_default_branch_no_condition() -> None:
    branches = relations.parse_conditional_relation('IF (Cond1) "T1"."f1" ELSE "T2"."f2"')
    assert branches is not None
    assert len(branches) == 2
    assert branches[0][0] == "(Cond1)"
    assert branches[0][1:3] == ("T1", "f1")
    assert branches[1][0] is None  # default branch has no IF condition
    assert branches[1][1:3] == ("T2", "f2")


def test_if_else_with_per_branch_where() -> None:
    branches = relations.parse_conditional_relation('IF (T=CONST(A)) Tbl."F" WHERE("X"=CONST(""))')
    assert branches is not None
    if_cond, table, field, where = branches[0]
    assert if_cond == "(T=CONST(A))"
    assert table == "Tbl"
    assert field == "F"
    assert where == '("X"=CONST(""))'


def test_if_else_unresolvable_branch_keeps_note() -> None:
    # A branch pointing to a table that isn't in the symbols still appears in the note.
    dbml = Diagram(
        symbols={
            "Tables": [
                {
                    "Name": "S",
                    "Fields": [
                        {
                            "Name": "ref",
                            "TypeDefinition": {"Name": "Integer"},
                            "Properties": [
                                {
                                    "Name": "TableRelation",
                                    "Value": 'IF (T=CONST(X)) DoesNotExist."No."',
                                }
                            ],
                        }
                    ],
                    "Keys": [{"FieldNames": ["ref"]}],
                }
            ]
        }
    ).dbml()
    assert "IF (T=CONST(X))" in dbml
    assert "DoesNotExist" in dbml


def test_non_conditional_relation_returns_none() -> None:
    # A regular table.field reference should not match the IF/ELSE form, so
    # _parse_conditional_relation returns None and the caller falls back.
    assert relations.parse_conditional_relation('"Customer"."No."') is None
    assert relations.parse_conditional_relation("Customer.No.") is None
    assert relations.parse_conditional_relation("") is None


def test_unique_flag_renders_in_dbml() -> None:
    dbml = Diagram(symbols=sample_symbols()).dbml()
    # The Email column on Customer should have both flags in some order
    # (pydbml controls the in-block ordering); assert each substring independently.
    assert '"Email" varchar(80)' in dbml
    assert "not null" in dbml.lower()
    assert "unique" in dbml.lower()


def test_dbml_starts_with_provenance_header() -> None:
    # The header is the tool tagline + project URL. Package metadata
    # (Name / Version / Publisher / AppId) lives in the Project block's
    # Note instead, so the header line itself stays short and stable.
    symbols = dict(sample_symbols())
    symbols.update(
        {
            "Name": "Sample App",
            "Version": "1.2.3.4",
            "Publisher": "ACME",
            "AppId": "00000000-0000-0000-0000-000000000001",
        }
    )
    dbml = Diagram(symbols=symbols).dbml()
    first_line, second_line, _ = dbml.split("\n", 2)
    assert first_line.startswith("// Auto-generated by AL-to-DBML v")
    assert "edits will be lost on next run" in first_line
    assert second_line == "// https://github.com/panda-coop/al2dbml"
    # Package metadata appears in the Project block's Note, not the header.
    assert "Sample App 1.2.3.4 by ACME" in dbml
    assert "AppId: 00000000-0000-0000-0000-000000000001" in dbml


def test_include_keeps_only_matching_tables() -> None:
    gen = Diagram(symbols=sample_symbols(), includes=["Sales*"])
    gen.build()
    assert "Sales Header" in gen.context.tables
    assert "Sales Line" in gen.context.tables
    assert "Customer" not in gen.context.tables
    assert "Purchase Header" not in gen.context.tables


def test_exclude_drops_matching_tables() -> None:
    gen = Diagram(symbols=sample_symbols(), excludes=["Purchase*"])
    gen.build()
    assert "Customer" in gen.context.tables
    assert "Sales Header" in gen.context.tables
    assert "Purchase Header" not in gen.context.tables
    assert "Purchase Line" not in gen.context.tables


def test_exclude_wins_over_include() -> None:
    gen = Diagram(
        symbols=sample_symbols(),
        includes=["Sales*", "Purchase*"],
        excludes=["*Line*"],
    )
    gen.build()
    assert "Sales Header" in gen.context.tables
    assert "Purchase Header" in gen.context.tables
    assert "Sales Line" not in gen.context.tables
    assert "Purchase Line" not in gen.context.tables


def test_ref_to_filtered_target_degrades_to_note() -> None:
    # Customer is filtered out; Sales Header.Sell-to Customer No. -> Customer
    # should degrade to a cross-package note rather than producing a Ref.
    gen = Diagram(symbols=sample_symbols(), excludes=["Customer"])
    dbml = gen.dbml()
    assert 'Table "dbo"."Customer"' not in dbml
    # The cross-package note path runs when the target table is missing.
    assert "cross-package" in dbml.lower()


def test_default_enum_schema_is_meta() -> None:
    # Enums live in their own schema by default ('meta') because BC enums are
    # AL-language metadata, not SQL objects. Separate from the table schema.
    gen = Diagram(symbols=sample_symbols())
    gen.build()
    assert gen.context.enums["Customer Type"].schema == "meta"


def test_enum_schema_override_is_respected() -> None:
    gen = Diagram(symbols=sample_symbols(), enum_schema="custom")
    gen.build()
    assert gen.context.enums["Customer Type"].schema == "custom"


def test_enum_rendered_with_meta_schema_prefix() -> None:
    dbml = Diagram(symbols=sample_symbols()).dbml()
    assert 'Enum "meta"."Customer Type"' in dbml
    # And the column type that references the enum carries the same prefix
    assert '"Type" "meta"."Customer Type"' in dbml


def test_enum_items_carry_ordinal_as_note() -> None:
    # AL omits Ordinal=0; values from the fixture: Person ordinal 0,
    # Company ordinal 1, Government ordinal 10 (from the extension).
    gen = Diagram(symbols=sample_symbols())
    gen.build()
    items = {i.name: i.note.text for i in gen.context.enums["Customer Type"].items}
    assert items == {"Person": "0", "Company": "1", "Government": "10"}


def test_enum_ordinals_render_in_dbml() -> None:
    dbml = Diagram(symbols=sample_symbols()).dbml()
    assert "\"Person\" [note: '0']" in dbml
    assert "\"Company\" [note: '1']" in dbml
    assert "\"Government\" [note: '10']" in dbml


def test_empty_enum_value_substituted_with_single_space() -> None:
    # AL sometimes encodes the default/blank slot as "" which breaks DBML's
    # parser. We substitute a single space so the slot still appears.
    symbols = {
        "EnumTypes": [
            {
                "Name": "Blocked",
                "Values": [
                    {"Name": ""},
                    {"Name": "Ship"},
                    {"Name": "All"},
                ],
            }
        ]
    }
    gen = Diagram(symbols=symbols)
    gen.build()
    item_names = [i.name for i in gen.context.enums["Blocked"].items]
    assert item_names == [" ", "Ship", "All"]


def test_single_space_enum_value_passes_through() -> None:
    # The other direction: an explicit " " value is preserved as-is.
    symbols = {
        "EnumTypes": [
            {
                "Name": "Type",
                "Values": [{"Name": " "}, {"Name": "Item"}],
            }
        ]
    }
    gen = Diagram(symbols=symbols)
    gen.build()
    item_names = [i.name for i in gen.context.enums["Type"].items]
    assert item_names == [" ", "Item"]


def test_enum_extension_empty_value_also_substituted() -> None:
    # Same rule applies to EnumExtension values.
    symbols = {
        "EnumTypes": [{"Name": "E", "Values": [{"Name": "A"}]}],
        "EnumExtensionTypes": [{"TargetObject": "E", "Values": [{"Name": ""}, {"Name": "B"}]}],
    }
    gen = Diagram(symbols=symbols)
    gen.build()
    item_names = [i.name for i in gen.context.enums["E"].items]
    assert item_names == ["A", " ", "B"]


def test_self_referential_relation_is_skipped() -> None:
    # Real-world AL has fields with TableRelation pointing at the same column
    # they live on (e.g. 'Production Order.No.' -> 'Production Order.No.').
    # Such a Ref carries no information; drop it instead of emitting noise.
    symbols = {
        "Tables": [
            {
                "Name": "Production Order",
                "Fields": [
                    {
                        "Name": "No.",
                        "TypeDefinition": {"Name": "Code", "TypeArguments": [20]},
                        "Properties": [
                            {
                                "Name": "TableRelation",
                                "Value": '"Production Order"."No."',
                            }
                        ],
                    }
                ],
                "Keys": [{"FieldNames": ["No."]}],
            }
        ]
    }
    dbml = Diagram(symbols=symbols).dbml()
    # No Ref block should be emitted at all
    assert "Ref {" not in dbml
    # The table itself is still present
    assert 'Table "dbo"."Production Order"' in dbml


def test_filter_drops_tables_from_groups() -> None:
    gen = Diagram(symbols=sample_symbols(), excludes=["Sales*"])
    dbml = gen.dbml()
    assert 'TableGroup "Sales"' not in dbml


def test_dbml_header_works_without_metadata() -> None:
    # The two-line tagline header is always present regardless of whether
    # the source .app carried Name / Version / Publisher / AppId.
    dbml = Diagram(symbols={"Tables": [{"Name": "T", "Fields": []}]}).dbml()
    assert dbml.startswith("// Auto-generated by AL-to-DBML v")
    assert "// https://github.com/panda-coop/al2dbml" in dbml.split("\n", 2)[1]


def test_project_block_emits_mssql_database_type_by_default() -> None:
    # Every BC .app produces a Project block at the top of the DBML so
    # dbdocs.io renders a useful title card. Default database_type is
    # MSSQL since BC's underlying storage is always SQL Server.
    symbols = dict(sample_symbols(), Name="Sample App")
    dbml = Diagram(symbols=symbols).dbml()
    assert 'Project "Sample App"' in dbml
    assert "database_type: 'MSSQL'" in dbml


def test_project_block_note_carries_package_metadata() -> None:
    # The Note inside the Project block surfaces Name + Version +
    # Publisher + AppId so dbdocs renders an informative description
    # without making the consumer read the // header comment.
    symbols = {
        "Name": "Base Application",
        "Version": "25.0.0.0",
        "Publisher": "Microsoft",
        "AppId": "437dbf0e-84ff-417a-965d-ed2bb9650972",
        "Tables": [{"Name": "T", "Fields": [], "Keys": []}],
    }
    dbml = Diagram(symbols=symbols).dbml()
    assert 'Project "Base Application"' in dbml
    assert "Base Application 25.0.0.0 by Microsoft" in dbml
    assert "AppId: 437dbf0e-84ff-417a-965d-ed2bb9650972" in dbml


def test_project_block_custom_database_type_overrides_default() -> None:
    symbols = dict(sample_symbols(), Name="Sample App")
    dbml = Diagram(symbols=symbols, database_type="PostgreSQL").dbml()
    assert "database_type: 'PostgreSQL'" in dbml
    assert "database_type: 'MSSQL'" not in dbml


def test_project_block_empty_database_type_omits_the_line() -> None:
    # Empty string suppresses the database_type item but keeps the
    # Project block so dbdocs still has a title + Note to render.
    symbols = dict(sample_symbols(), Name="Sample App")
    dbml = Diagram(symbols=symbols, database_type="").dbml()
    assert 'Project "Sample App"' in dbml
    assert "database_type:" not in dbml


def test_project_block_falls_back_to_generic_name_when_metadata_missing() -> None:
    # A symbols document with no Name / Version / Publisher still gets
    # a Project block (carrying just database_type) so the dbdocs UI
    # has something to label the schema with.
    dbml = Diagram(symbols={"Tables": [{"Name": "T", "Fields": [], "Keys": []}]}).dbml()
    assert 'Project "al2dbml export"' in dbml
    assert "database_type: 'MSSQL'" in dbml
    # No Note block when there is no package metadata to put in it.
    project_start = dbml.index("Project ")
    project_end = dbml.index("}", project_start)
    assert "Note {" not in dbml[project_start:project_end]


def test_project_block_skipped_entirely_when_no_name_and_no_database_type() -> None:
    # No name and no database_type to put anywhere -> no Project block.
    dbml = Diagram(
        symbols={"Tables": [{"Name": "T", "Fields": [], "Keys": []}]},
        database_type="",
    ).dbml()
    assert "Project " not in dbml


def test_project_block_does_not_overwrite_caller_supplied_project() -> None:
    # If the caller passes a pre-existing pydbml Database that already
    # has a Project, leave it alone — our Project is a default, not a
    # forced override.
    from pydbml import Database
    from pydbml.classes import Project

    db = Database()
    db.project = Project(name="CustomProject", items={"database_type": "MySQL"})
    symbols = dict(sample_symbols(), Name="Sample App")
    Diagram(symbols=symbols, db=db).build()
    assert db.project is not None
    assert db.project.name == "CustomProject"
    assert db.project.items.get("database_type") == "MySQL"


def test_multi_condition_where_renders_as_indented_and_block() -> None:
    # Real Base Application TableRelations have multi-condition WHERE
    # clauses (often 4+ comma-separated filters) that AL source wraps
    # across lines with continuation indent. The Ref comment used to
    # inherit that whitespace verbatim, producing a jagged
    # '// where ("Contract Type"... ,\n//                          "Customer No."...'
    # block. The renderer now reformats the clause into a deliberate
    # indented block joined by AND — readable without lying about
    # the semantics (AL filter commas are implicitly AND).
    symbols = {
        "Tables": [
            {
                "Name": "Customer",
                "Fields": [{"Name": "No.", "TypeDefinition": {"Name": "Code"}, "Properties": []}],
                "Keys": [{"FieldNames": ["No."]}],
            },
            {
                "Name": "Sales Line",
                "Fields": [
                    {
                        "Name": "Customer No.",
                        "TypeDefinition": {"Name": "Code"},
                        "Properties": [
                            {
                                "Name": "TableRelation",
                                "Value": (
                                    'Customer."No." WHERE("Contract Type" = CONST(Contract),\n'
                                    '                    "Customer No." = FIELD("Customer No."),\n'
                                    '                    "Ship-to Code" = FIELD("Ship-to Code"))'
                                ),
                            }
                        ],
                    }
                ],
                "Keys": [{"FieldNames": ["Customer No."]}],
            },
        ]
    }
    dbml = Diagram(symbols=symbols).dbml()
    # The reformatted block: 'where' on its own line, each condition indented
    # two spaces, all but the last suffixed with ' AND'.
    expected = (
        "// where\n"
        '//   "Contract Type" = CONST(Contract) AND\n'
        '//   "Customer No." = FIELD("Customer No.") AND\n'
        '//   "Ship-to Code" = FIELD("Ship-to Code")'
    )
    assert expected in dbml
    # And the old jagged form is gone — the rendered output must not
    # contain a '// where (' followed by a trailing comma on the same line.
    assert "// where (" not in dbml
