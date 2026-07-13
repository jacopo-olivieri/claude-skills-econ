"""Unit U1 tests — mechanism schema and canonicalizer (issue #14).

The four ``test_pinned_*`` cases pin the ticket's fixture canonicalizations
byte-for-byte: the flood-value repair error (benchmark E-0401, both code
sites), and fixture plants P-15, P-17, and P-18.  The escape-grammar suite
is the Amendment 3 mandated set.
"""

import base64
import itertools

import pytest

import regbuild as rb

ms = rb.load_script("mechanism_schema")

pytestmark = pytest.mark.u1


def b64cell(identity_bytes):
    return "b64:" + base64.urlsafe_b64encode(identity_bytes).rstrip(b"=").decode("ascii")


# ------------------------------------------------------- pinned records
# The flood-value repair error (#14 A1 worked example): Object the repaired
# flood-extent variable as named at the obligation-stating comment, Expected
# the missing-value case as a one-element predicate array, Actual the
# observed guard literal.  Site 1 (build_supplier_flood_status.do:368)
# writes the guard as `var' != . and site 2
# (make_sales_weighted_outcomes.do:525) as !mi(`var'); the closed
# predicate-alias list normalizes both to the same canonical bytes, so the
# two site witnesses share one canonical mechanism (plan AE2).
FLOOD_IDENTITY = (
    '{"class":"sample_filter_or_flag_error",'
    '"object":"fldx_`window\'m_`y\'",'
    '"relation":"never_fires",'
    '"expected":["mi(`var\')"],'
    '"actual":"!mi(`var\')"}'
).encode("utf-8")

P15_IDENTITY = (
    '{"class":"aggregation_or_unit_error",'
    '"object":"income_check",'
    '"relation":"omits",'
    '"expected":["remittances"],'
    '"actual":"-"}'
).encode("utf-8")

P17_IDENTITY = (
    '{"class":"sample_filter_or_flag_error",'
    '"object":"hhsize",'
    '"relation":"never_fires",'
    '"expected":["mi(hhsize)"],'
    '"actual":"!mi(hhsize)"}'
).encode("utf-8")

P18_IDENTITY = (
    '{"class":"sample_filter_or_flag_error",'
    '"object":"has_wages",'
    '"relation":"overwrites",'
    '"expected":"-",'
    '"actual":"(df[\\"wave\\"] == wave) & (df[\\"wage_earnings\\"] > 0)"}'
).encode("utf-8")


def test_pinned_flood_fill_never_fires():
    site2 = ms.canonicalize_mechanism(
        "sample_filter_or_flag_error",
        "fldx_%60window'm_%60y'",
        "never_fires",
        "[mi(%60var')]",
        "!mi(%60var')",
        register="code_errors",
        anchor="do/data_building/make_sales_weighted_outcomes.do:525",
    )
    assert site2.identity_bytes == FLOOD_IDENTITY
    assert site2.sidecar == b64cell(FLOOD_IDENTITY)
    # Site 1 spells the guard `var' != . — the alias list must land on the
    # identical canonical bytes, one mechanism for both site witnesses.
    site1 = ms.canonicalize_mechanism(
        "sample_filter_or_flag_error",
        "fldx_%60window'm_%60y'",
        "never_fires",
        "[%60var' == .]",
        "%60var' != .",
        register="code_errors",
        anchor="do/data_building/build_supplier_flood_status.do:368",
    )
    assert site1.identity_bytes == FLOOD_IDENTITY
    assert site1.sidecar == site2.sidecar


def test_pinned_p15_omits_step2_object():
    # No code declaration states the four-component contract, so tie-break
    # step 2 selects the produced income aggregate; the member list is
    # never the Object (#14 A1).
    assert ms.select_object([(2, "income_check"), (3, "py/build_income.py")]) == "income_check"
    got = ms.canonicalize_mechanism(
        "aggregation_or_unit_error",
        "income_check",
        "omits",
        "[remittances]",
        "-",
        register="code_errors",
        anchor="py/build_income.py:14",
    )
    assert got.identity_bytes == P15_IDENTITY
    assert got.sidecar == b64cell(P15_IDENTITY)
    assert got.columns == (
        "aggregation_or_unit_error", "income_check", "omits",
        "[remittances]", "-",
    )


def test_pinned_p17_never_fires_by_precedence():
    # A wrong guard value that makes the operation unreachable satisfies
    # both never_fires and wrong_value; the total order resolves it.
    assert ms.select_relation(["wrong_value", "never_fires"]) == "never_fires"
    projection = ms.SourceProjection(
        variables={"do/build_panel.do": ("household_id", "wave", "hhsize")},
        macros={},
    )
    got = ms.canonicalize_mechanism(
        "sample_filter_or_flag_error",
        "hhsize",
        "never_fires",
        "[hhsize == .]",
        "hhsize < .",
        register="code_errors",
        anchor="do/build_panel.do:21",
        projection=projection,
    )
    assert got.identity_bytes == P17_IDENTITY
    assert got.sidecar == b64cell(P17_IDENTITY)


def test_pinned_p18_overwrites():
    got = ms.canonicalize_mechanism(
        "sample_filter_or_flag_error",
        "has_wages",
        "overwrites",
        "-",
        '(df["wave"] == wave) & (df["wage_earnings"] > 0)',
        register="code_errors",
        anchor="py/build_income.py:25",
    )
    assert got.identity_bytes == P18_IDENTITY
    assert got.sidecar == b64cell(P18_IDENTITY)
    # Determinism: feeding the canonical columns back through the
    # canonicalizer reproduces the same identity bytes.
    again = ms.canonicalize_mechanism(
        *got.columns, register="code_errors", anchor="py/build_income.py:25")
    assert again.identity_bytes == P18_IDENTITY


def test_p12_byte_order_tiebreak():
    # P-12 (reversed figure legend): a swap leaves two mislabeled targets in
    # the same tie-break step; the record takes the identifier sorting first
    # by unsigned lexicographic order of its normalized UTF-8 bytes.
    assert ms.select_object([(4, "Shocked"), (4, "Non-shocked")]) == "Non-shocked"
    # An earlier applicable step always wins over later steps.
    assert ms.select_object([(4, "aaa"), (2, "zzz")]) == "zzz"
    # Byte order is over UTF-8 bytes, not code points reinterpreted: ASCII
    # sorts before any multi-byte sequence.
    assert ms.select_object([(1, "élabel"), (1, "zlabel")]) == "zlabel"
    with pytest.raises(ms.MechanismSchemaError):
        ms.select_object([])
    with pytest.raises(ms.MechanismSchemaError):
        ms.select_object([(5, "x")])


def test_negation_scores_denied_miss():
    # "The consumer is NOT narrower" is inexpressible as a defect record:
    # negation words can never appear inside values.
    with pytest.raises(ms.MechanismSchemaError):
        ms.canonicalize_mechanism(
            "sample_filter_or_flag_error",
            "hhsize",
            "never_fires",
            "[mi(hhsize)]",
            "the guard is NOT narrower",
            register="code_errors",
        )
    # The only expressible denial is a matches record, which scores as a
    # denied miss against the expected defect record.
    denial = ms.canonicalize_mechanism(
        "sample_filter_or_flag_error", "hhsize", "matches", "-", "-",
        register="code_errors",
    )
    assert ms.score_expected_finding([denial], [P17_IDENTITY]) == "denied"


def test_mirror_image_inexpressible():
    # The closed relation set contains no directional pairs, so the
    # mirror-image record (producer, wider_than, consumer) cannot be
    # expressed at all; there is no runtime flip step to be buggy.
    for register in ("code_errors", "claims", "outputs"):
        assert "wider_than" not in ms.REGISTER_RELATIONS[register]
        assert "narrower_than" not in ms.REGISTER_RELATIONS[register]
        for relation in ("wider_than", "narrower_than"):
            with pytest.raises(ms.MechanismSchemaError):
                ms.canonicalize_mechanism(
                    "sample_filter_or_flag_error", "consent_ok", relation,
                    "[individual]", "[community]", register=register,
                )
    with pytest.raises(ms.MechanismSchemaError):
        ms.select_relation(["wider_than"])


def test_arity_and_grammar_hard_fails():
    def bad(*fields, register="code_errors"):
        with pytest.raises(ms.MechanismSchemaError):
            ms.canonicalize_mechanism(*fields, register=register)

    ok = ("sample_filter_or_flag_error", "hhsize", "never_fires",
          "[mi(hhsize)]", "!mi(hhsize)")
    # Set slot given a bare scalar: brackets are mandatory even for
    # singletons, so "individual" vs ["individual"] can never both be legal.
    bad(ok[0], ok[1], ok[2], "mi(hhsize)", ok[4])
    # Scalar slot given a set-shaped cell.
    bad(ok[0], ok[1], "wrong_value", "[5]", "3")
    # Required "-" holds something else, and vice versa.
    bad(ok[0], "income_check", "omits", "[remittances]", "extra")
    bad(ok[0], ok[1], ok[2], ok[3], "-")
    # Raw reserved characters in a cell.
    bad(ok[0], "hh|size", ok[2], ok[3], ok[4])
    bad(ok[0], "hh`size", ok[2], ok[3], ok[4])
    bad(ok[0], "hh\nsize", ok[2], ok[3], ok[4])
    # Raw comma inside a set member (comma-space is the only separator).
    bad(ok[0], "income_check", "omits", "[a,b]", "-")
    # Malformed sets: empty, unclosed, duplicate normalized members.
    bad(ok[0], "income_check", "omits", "[]", "-")
    bad(ok[0], "income_check", "omits", "[remittances", "-")
    bad(ok[0], "income_check", "omits", "[remittances, remittances]", "-")
    # Unknown relation word, per register class.
    bad(ok[0], ok[1], "explodes", ok[3], ok[4])
    bad(ok[0], ok[1], "omits", "[x]", "-", register="outputs")
    bad("output_mapping", "Table 1", "maps_to", "-", "do/analysis.do")
    # Empty cells and unknown register.
    bad(ok[0], "", ok[2], ok[3], ok[4])
    with pytest.raises(ms.MechanismSchemaError):
        ms.canonicalize_mechanism(*ok, register="figments")
    # Prose-shaped identifier values.
    bad(ok[0], "the repaired variable", ok[2], ok[3], ok[4])


def test_alias_determinism():
    projection = ms.SourceProjection(
        variables={"do/build_panel.do": ("household_size", "wave")},
        macros={"build_dir": "output"},
    )
    # (a) Stata unambiguous abbreviation expands to the full declared name.
    expanded = ms.canonicalize_mechanism(
        "sample_filter_or_flag_error", "household_s", "wrong_value", "2", "3",
        register="code_errors", anchor="do/build_panel.do:10",
        projection=projection)
    full = ms.canonicalize_mechanism(
        "sample_filter_or_flag_error", "household_size", "wrong_value", "2", "3",
        register="code_errors", anchor="do/build_panel.do:10",
        projection=projection)
    assert expanded.identity_bytes == full.identity_bytes
    # An ambiguous abbreviation stays verbatim.
    ambiguous = ms.SourceProjection(
        variables={"do/build_panel.do": ("household_size", "household_shock")},
        macros={})
    kept = ms.canonicalize_mechanism(
        "sample_filter_or_flag_error", "household_s", "wrong_value", "2", "3",
        register="code_errors", anchor="do/build_panel.do:10",
        projection=ambiguous)
    assert b'"object":"household_s"' in kept.identity_bytes
    # (b) The two global-macro spellings normalize to the braced form.
    bare = ms.canonicalize_mechanism(
        "stale_or_wrong_path", "$build_dir", "wrong_value", "2", "3",
        register="code_errors")
    braced = ms.canonicalize_mechanism(
        "stale_or_wrong_path", "${build_dir}", "wrong_value", "2", "3",
        register="code_errors")
    assert bare.identity_bytes == braced.identity_bytes
    # (c) Path-typed values reuse issue #10's literal macro expansion.
    via_macro = ms.canonicalize_mechanism(
        "stale_or_wrong_path", "panel_path", "stale_reference",
        "output/panel.csv", "${build_dir}\\panel_v2.csv",
        register="code_errors", projection=projection)
    literal = ms.canonicalize_mechanism(
        "stale_or_wrong_path", "panel_path", "stale_reference",
        "output/panel.csv", "output/panel_v2.csv",
        register="code_errors", projection=projection)
    assert via_macro.identity_bytes == literal.identity_bytes
    # An unresolvable reference keeps its verbatim (braced) spelling.
    unresolved = ms.canonicalize_mechanism(
        "stale_or_wrong_path", "panel_path", "stale_reference",
        "output/panel.csv", "$unknown_root/panel_v2.csv",
        register="code_errors", projection=projection)
    assert b'"actual":"${unknown_root}/panel_v2.csv"' in unresolved.identity_bytes
    # Predicate aliases: the closed equivalent missing-test spellings.
    identities = set()
    for cell in ("[missing(hhsize)]", "[hhsize == .]"):
        got = ms.canonicalize_mechanism(
            "sample_filter_or_flag_error", "hhsize", "never_fires",
            cell, "hhsize < .", register="code_errors")
        identities.add(got.identity_bytes)
    assert identities == {P17_IDENTITY}
    # Determinism: the same inputs always produce the same bytes.
    for _ in range(3):
        again = ms.canonicalize_mechanism(
            "sample_filter_or_flag_error", "household_s", "wrong_value",
            "2", "3", register="code_errors", anchor="do/build_panel.do:10",
            projection=projection)
        assert again.identity_bytes == expanded.identity_bytes


def test_truth_table_maps_to_wrong_mechanism():
    expected = ms.canonicalize_mechanism(
        "output_mapping", "Table 1", "maps_to", "-", "do/analysis.do",
        register="outputs")
    wrong_producer = ms.canonicalize_mechanism(
        "output_mapping", "Table 1", "maps_to", "-", "py/make_figures.py",
        register="outputs")
    unresolved = ms.canonicalize_mechanism(
        "output_mapping", "Table 1", "unresolved", "-", "-",
        register="outputs")
    other_object = ms.canonicalize_mechanism(
        "output_mapping", "Figure 1", "maps_to", "-", "py/make_figures.py",
        register="outputs")
    accepted = [expected.identity_bytes]
    # A maps_to record naming the wrong producer is a wrong-mechanism miss,
    # not a fall-through: output records are scoreable (#14 A14).
    assert ms.score_expected_finding([wrong_producer], accepted) == "wrong_mechanism"
    # Precedence and the remaining outcomes.
    assert ms.score_expected_finding([expected], accepted) == "hit"
    assert ms.score_expected_finding([expected, wrong_producer], accepted) == "hit"
    assert ms.score_expected_finding([unresolved], accepted) == "undetermined"
    assert ms.score_expected_finding([wrong_producer, unresolved], accepted) == "wrong_mechanism"
    assert ms.score_expected_finding([], accepted) == "absent"
    assert ms.score_expected_finding([other_object], accepted) == "absent"
    with pytest.raises(ms.MechanismSchemaError):
        ms.score_expected_finding([expected], [])


def test_hit_plus_contradiction_hard_fail():
    hit = ms.canonicalize_mechanism(
        "sample_filter_or_flag_error", "hhsize", "never_fires",
        "[mi(hhsize)]", "!mi(hhsize)", register="code_errors")
    assert hit.identity_bytes == P17_IDENTITY
    denial = ms.canonicalize_mechanism(
        "sample_filter_or_flag_error", "hhsize", "matches", "-", "-",
        register="code_errors")
    # An exact hit plus a contradictory matches record on the same
    # (Class, Object) is a hard gate failure, never a hit with a footnote.
    with pytest.raises(ms.ContradictoryHitError):
        ms.score_expected_finding([hit, denial], [P17_IDENTITY])
    # A matches record on a different object does not contradict.
    unrelated_denial = ms.canonicalize_mechanism(
        "sample_filter_or_flag_error", "has_wages", "matches", "-", "-",
        register="code_errors")
    assert ms.score_expected_finding([hit, unrelated_denial], [P17_IDENTITY]) == "hit"


def test_escape_roundtrip_and_collisions():
    cases = [
        ("|", "%7C"),
        ("\n", "%0A"),
        ("%", "%25"),
        ("%7C", "%257C"),
        ("%9.0g", "%259.0g"),
    ]
    for raw, encoded in cases:
        assert ms.encode_cell(raw) == encoded
        assert ms.decode_cell(encoded) == raw
    # A literal %7C and an encoded | are distinct raw values with distinct
    # encoded bytes — the A15 injectivity repair.
    assert ms.encode_cell("%7C") != ms.encode_cell("|")
    assert ms.decode_cell("%257C") == "%7C"
    assert ms.decode_cell("%7C") == "|"
    # Comma and ] are additionally reserved inside set members only.
    assert ms.encode_cell("a,b", set_member=True) == "a%2Cb"
    assert ms.encode_cell("a]b", set_member=True) == "a%5Db"
    assert ms.encode_cell("a,b") == "a,b"
    assert ms.decode_cell("a%2Cb", set_member=True) == "a,b"
    got = ms.canonicalize_mechanism(
        "aggregation_or_unit_error", "income_check", "omits",
        "[a%2Cb, c%5Dd]", "-", register="code_errors")
    assert b'"expected":["a,b","c]d"]' in got.identity_bytes
    assert got.columns[3] == "[a%2Cb, c%5Dd]"


def test_escape_malformed_hard_fails():
    malformed = [
        "%7c",       # lowercase hex
        "%41",       # undefined code point (not in the reserved set)
        "abc%",      # trailing bare %
        "%2",        # truncated escape
        "a|b",       # raw reserved character
        "a`b",
        "a\nb",
    ]
    for cell in malformed:
        with pytest.raises(ms.MechanismSchemaError):
            ms.decode_cell(cell)
    for cell in ("a,b", "a]b"):
        with pytest.raises(ms.MechanismSchemaError):
            ms.decode_cell(cell, set_member=True)


def test_escape_injectivity_property():
    # Deterministic corpus: every string of length <= 3 over an alphabet
    # mixing reserved characters, hex-digit lookalikes, and plain text.
    alphabet = ["a", "%", "|", "`", "\n", ",", "]", "2", "5", "7", "C", "c", "0"]
    corpus = [""]
    for length in (1, 2, 3):
        corpus.extend("".join(chars) for chars in itertools.product(alphabet, repeat=length))
    corpus.extend(["%7C", "%257C", "%9.0g", "%25", "%td"])
    for set_member in (False, True):
        seen = {}
        for raw in corpus:
            encoded = ms.encode_cell(raw, set_member=set_member)
            assert ms.decode_cell(encoded, set_member=set_member) == raw
            assert seen.setdefault(encoded, raw) == raw, (
                f"collision: {raw!r} and {seen[encoded]!r} both encode to {encoded!r}")


def test_mixed_aggregate_emission():
    mech_a = ms.canonicalize_mechanism(
        "sample_filter_or_flag_error", "hhsize", "never_fires",
        "[mi(hhsize)]", "!mi(hhsize)", register="code_errors")
    mech_b = ms.canonicalize_mechanism(
        "sample_filter_or_flag_error", "has_wages", "overwrites", "-",
        '(df["wave"] == wave) & (df["wage_earnings"] > 0)',
        register="code_errors")
    # Homogeneous witness tuples collapse to the single canonical value,
    # whatever transport form each witness record arrived in.
    homogeneous = [
        (mech_a.sidecar, "confirmed_error", "2", "-"),
        (mech_a, "confirmed_error", 2, None),
        (mech_a.identity_bytes, "confirmed_error", "2", ""),
    ]
    assert ms.aggregate_row_mechanism(homogeneous) == mech_a.sidecar
    # Heterogeneity in mechanism, verdict, severity, or duplicate target
    # each yields MIXED — verdicts never collapse merely because the
    # mechanisms match (#8 A7 point 7).
    assert ms.aggregate_row_mechanism([
        (mech_a.sidecar, "confirmed_error", "2", "-"),
        (mech_b.sidecar, "confirmed_error", "2", "-"),
    ]) == "MIXED"
    assert ms.aggregate_row_mechanism([
        (mech_a.sidecar, "confirmed_error", "2", "-"),
        (mech_a.sidecar, "confirmation_needed", "2", "-"),
    ]) == "MIXED"
    assert ms.aggregate_row_mechanism([
        (mech_a.sidecar, "confirmed_error", "2", "-"),
        (mech_a.sidecar, "confirmed_error", "3", "-"),
    ]) == "MIXED"
    assert ms.aggregate_row_mechanism([
        (mech_a.sidecar, "duplicate", "2", "E-0101"),
        (mech_a.sidecar, "duplicate", "2", "E-0102"),
    ]) == "MIXED"
    with pytest.raises(ms.MechanismSchemaError):
        ms.aggregate_row_mechanism([])


def test_worker_mixed_hard_fail():
    ok = ("sample_filter_or_flag_error", "hhsize", "never_fires",
          "[mi(hhsize)]", "!mi(hhsize)")
    # A worker-supplied literal MIXED in any of the five columns is a
    # grammar hard-fail; only the canonicalizer emits MIXED (#14 A6).
    for position in range(5):
        cells = list(ok)
        cells[position] = "MIXED"
        with pytest.raises(ms.MechanismSchemaError):
            ms.canonicalize_mechanism(*cells, register="code_errors")
    with pytest.raises(ms.MechanismSchemaError):
        ms.canonicalize_mechanism(
            ok[0], ok[1], ok[2], "[MIXED]", ok[4], register="code_errors")
    # The aggregate path refuses a supplied MIXED as an input mechanism.
    with pytest.raises(ms.MechanismSchemaError):
        ms.aggregate_row_mechanism([("MIXED", "confirmed_error", "2", "-")])
