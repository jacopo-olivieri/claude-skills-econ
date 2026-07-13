"""Shared mechanism-identity schema and canonicalizer (issue #14).

This module is the ONLY implementation of defect-mechanism identity in the
repo.  It owns, per the issue #14 resolution and Amendments 1-4:

- ``MECHANISM_SCHEMA_VERSION`` — the schema/canonicalizer version pinned per
  run (#14 A8).  The role table, alias lists, and escape grammar below are
  all part of this version; changing any of them mints a new version.
- The normative per-relation role table (A1/A10), the total relation
  precedence order, and the four-step Object tie-break with unsigned
  lexicographic byte order within a step (A10d).
- The closed, versioned identifier-alias and predicate-alias lists (#14
  point 4, A10e), reusing issue #10's literal-macro-expansion rules for
  path-typed values.
- The injective percent-escape cell grammar (A15): ``%`` reserved everywhere
  and encoded first as ``%25``, uppercase-hex two-digit escapes only,
  exactly one decode pass, malformed escapes hard-fail.
- The canonicalizer: five readable worker cells (A12 pre-boundary wire) in,
  canonical-JSON identity bytes plus the ``b64:`` sidecar cell plus the
  canonicalized mechanism columns out (A16 — never Receipt IDs, which are
  verifier-issued and joined by U3's atomic boundary assembler, A17).
- Sole ``MIXED`` authority (A6): only ``aggregate_row_mechanism`` may emit
  the literal ``MIXED``; a worker-supplied ``MIXED`` is a grammar hard-fail.
- The five-outcome replay scoring truth table (A3/A14): hit >
  wrong-mechanism > denied > undetermined > absent, with the
  hit-plus-contradictory-``matches`` coexistence raising the hard gate
  failure.

Identity bytes follow issue #8 Amendment 7 point 6: a UTF-8 JSON object with
literal keys ``class``, ``object``, ``relation``, ``expected``, ``actual``
in exactly that order, no insignificant whitespace, NFC-normalized strings
with RFC 8785/JCS string escaping, set values as byte-sorted arrays.
"""

import base64
import json
import re
import unicodedata
from typing import NamedTuple

# U1 owns this constant only; the recording surfaces (run identity, answer
# sheets, acceptance tuples) build with their own units (#14 A8).
MECHANISM_SCHEMA_VERSION = "1.0.0"

# --------------------------------------------------------------- vocabulary

DEFECT_RELATIONS = (
    # Total precedence order, most specific first (#14 A1).  Relation
    # selection takes the highest-precedence relation whose gloss applies.
    "never_fires",
    "overwrites",
    "wrong_target",
    "stale_reference",
    "omits",
    "adds",
    "wrong_value",
    "mismatches",
)
COVERAGE_RELATIONS = ("matches", "unresolved")
OUTPUT_RELATION = "maps_to"

REGISTER_RELATIONS = {
    # Per-register-class relation vocabularies (#14 A5).  The unknown-
    # relation hard-fail applies per register class.
    "code_errors": DEFECT_RELATIONS + COVERAGE_RELATIONS,
    "claims": DEFECT_RELATIONS + COVERAGE_RELATIONS,
    "outputs": (OUTPUT_RELATION,) + COVERAGE_RELATIONS,
}

OUTPUT_MECHANISM_CLASS = "output_mapping"

SCORE_OUTCOMES = ("hit", "wrong_mechanism", "denied", "undetermined", "absent")

# The exact witness wires either side of the boundary (#14 A6/A12).  Workers
# emit the pre-boundary columns; ``Receipt IDs`` is verifier-issued and
# joined by the U3 atomic boundary assembler (A16-A17), never produced here.
PRE_BOUNDARY_WITNESS_COLUMNS = (
    "Channel", "Source ID", "Witness ID", "Verdict",
    "Mech Class", "Mech Object", "Mech Relation", "Mech Expected",
    "Mech Actual", "Proposed Severity", "Duplicate Target",
)
POST_BOUNDARY_WITNESS_COLUMNS = (
    "Channel", "Source ID", "Witness ID", "Verdict",
    "Mechanism", "Proposed Severity", "Receipt IDs", "Duplicate Target",
)

MIXED = "MIXED"
DASH = "-"


class MechanismSchemaError(ValueError):
    """A mechanism value cannot be canonicalized unambiguously (hard fail)."""


class ContradictoryHitError(MechanismSchemaError):
    """An exact hit coexists with a contradictory ``matches`` record on the
    same (Class, Object) — a hard gate failure per #14 A14, never a hit."""


class SourceProjection(NamedTuple):
    """The slice of the audited source projection the canonicalizer consumes
    (#14 A13): declared Stata variable sets per repo-relative path, and the
    literal global-macro table for issue #10's macro-expansion rules."""

    variables: dict  # repo-relative path -> iterable of declared names
    macros: dict     # macro name -> literal value

EMPTY_PROJECTION = SourceProjection(variables={}, macros={})


class CanonicalMechanism(NamedTuple):
    identity_bytes: bytes  # canonical-JSON identity (#8 A7 point 6)
    sidecar: str           # "b64:" + unpadded base64url of identity_bytes
    columns: tuple         # canonicalized five-column wire cells (A16)


# --------------------------------------------------------------- role table
# One row per relation (#14 A1 with the A10 pins).  Value types drive the
# normalization applied per cell (A13): identifier, predicate literal,
# plain literal, target (identifier-or-path by the mechanical rule), the
# overwrites source expression, or the maps_to producer identity.  Arity is
# fixed per field per relation; "none" means the cell must be literally "-".

class RoleRule(NamedTuple):
    object_type: str
    expected_arity: str   # "scalar" | "set"
    expected_type: str
    actual_arity: str
    actual_type: str
    expected_dash_ok: bool = False
    actual_dash_ok: bool = False


ROLE_TABLE = {
    "never_fires": RoleRule("identifier", "set", "predicate", "scalar", "predicate"),
    "overwrites": RoleRule("identifier", "scalar", "none", "scalar", "expression"),
    # wrong_target Expected: the required role as a plain literal, or "-"
    # where no role is expressible (A10a).
    "wrong_target": RoleRule("target", "scalar", "literal", "scalar", "target",
                             expected_dash_ok=True),
    "stale_reference": RoleRule("identifier", "scalar", "target", "scalar", "target"),
    "omits": RoleRule("target", "set", "literal", "scalar", "none"),
    "adds": RoleRule("target", "scalar", "none", "set", "literal"),
    "wrong_value": RoleRule("identifier", "scalar", "literal", "scalar", "literal"),
    # mismatches Expected/Actual are always scalar (A10c); set-shaped
    # disagreements belong to omits/adds by precedence.
    "mismatches": RoleRule("target", "scalar", "literal", "scalar", "literal"),
    "matches": RoleRule("target", "scalar", "none", "scalar", "none"),
    "unresolved": RoleRule("target", "scalar", "none", "scalar", "none"),
    # maps_to Actual: normalized producer identity, "manual" or "-" allowed
    # (#8 A7 point 6).
    "maps_to": RoleRule("label", "scalar", "none", "scalar", "producer",
                        actual_dash_ok=True),
}

# The register classes whose Objects may be multi-word labels (paper/output
# objects); code-register objects are identifiers or paths, so internal
# whitespace there is prose-shaped and hard-fails.
_LABEL_OBJECT_REGISTERS = {"claims", "outputs"}

# ------------------------------------------------- percent-escape grammar
# #14 Amendment 3 (A15).  Reserved everywhere: % | ` newline; additionally
# , and ] inside set members.  Escapes are exactly "%" + two uppercase hex
# digits drawn from the reserved-set code points; one encode pass with %
# escaped first, one decode pass, injective by construction.

_ESCAPES = {"%": "%25", "|": "%7C", "`": "%60", "\n": "%0A", ",": "%2C", "]": "%5D"}
_UNESCAPES = {"25": "%", "7C": "|", "60": "`", "0A": "\n", "2C": ",", "5D": "]"}
_SCALAR_RESERVED = {"%", "|", "`", "\n"}
_MEMBER_RESERVED = {"%", "|", "`", "\n", ",", "]"}


def encode_cell(raw, set_member=False):
    """Encode a raw value into the readable-cell escape grammar (A15)."""
    reserved = _MEMBER_RESERVED if set_member else _SCALAR_RESERVED
    out = []
    for ch in raw:
        out.append(_ESCAPES[ch] if ch in reserved else ch)
    return "".join(out)


def decode_cell(cell, set_member=False):
    """One-pass decode; raw reserved characters and malformed escapes
    (lowercase hex, undefined code point, truncated escape) hard-fail."""
    reserved = _MEMBER_RESERVED if set_member else _SCALAR_RESERVED
    out = []
    i = 0
    while i < len(cell):
        ch = cell[i]
        if ch == "%":
            digits = cell[i + 1:i + 3]
            if len(digits) < 2:
                raise MechanismSchemaError(f"truncated escape in cell: {cell!r}")
            if digits != digits.upper() or digits not in _UNESCAPES:
                raise MechanismSchemaError(f"malformed escape %{digits} in cell: {cell!r}")
            out.append(_UNESCAPES[digits])
            i += 3
            continue
        if ch in reserved:
            raise MechanismSchemaError(f"raw reserved character {ch!r} in cell: {cell!r}")
        out.append(ch)
        i += 1
    return "".join(out)


# ------------------------------------------------------------- alias lists
# Closed and versioned (#14 point 4, A10e).  Extending either list is a
# recorded schema-version change, never a silent behavior change.

# Identifier aliases: (a) Stata unambiguous abbreviations expand against the
# location-anchored file's declared variable set (A13); (b) the two global-
# macro spellings normalize to the braced form ${x}; (c) path-typed values
# reuse issue #10's literal-macro-expansion rules (implemented below).
_GLOBAL_MACRO_RE = re.compile(r"\$(\{)?([A-Za-z_]\w*)(\})?")
_IDENTIFIER_RE = re.compile(r"[A-Za-z_]\w*")

# Predicate aliases: known equivalent Stata missing-test spellings.  The
# canonical spellings are mi(x) and !mi(x); `x != .`, `x < .`, `x == .`,
# `x >= .`, and missing(x) are the closed equivalent set.  Semantic
# equivalence beyond this list stays distinct bytes (A10e).
_PRED_TOKEN = r"(`[A-Za-z_]\w*'|\$\{[A-Za-z_]\w*\}|[A-Za-z_]\w*)"
_PREDICATE_ALIASES = (
    (re.compile(r"\bmissing\("), "mi("),
    (re.compile(_PRED_TOKEN + r" ?== ?\.(?![\w.])"), r"mi(\1)"),
    (re.compile(_PRED_TOKEN + r" ?!= ?\.(?![\w.])"), r"!mi(\1)"),
    (re.compile(_PRED_TOKEN + r" ?< ?\.(?![\w.])"), r"!mi(\1)"),
    (re.compile(_PRED_TOKEN + r" ?>= ?\.(?![\w.])"), r"mi(\1)"),
)

# Recognized script/data extensions for the wrong_target path-vs-identifier
# mechanical rule (A13).  Closed and versioned like the alias lists.
PATH_EXTENSIONS = {
    ".do", ".ado", ".py", ".r", ".jl", ".m", ".sas", ".dta", ".csv", ".tsv",
    ".txt", ".log", ".json", ".toml", ".yml", ".yaml", ".xlsx", ".xls",
    ".tex", ".md", ".pdf", ".png",
}

_NEGATION_WORD_RE = re.compile(r"(?i)\b(not|never)\b")
_NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")


def _nfc(value):
    return unicodedata.normalize("NFC", value)


def _declared_variables(projection, anchor):
    path = anchor.split(":", 1)[0] if anchor else ""
    return tuple(projection.variables.get(path, ()))


def _normalize_identifier(value, declared):
    match = _GLOBAL_MACRO_RE.fullmatch(value)
    if match:
        return "${" + match.group(2) + "}"
    if _IDENTIFIER_RE.fullmatch(value) and declared and value not in declared:
        hits = [name for name in declared if name.startswith(value)]
        if len(hits) == 1:
            return hits[0]
    return value


def _normalize_predicate(value, declared):
    # Canonical predicate literal (A10e): whitespace collapse to single
    # spaces, identifier normalization on tokens, negation spelled with a
    # leading !, then the closed predicate-alias list.
    value = re.sub(r"\s+", " ", value).strip()
    value = value.replace("~=", "!=").replace("~", "!")

    def _expand(match):
        token = match.group(0)
        start, end = match.start(), match.end()
        if end < len(value) and value[end] == "(":
            return token  # function name, not a variable position
        if start > 0 and value[start - 1] in "`${":
            return token  # macro name, not a variable position
        return _normalize_identifier(token, declared)

    value = _IDENTIFIER_RE.sub(_expand, value)
    value = _GLOBAL_MACRO_RE.sub(lambda m: "${" + m.group(2) + "}", value)
    for pattern, replacement in _PREDICATE_ALIASES:
        value = pattern.sub(replacement, value)
    return value


def _normalize_literal(value):
    if _NUMBER_RE.fullmatch(value):
        return _canonical_number(value)
    if value.lower() in ("true", "false"):
        return value.lower()
    return value


def _canonical_number(value):
    sign = ""
    if value[0] in "+-":
        sign = "-" if value[0] == "-" else ""
        value = value[1:]
    integer, _, fraction = value.partition(".")
    integer = integer.lstrip("0") or "0"
    fraction = fraction.rstrip("0")
    out = integer + ("." + fraction if fraction else "")
    if out == "0":
        return "0"
    return sign + out


_MACRO_EXPANSION_LIMIT = 32


def _normalize_path(value, macros):
    """Issue #10 step-1 literal macro expansion, reused verbatim: expand only
    literal macros/globals whose values are available, reject cycles,
    normalize quoting, separators, and dot segments, refuse ``..`` that
    escapes.  An unresolvable reference keeps its verbatim spelling (with
    the two global spellings still normalized to the braced form)."""
    original = _GLOBAL_MACRO_RE.sub(lambda m: "${" + m.group(2) + "}", value)
    text = value.strip()
    if text.startswith('`"') and text.endswith('"\''):
        text = text[2:-2]
    text = text.strip('"')
    for _ in range(_MACRO_EXPANSION_LIMIT):
        match = _GLOBAL_MACRO_RE.search(text)
        if match is None:
            break
        name = match.group(2)
        if name not in macros:
            return original  # unresolved root: verbatim spelling
        text = text[:match.start()] + str(macros[name]) + text[match.end():]
    else:
        return original  # cycle or runaway expansion: unresolved, verbatim
    text = text.replace("\\", "/")
    segments = []
    for segment in text.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if not segments:
                return original  # escapes the candidate suffix: unresolved
            segments.pop()
            continue
        segments.append(segment)
    return "/".join(segments) if segments else original


def _looks_like_path(value):
    if "/" in value or "\\" in value:
        return True
    dot = value.rfind(".")
    return dot > 0 and value[dot:].lower() in PATH_EXTENSIONS


def _normalize_target(value, declared, macros):
    if _looks_like_path(value):
        return _normalize_path(value, macros)
    return _normalize_identifier(value, declared)


# ------------------------------------------------------ selection helpers

def select_relation(applicable):
    """Pick the relation for a defect satisfying several glosses: the
    highest-precedence applicable relation in the A1 total order."""
    chosen = [rel for rel in DEFECT_RELATIONS if rel in set(applicable)]
    if not chosen:
        raise MechanismSchemaError(f"no applicable defect relation in {sorted(set(applicable))!r}")
    unknown = set(applicable) - set(DEFECT_RELATIONS)
    if unknown:
        raise MechanismSchemaError(f"unknown relation(s) in precedence selection: {sorted(unknown)!r}")
    return chosen[0]


def select_object(candidates):
    """Four-step Object tie-break (A1/A10d).  ``candidates`` is an iterable
    of ``(step, value)`` pairs with step 1-4; the Object is the first
    applicable step's candidate, and within one step the value that sorts
    first by unsigned lexicographic order of its normalized UTF-8 bytes."""
    by_step = {}
    for step, value in candidates:
        if step not in (1, 2, 3, 4):
            raise MechanismSchemaError(f"object tie-break step must be 1-4, got {step!r}")
        by_step.setdefault(step, []).append(_nfc(value).strip())
    if not by_step:
        raise MechanismSchemaError("object tie-break requires at least one candidate")
    winners = by_step[min(by_step)]
    return min(winners, key=lambda v: v.encode("utf-8"))


# ---------------------------------------------------------- canonicalizer

def canonicalize_mechanism(mech_class, mech_object, mech_relation,
                           mech_expected, mech_actual, *, register,
                           anchor="", projection=EMPTY_PROJECTION):
    """Canonicalize a worker's five readable mechanism cells.

    Inputs are exactly #14 A13's declared set: the five readable fields
    (percent-escaped wire cells), the row's register class, the row's
    location witness anchor, and the audited-source projection slice.
    Returns the canonical-JSON identity bytes, the ``b64:`` sidecar cell,
    and the canonicalized five-column wire cells — never Receipt IDs (A16).
    Anything ambiguous is a hard fail, never a silent variant identity.
    """
    if register not in REGISTER_RELATIONS:
        raise MechanismSchemaError(f"unknown register class {register!r}")
    cells = (mech_class, mech_object, mech_relation, mech_expected, mech_actual)
    for cell in cells:
        if not isinstance(cell, str) or not cell.strip():
            raise MechanismSchemaError("empty mechanism cell")
        if cell.strip() == MIXED:
            # A6: MIXED is merge-derived aggregation state; a worker never
            # emits it in any of the five columns.
            raise MechanismSchemaError("worker-emitted MIXED is a grammar hard-fail")

    relation = _nfc(decode_cell(mech_relation)).strip()
    if relation not in REGISTER_RELATIONS[register]:
        raise MechanismSchemaError(
            f"unknown relation {relation!r} for register class {register!r}")
    rule = ROLE_TABLE[relation]

    klass = _nfc(decode_cell(mech_class)).strip()
    _reject_prose(klass, "class")
    if re.search(r"\s", klass):
        raise MechanismSchemaError(f"prose-shaped mechanism class {klass!r}")
    if register == "outputs" and klass != OUTPUT_MECHANISM_CLASS:
        raise MechanismSchemaError(
            f"outputs register requires class {OUTPUT_MECHANISM_CLASS!r}, got {klass!r}")

    declared = _declared_variables(projection, anchor)
    macros = projection.macros

    obj = _nfc(decode_cell(mech_object)).strip()
    if obj == DASH:
        raise MechanismSchemaError("mechanism Object may not be '-'")
    _reject_prose(obj, "object")
    object_may_be_label = rule.object_type == "label" or register in _LABEL_OBJECT_REGISTERS
    if not object_may_be_label:
        if re.search(r"\s", obj) and not _looks_like_path(obj):
            raise MechanismSchemaError(f"prose-shaped Object {obj!r}")
    if rule.object_type != "label":
        obj = _normalize_target(obj, declared, macros)

    expected = _canonical_field(mech_expected, rule.expected_arity,
                                rule.expected_type, rule.expected_dash_ok,
                                declared, macros, "Expected", relation)
    actual = _canonical_field(mech_actual, rule.actual_arity,
                              rule.actual_type, rule.actual_dash_ok,
                              declared, macros, "Actual", relation)

    record = {"class": klass, "object": obj, "relation": relation,
              "expected": expected, "actual": actual}
    identity = json.dumps(record, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")
    sidecar = "b64:" + base64.urlsafe_b64encode(identity).rstrip(b"=").decode("ascii")
    columns = (
        encode_cell(klass), encode_cell(obj), encode_cell(relation),
        _encode_field(expected), _encode_field(actual),
    )
    return CanonicalMechanism(identity, sidecar, columns)


def _reject_prose(value, field):
    if _NEGATION_WORD_RE.search(value):
        # Polarity lives in the Relation field alone; negation words can
        # never appear inside values (#14 resolution point 3).
        raise MechanismSchemaError(f"negation word inside mechanism {field}: {value!r}")


def _canonical_field(cell, arity, value_type, dash_ok, declared, macros,
                     field, relation):
    if arity == "set":
        return _canonical_set(cell, value_type, declared, macros, field, relation)
    value = _nfc(decode_cell(cell)).strip()
    if not value:
        raise MechanismSchemaError(f"empty {field} value for {relation!r}")
    if cell.strip().startswith("[") and cell.strip().endswith("]"):
        raise MechanismSchemaError(
            f"{relation!r} {field} is scalar; set-shaped cell {cell!r} is a wrong arity")
    if value_type == "none":
        if value != DASH:
            raise MechanismSchemaError(
                f"{relation!r} requires {field} to be '-', got {value!r}")
        return DASH
    if value == DASH:
        if dash_ok:
            return DASH
        raise MechanismSchemaError(f"{relation!r} {field} may not be '-'")
    return _normalize_value(value, value_type, declared, macros, field)


def _canonical_set(cell, value_type, declared, macros, field, relation):
    cell = cell.strip()
    if not (cell.startswith("[") and cell.endswith("]")):
        # Brackets are mandatory even for singletons (A1), so a bare scalar
        # can never be legal in a set slot.
        raise MechanismSchemaError(
            f"{relation!r} {field} is a set; cell must be bracketed, got {cell!r}")
    interior = cell[1:-1]
    if not interior.strip():
        raise MechanismSchemaError(f"empty set in {relation!r} {field}")
    members = []
    for raw_member in interior.split(", "):
        value = _nfc(decode_cell(raw_member, set_member=True)).strip()
        if not value or value == DASH:
            raise MechanismSchemaError(
                f"invalid set member {raw_member!r} in {relation!r} {field}")
        if value == MIXED:
            raise MechanismSchemaError("worker-emitted MIXED is a grammar hard-fail")
        members.append(_normalize_value(value, value_type, declared, macros, field))
    if len(set(members)) != len(members):
        raise MechanismSchemaError(
            f"duplicate normalized set members in {relation!r} {field}: {members!r}")
    return sorted(members, key=lambda m: m.encode("utf-8"))


def _normalize_value(value, value_type, declared, macros, field):
    _reject_prose(value, field)
    if value_type == "identifier":
        if re.search(r"\s", value):
            raise MechanismSchemaError(f"prose-shaped identifier {value!r}")
        return _normalize_identifier(value, declared)
    if value_type == "predicate":
        return _normalize_predicate(value, declared)
    if value_type == "literal":
        return _normalize_literal(value)
    if value_type == "target":
        return _normalize_target(value, declared, macros)
    if value_type == "expression":
        # overwrites Actual (A10b): the source identifier when the surviving
        # write's right-hand side is exactly one identifier, otherwise the
        # normalized expression literal.
        if _IDENTIFIER_RE.fullmatch(value):
            return _normalize_identifier(value, declared)
        return _normalize_predicate(value, declared)
    if value_type == "producer":
        if value == "manual":
            return value
        return _normalize_target(value, declared, macros)
    raise MechanismSchemaError(f"unknown value type {value_type!r}")


def _encode_field(value):
    if isinstance(value, list):
        return "[" + ", ".join(encode_cell(m, set_member=True) for m in value) + "]"
    return encode_cell(value)


# ------------------------------------------------------------ MIXED merge

def aggregate_row_mechanism(witnesses):
    """Sole ``MIXED`` authority (#14 A6, #8 A7 point 7).

    ``witnesses`` is the merged row's witness tuples, each
    ``(mechanism, verdict, proposed_severity, duplicate_target)`` where
    ``mechanism`` is a canonicalizer-produced ``b64:`` cell, identity bytes,
    or ``CanonicalMechanism``.  Returns the single canonical ``b64:`` cell
    when every witness shares the same full tuple, else the literal
    ``MIXED``.  A parent row may remain unsplit only when homogeneous;
    heterogeneity in mechanism, verdict, severity, or target is ``MIXED``.
    """
    rows = list(witnesses)
    if not rows:
        raise MechanismSchemaError("aggregate requires at least one witness record")
    tuples = []
    for mechanism, verdict, severity, target in rows:
        sidecar = _sidecar_cell(mechanism)
        tuples.append((
            sidecar,
            str(verdict).strip(),
            str(severity).strip(),
            str(target).strip() if target not in (None, "") else DASH,
        ))
    if len(set(tuples)) == 1:
        return tuples[0][0]
    return MIXED


def _sidecar_cell(mechanism):
    if isinstance(mechanism, CanonicalMechanism):
        return mechanism.sidecar
    if isinstance(mechanism, bytes):
        return "b64:" + base64.urlsafe_b64encode(mechanism).rstrip(b"=").decode("ascii")
    if isinstance(mechanism, str) and mechanism.startswith("b64:"):
        _identity_bytes(mechanism)  # validates transport and JSON shape
        return mechanism
    if mechanism == MIXED:
        raise MechanismSchemaError("only the canonicalizer emits MIXED; "
                                   "a supplied literal MIXED is a hard fail")
    raise MechanismSchemaError(f"not a canonical mechanism value: {mechanism!r}")


# ----------------------------------------------------------- truth table

def _identity_bytes(record):
    if isinstance(record, CanonicalMechanism):
        return record.identity_bytes
    if isinstance(record, bytes):
        return record
    if isinstance(record, str) and record.startswith("b64:"):
        payload = record[4:]
        padded = payload + "=" * (-len(payload) % 4)
        try:
            return base64.urlsafe_b64decode(padded.encode("ascii"))
        except Exception as exc:
            raise MechanismSchemaError(f"invalid b64 sidecar {record!r}") from exc
    raise MechanismSchemaError(f"not a canonical mechanism record: {record!r}")


def _parse_identity(record):
    raw = _identity_bytes(record)
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise MechanismSchemaError(f"invalid identity bytes {raw!r}") from exc
    if not isinstance(parsed, dict) or list(parsed) != [
            "class", "object", "relation", "expected", "actual"]:
        raise MechanismSchemaError(f"identity bytes are not a canonical record: {raw!r}")
    return raw, parsed


def score_expected_finding(run_records, accepted_records):
    """Five-outcome scoring truth table (#14 A3/A14).

    ``accepted_records`` is the answer sheet's acceptance set for one
    expected finding (cardinality one for gate sheets, A9); a hit is byte
    equality to any member.  ``run_records`` is every mechanism record the
    replayed run produced.  The (Class, Object) grouping is a diagnostic
    projection only; identity remains full-canonical-byte equality.
    Raises ``ContradictoryHitError`` when an exact hit coexists with a
    ``matches`` record on the same (Class, Object) — a hard gate failure.
    """
    accepted = [_parse_identity(r) for r in accepted_records]
    if not accepted:
        raise MechanismSchemaError("acceptance set must have at least one member")
    accepted_bytes = {raw for raw, _ in accepted}
    expected_pairs = {(p["class"], p["object"]) for _, p in accepted}

    engaged = []
    for record in run_records:
        raw, parsed = _parse_identity(record)
        if (parsed["class"], parsed["object"]) in expected_pairs:
            engaged.append((raw, parsed["relation"]))

    hit = any(raw in accepted_bytes for raw, _ in engaged)
    denied = any(rel == "matches" for _, rel in engaged)
    if hit and denied:
        raise ContradictoryHitError(
            "exact hit coexists with a contradictory matches record on the "
            "expected (Class, Object)")
    if hit:
        return "hit"
    # Wrong-mechanism is widened (A14) to any record on the expected
    # (Class, Object) whose relation is not matches/unresolved, which makes
    # output maps_to records scoreable.
    if any(rel not in COVERAGE_RELATIONS for _, rel in engaged):
        return "wrong_mechanism"
    if denied:
        return "denied"
    if any(rel == "unresolved" for _, rel in engaged):
        return "undetermined"
    return "absent"
