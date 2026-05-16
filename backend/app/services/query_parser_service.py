"""Natural-language query parsing — runs BEFORE molecule resolution.

This service converts a free-form scientific question such as:

    "What do we know about Aspirin? Summarize key ChEMBL assays and potency"

into a structured :class:`ParsedQuery` object:

    ParsedQuery(
        raw_query="What do we know about Aspirin?…",
        molecules=["Aspirin"],
        targets=[],
        intent="evidence_summary",
        requested_fields=["assays", "potency"],
        filters={},
    )

The downstream pipeline (validation → resolution → ChEMBL retrieval → report)
operates on the **extracted entities only** and never on the raw sentence.

The parser is deliberately deterministic (regex + lexicon + optional ChEMBL
verification) so it works without an LLM call and stays cheap.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public schemas
# ---------------------------------------------------------------------------

class ParsedQuery(BaseModel):
    """Output of :func:`build_normalized_request` — what the orchestrator sees."""

    raw_query: str
    query_type: str = "natural_language"  # natural_language | smiles_only | mixed_query | target_query | comparison_query
    molecules: List[str] = Field(default_factory=list)
    targets: List[str] = Field(default_factory=list)
    intent: str = "evidence_summary"
    requested_fields: List[str] = Field(default_factory=list)
    filters: Dict[str, object] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Constants — lexicons & regexes
# ---------------------------------------------------------------------------

# Common drug brand → generic synonyms (ChEMBL stores generic names).
_SYNONYM_MAP: Dict[str, str] = {
    "tylenol": "Paracetamol",
    "panadol": "Paracetamol",
    "acetaminophen": "Paracetamol",
    "advil": "Ibuprofen",
    "motrin": "Ibuprofen",
    "nurofen": "Ibuprofen",
    "aleve": "Naproxen",
    "naprosyn": "Naproxen",
    "voltaren": "Diclofenac",
    "celebrex": "Celecoxib",
    "vioxx": "Rofecoxib",
    "zocor": "Simvastatin",
    "lipitor": "Atorvastatin",
    "crestor": "Rosuvastatin",
    "plavix": "Clopidogrel",
    "coumadin": "Warfarin",
    "azd9291": "Osimertinib",
    "tagrisso": "Osimertinib",
    "iressa": "Gefitinib",
    "tarceva": "Erlotinib",
    "gleevec": "Imatinib",
    "glivec": "Imatinib",
    "sutent": "Sunitinib",
    "viagra": "Sildenafil",
    "cialis": "Tadalafil",
    "prozac": "Fluoxetine",
    "zoloft": "Sertraline",
    "xanax": "Alprazolam",
}

# ChEMBL ID
_CHEMBL_ID_RE = re.compile(r"\bCHEMBL\d+\b", re.IGNORECASE)

# SMILES heuristic: a token containing chemistry-only characters
_SMILES_TOKEN_RE = re.compile(r"[A-Za-z0-9@+\-\[\]\(\)=#%/\\.]{6,}")
_SMILES_REQUIRED_CHARS = set("=@#[]()/\\")

# Bioactivity / endpoint keywords (used both for intent & filters)
_ENDPOINT_TERMS = {
    "ic50": "IC50",
    "ki":   "Ki",
    "kd":   "Kd",
    "ec50": "EC50",
    "ki50": "Ki",
    "potency": "potency",
    "activity": "activity",
    "inhibition": "inhibition",
}

_REQUESTED_FIELD_TERMS = {
    "assays":      ["assay", "assays"],
    "ligands":     ["ligand", "ligands"],
    "IC50":        ["ic50", "pic50"],
    "EC50":        ["ec50", "pec50"],
    "Kd":          ["kd"],
    "Ki":          ["ki"],
    "potency":     ["potency"],
    "predictions": ["predict", "prediction", "predicted"],
    "toxicity":    ["toxicity", "toxic"],
    "solubility":  ["solubility", "soluble", "logs"],
    "targets":     ["target", "targets", "binding"],
    "similar":     ["similar", "analog", "analogue", "scaffold"],
    "physchem":    ["physchem", "physicochemical", "molecular weight", "logp", "tpsa"],
}

# Target gene / protein name regex.  Catches things like:
#   BRD4, EGFR, COX-1, COX2, HER2, p53, AKT1, JAK2, mTOR, BCR-ABL
_TARGET_RE = re.compile(
    r"\b(?:[A-Z]{2,5}[-]?\d{1,3}|[A-Z]{2,5}\d?|p\d{2,3}|m[A-Z]{2,4})\b"
)

# Common all-caps acronyms that are NOT biological targets — never return them
# from :func:`extract_targets` even though the regex matches.
_TARGET_ACRONYM_BLOCKLIST = {
    "SAR", "QSAR", "ADMET", "DMSO", "DMF", "DCM", "THF", "MEOH", "ETOH",
    "USA", "UK", "EU", "NIH", "FDA", "EMA", "WHO", "PDB", "PMID", "DOI",
    "NMR", "HPLC", "LCMS", "GCMS", "MS", "UV", "IR",
    "MD", "QM", "DFT",
    "DNA", "RNA", "MRNA", "ATP", "ADP", "GTP", "GDP", "CAMP", "CGMP",
    "CHEMBL",
    # Physicochemical / model-prediction labels — never biological targets
    "LOGP", "LOGD", "LOGS", "TPSA", "MW", "PSA", "HBA", "HBD", "PKA", "PKB",
    "SLOGP", "SMR",
}

# Common stop phrases / fillers we strip before extracting molecule candidates.
_STOP_PHRASES = [
    "what do we know about",
    "what do you know about",
    "tell me about",
    "tell me everything about",
    "give me a summary of",
    "give me the summary of",
    "summarize",
    "summarise",
    "summary of",
    "show me",
    "show",
    "find",
    "lookup",
    "look up",
    "search for",
    "search",
    "get",
    "fetch",
    "predict",
    "prediction for",
    "predictions for",
    "compare",
    "vs",
    "versus",
    "and",
    "what is the",
    "what is",
    "explain",
    "describe",
    "report on",
    "report for",
    "generate report for",
    "generate a report for",
    "key chembl assays and potency",
    "chembl assays and potency",
    "from chembl",
    "in chembl",
    "the",
    "a",
    "an",
    "of",
    "for",
    "this",
    "that",
    "these",
    "those",
    "molecule",
    "compound",
    "drug",
    "please",
]

# Generic question/utility words that should NEVER be returned as molecules.
_BLOCKLIST = {
    "report", "summary", "overview", "details", "info", "information",
    "study", "studies", "data", "compound", "compounds", "drug", "drugs",
    "molecule", "molecules", "structure", "structures", "smiles", "name",
    "what", "where", "when", "why", "how", "who", "which",
    "the", "a", "an", "and", "or", "of", "for", "to", "from",
    "with", "without", "about", "in", "on", "at",
    "please", "kindly",
    "predict", "prediction", "predictions", "compare", "comparison",
    "find", "lookup", "search", "get", "fetch", "show", "tell", "give",
    "summary", "summarize", "summarise",
    "retrieve", "retrieves", "retrieved", "retrieving",
    "cluster", "clusters", "clustering", "clustered",
    "trend", "trends", "trending",
    "functional", "groups", "group",
    "targeting", "targets", "targeted",
    "pka", "pkb", "pkc", "pki", "logp", "logd", "logs", "tpsa", "mw", "psa",
    "evidence", "assay", "assays", "potency", "toxicity", "solubility",
    "target", "targets", "activity", "activities",
    "chembl", "deepchem", "milvus",
    # Assay endpoint shorthands — must NEVER be parsed as molecules or SMILES
    "ic50", "ec50", "ki", "kd", "tm", "pic50", "pec50", "ld50", "ki50",
    "ligand", "ligands", "inhibitor", "inhibitors", "agonist", "agonists",
    "antagonist", "antagonists", "modulator", "modulators",
    "well", "known", "well-known", "list", "ranges", "range", "reported",
    # Sentence-stem verbs / connectors that appear capitalised at sentence start
    "starting", "start", "begin", "beginning", "identify", "propose",
    "investigate", "explore", "consider", "examine", "discover", "develop",
    "design", "evaluate", "assess", "analyze", "analyse", "review",
    "close", "closely", "near", "nearest", "best",
    # SAR / common chemistry terminology that isn't a molecule or target
    "sar", "qsar", "admet", "mini-sar", "scaffold", "scaffolds",
    "analog", "analogs", "analogue", "analogues",
    "from", "into", "between", "across", "through",
    # Organism words (we capture these in extract_filters; never treat as molecules)
    "human", "humans", "homo", "sapiens", "mouse", "mice", "rat", "rats",
    "rabbit", "dog", "cat", "monkey", "primate",
    # Activity / general-bio prose words
    "active", "inactive", "compounds", "compound",
    "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did",
    "can", "could", "should", "would", "may", "might",
    "this", "that", "these", "those",
    "yes", "no", "ok", "okay",
    # Cardiac ion channel gene symbols — targets, not marketed drug names
    "herg",
    "kcnh2",
    "off-target", "offtarget",
    "risk", "risks",
    "signals", "signal",
}

# Phrases / tokens that, when present, strongly indicate the input is English
# prose rather than a chemical-notation string.
_NL_INDICATORS = re.compile(
    r"\b(for|the|and|or|with|without|about|please|tell|show|find|list|"
    r"what|how|why|when|where|which|who|do|does|did|"
    r"compare|predict|summari[sz]e|describe|explain|report|overview|"
    r"ligand|ligands|inhibitor|inhibitors|target|targets|assay|assays|"
    r"ic50|ec50|kd|ki|pic50|potency|activity|toxicity|solubility|"
    r"reported|ranges?|well-known|known)\b",
    re.IGNORECASE,
)

# Tokens shaped like assay notation that must NEVER reach RDKit.
_ASSAY_TOKEN_RE = re.compile(
    r"\b(?:p?IC50|EC50|p?Ki|Kd|Tm|LD50|Ki50|pIC50|pEC50)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Stage 1 — Query-type classification
# ---------------------------------------------------------------------------

def classify_query_type(query: str) -> str:
    """Return one of:
    ``natural_language`` · ``smiles_only`` · ``mixed_query`` ·
    ``target_query`` · ``comparison_query``.

    The classifier is conservative — it errs on the side of NL so that
    SMILES parsing is only attempted on inputs that look like real
    chemical notation.
    """
    q = (query or "").strip()
    if not q:
        return "natural_language"

    lowered = q.lower()
    nl_hits = len(_NL_INDICATORS.findall(lowered))
    word_count = len(q.split())

    # ── Comparison ────────────────────────────────────────────────────────
    if re.search(r"\b(compare|comparison|vs|versus|difference between)\b", lowered):
        return "comparison_query"

    # ── Pure SMILES — single token, contains chemistry-only chars ────────
    if " " not in q and len(q) >= 4 and _looks_like_real_smiles(q):
        if not _NL_INDICATORS.search(lowered):
            return "smiles_only"

    # Real SMILES anywhere in the query — used both for mixed/target detection.
    has_real_smiles = any(_looks_like_real_smiles(tok) for tok in q.split())

    # ── Target-centric query (gene-shaped token + target/ligand vocabulary)
    target_hits = [t for t in extract_targets(q)]  # uses the same gate as the extractor
    has_target_word = bool(
        re.search(r"\b(target|ligand[s]?|inhibitor[s]?|agonist[s]?|antagonist[s]?)\b", lowered)
    )
    if target_hits and (has_target_word or nl_hits >= 2) and not has_real_smiles:
        return "target_query"

    # ── Mixed query: real SMILES AND noticeable NL prose ─────────────────
    if has_real_smiles and nl_hits >= 1:
        return "mixed_query"

    return "natural_language"


# ---------------------------------------------------------------------------
# Strict per-token SMILES guard
# ---------------------------------------------------------------------------

# Bond / branch / ring chars that MUST be present in a real SMILES token.
_SMILES_STRONG_CHARS = set("[]=#@")

# Valid SMILES atom letters (uppercase = aliphatic, lowercase = aromatic).
_SMILES_AROMATIC = set("bcnops")
_SMILES_ALIPHATIC_PREFIX = ("Br", "Cl")  # two-letter halogens worth recognising

def _has_valid_smiles_atoms(token: str) -> bool:
    """A token must contain at least one aromatic SMILES atom (b/c/n/o/p/s)
    or a meaningful aliphatic carbon/nitrogen/oxygen pattern.  This rules
    out fragments like ``d)/IC(`` whose only lowercase letter is ``d``."""
    if any(c in _SMILES_AROMATIC for c in token):
        return True
    # Two-letter halogens
    if any(p in token for p in _SMILES_ALIPHATIC_PREFIX):
        return True
    # Long aliphatic chain pattern: at least 2 of CC / CO / CN / CS / NC etc.
    aliphatic_pairs = sum(
        1
        for i in range(len(token) - 1)
        if token[i] in "CNOS" and token[i + 1] in "CNOS()=#"
    )
    return aliphatic_pairs >= 2

def _rdkit_validates(token: str) -> bool:
    """True iff RDKit can parse ``token`` as a chemical structure.

    Wrapped so the parser only attempts RDKit on candidates that already
    pass our cheap heuristic; failures are silent.
    """
    try:
        from app.services.rdkit_service import validate_smiles
        validate_smiles(token)
        return True
    except Exception:
        return False


def _looks_like_real_smiles(token: str) -> bool:
    """Reject assay notation (Kd/IC50, pIC50, etc.) and common false positives.

    A token only counts as SMILES if ALL of the following hold:
    * length ≥ 6
    * does NOT contain an assay-token regex match (Kd, IC50, pIC50…)
    * letter density ≤ 85 %
    * contains a strong SMILES char (``[]``, ``=``, ``#``, ``@``) OR a
      branch-with-aliphatic-atom pattern
    * contains valid SMILES atom letters (aromatic b/c/n/o/p/s OR an
      aliphatic CC/CN/CO/etc. backbone — NOT random lowercase like ``d``)
    """
    t = (token or "").strip()
    if len(t) < 6:
        return False
    if _ASSAY_TOKEN_RE.search(t):
        return False
    letters = sum(1 for c in t if c.isalpha())
    letter_ratio = letters / max(len(t), 1)
    if letter_ratio > 0.85:
        return False
    has_strong = bool(_SMILES_STRONG_CHARS.intersection(t))
    has_branch = "(" in t or ")" in t
    if not (has_strong or has_branch):
        return False
    if not _has_valid_smiles_atoms(t):
        return False
    for blk in ("Kd", "Ki", "IC50", "EC50", "pIC50", "pEC50", "Tm", "LD50"):
        if blk.lower() in t.lower():
            return False
    return True


# ---------------------------------------------------------------------------
# Public extraction helpers
# ---------------------------------------------------------------------------

def extract_molecule_candidates(query: str) -> List[str]:
    """Return ordered, de-duplicated molecule candidates extracted from ``query``.

    Order of precedence (high → low):
    1. ChEMBL IDs.
    2. SMILES tokens.
    3. Synonym lookups (brand → generic).
    4. Capitalised single-word tokens (proper nouns).
    5. Other content words (last resort).

    The function does NOT verify hits against ChEMBL — it is purely lexical.
    Use :func:`_verify_in_chembl` or downstream validation for that.
    """
    if not query:
        return []

    candidates: List[str] = []
    seen_lower: set[str] = set()
    suppressed_lower: set[str] = set()  # tokens we should NOT add later (e.g. brand replaced by generic)

    def _push(value: str) -> None:
        v = value.strip()
        if not v:
            return
        key = v.lower()
        if key in seen_lower or key in _BLOCKLIST or key in suppressed_lower:
            return
        seen_lower.add(key)
        candidates.append(v)

    # 1. ChEMBL IDs (strongest signal)
    for match in _CHEMBL_ID_RE.findall(query):
        _push(match.upper())

    # 2. SMILES tokens — only attempt extraction when the query looks like it
    #    could contain real chemical notation.  This is the critical guard
    #    that prevents assay text like "Kd/IC50" from reaching RDKit.
    qtype = classify_query_type(query)
    accepted_smiles: list[str] = []
    if qtype in {"smiles_only", "mixed_query"}:
        smiles_hits: list[str] = []
        for token in _SMILES_TOKEN_RE.findall(query):
            # Strip trailing punctuation that the regex may have captured
            cleaned = token.rstrip(".,;:!?")
            if not cleaned or len(cleaned) < 4:
                continue
            if _looks_like_real_smiles(cleaned) and _rdkit_validates(cleaned):
                smiles_hits.append(cleaned)
        # Sort longest first so we keep the parent SMILES and discard sub-tokens
        smiles_hits.sort(key=len, reverse=True)
        for s in smiles_hits:
            if any(s in larger for larger in accepted_smiles):
                continue
            accepted_smiles.append(s)

        # ── SINGLE-ENTITY RULE ────────────────────────────────────────────
        # Once we have a real (RDKit-validated) SMILES we treat it as the
        # one atomic molecule for this query.  Skip synonym scan, capitalised
        # tokens and the lowercase fallback — they only inject noise like
        # "LogP" or "proxy)" into the candidate list.
        if accepted_smiles:
            for s in accepted_smiles:
                _push(s)
            return candidates

    # 3. Synonyms (case-insensitive whole-word match) — replace brand with generic
    lowered = query.lower()
    for brand, generic in _SYNONYM_MAP.items():
        if re.search(rf"\b{re.escape(brand)}\b", lowered):
            suppressed_lower.add(brand)  # don't echo the brand later
            _push(generic)

    # 4. Capitalised tokens (likely drug names: "Aspirin", "Ibuprofen", "Warfarin")
    #    When the query is target-shaped we EXCLUDE gene-symbol tokens from
    #    molecule candidates (JAK2, BRD4, EGFR…) — those go to ``targets``
    #    only, never to RDKit / molecule resolution.
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-]+", query)
    target_tokens_upper = {t.upper() for t in extract_targets(query)}
    suppress_targets = qtype == "target_query" or bool(target_tokens_upper)

    for i, tok in enumerate(tokens):
        if not tok or tok.lower() in _BLOCKLIST:
            continue
        # Skip tokens that are part of an already-accepted SMILES string
        if any(tok in s for s in accepted_smiles):
            continue
        # Skip gene-symbol tokens in target queries (JAK2, BRD4, EGFR, …)
        if suppress_targets and tok.upper() in target_tokens_upper:
            continue
        if tok[0].isupper():
            # Skip the very first token if it looks like a question starter
            if i == 0 and tok.lower() in {"what", "how", "tell", "show", "give", "find",
                                          "compare", "predict", "summarize", "summarise"}:
                continue
            _push(tok)

    # 5. Last-resort: any remaining non-blocklisted content word ≥ 3 chars
    #    Still respects the target-suppression set so gene symbols don't leak.
    if not candidates:
        for tok in tokens:
            if tok.lower() not in _BLOCKLIST and len(tok) >= 3:
                if suppress_targets and tok.upper() in target_tokens_upper:
                    continue
                _push(tok)

    return candidates


_SAR_KEYWORDS_RE = re.compile(
    r"\b(scaffold[s]?|cluster(?:ing|ed)?|sar|structure[-\s]?activity|"
    r"functional\s+group[s]?|pka|pkb|trend[s]?|enrichment|murcko)\b",
    re.IGNORECASE,
)


def detect_intent(query: str) -> str:
    """Return one of:
    ``molecule_lookup`` · ``similarity_search`` · ``evidence_summary`` ·
    ``comparison`` · ``prediction`` · ``report_generation`` ·
    ``target_lookup`` · ``sar_analysis``.

    Heuristics are deliberately ordered — first matching rule wins.
    """
    q = (query or "").lower().strip()
    if not q:
        return "evidence_summary"

    # SAR analysis takes priority when scaffold / cluster / trend / pKa words
    # co-occur with target or ligand vocabulary.
    sar_hit = bool(_SAR_KEYWORDS_RE.search(q))
    target_hit = bool(re.search(
        r"\b(target|targets|ligand[s]?|inhibitor[s]?|agonist[s]?|antagonist[s]?|"
        r"modulator[s]?)\b", q,
    ))
    if sar_hit and target_hit:
        return "sar_analysis"

    if re.search(r"\b(compare|comparison|vs|versus|difference between)\b", q):
        return "comparison"

    if re.search(r"\b(similar|analog|analogue|nearest|closest)\b", q):
        return "similarity_search"

    if re.search(r"\b(predict|prediction|predicted|estimate|forecast)\b", q):
        return "prediction"

    if re.search(r"\b(report|generate(?:\s+a)?\s+report|full report|detailed report)\b", q):
        return "report_generation"

    if target_hit or re.search(r"\b(binding|interacts? with)\b", q):
        # "Find BRD4 inhibitors", "List BRD4 ligands", "What targets does X bind to?"
        return "target_lookup"

    if re.search(
        r"\b(what do (?:we|you) know|tell me about|summari[sz]e|overview|describe|"
        r"evidence|assay|potency|activity|activities|ic50|ec50|ki)\b",
        q,
    ):
        return "evidence_summary"

    # Single-word / single-entity question → molecule lookup
    if len(q.split()) <= 3:
        return "molecule_lookup"

    return "evidence_summary"


def extract_targets(query: str) -> List[str]:
    """Extract probable biological-target tokens.

    Conservative: matches gene-like tokens (BRD4, EGFR, COX-1, HER2, p53 …)
    Returns empty when nothing matches.
    """
    q = query or ""
    out: List[str] = []
    seen: set[str] = set()
    for raw in _TARGET_RE.findall(q):
        token = raw.strip()
        # Skip pure capitalised dictionary words like "WHAT", "FIND"
        if token.lower() in _BLOCKLIST:
            continue
        # Skip well-known non-target acronyms (SAR, ADMET, NMR, …)
        if token.upper() in _TARGET_ACRONYM_BLOCKLIST:
            continue
        # Must contain at least one digit OR be clearly an abbreviation (≥3 caps)
        has_digit = any(c.isdigit() for c in token)
        many_caps = sum(1 for c in token if c.isupper()) >= 3
        if not (has_digit or many_caps):
            continue
        key = token.upper()
        if key in seen:
            continue
        seen.add(key)
        out.append(token)
    return out


_GENERIC_TARGET_FAMILIES = {
    "GPCR", "GPCRS", "RTK", "RTKS", "KINASE", "KINASES", "PROTEASE",
    "PROTEASES", "PHOSPHATASE", "PHOSPHATASES", "TRANSPORTER",
    "TRANSPORTERS", "RECEPTOR", "RECEPTORS", "CHANNEL", "CHANNELS",
    "ENZYME", "ENZYMES", "TF", "NHRS",
}


def pick_primary_target(targets: List[str]) -> Optional[str]:
    """Choose the most specific target token from a list.

    Preference order:
    1. Tokens that contain a digit (DRD2, JAK2, COX1) over those that don't.
    2. Tokens NOT in :data:`_GENERIC_TARGET_FAMILIES` (GPCR, kinase, …).
    3. Longest token (more specific spelling like "BCR-ABL").
    4. Last-mentioned (the user usually narrows to the specific target).
    """
    if not targets:
        return None
    indexed = list(enumerate(targets))

    def score(item):
        i, t = item
        u = t.upper()
        has_digit = 1 if any(c.isdigit() for c in t) else 0
        not_generic = 0 if u in _GENERIC_TARGET_FAMILIES else 1
        return (has_digit, not_generic, len(t), i)

    indexed.sort(key=score, reverse=True)
    return indexed[0][1]


def extract_filters(query: str) -> Dict[str, object]:
    """Pull endpoint keywords / organism hints / numeric thresholds into a filters dict.

    Extracted keys:
    * ``endpoints``        — list[str] of standard activity types (IC50, Ki, …)
    * ``organism``         — rough hint ("Homo sapiens", "Rattus norvegicus", …)
    * ``value_max_nm``     — numeric cap, e.g. "IC50 < 50 nM" → 50.0
    * ``value_min_nm``     — numeric floor, e.g. "IC50 > 100 nM" → 100.0
    * ``exclude_cell_based`` — True when the query mentions binding-only / non-cell-based
    """
    q = (query or "").lower()
    filters: Dict[str, object] = {}

    endpoints: list[str] = []
    for term, canonical in _ENDPOINT_TERMS.items():
        if re.search(rf"\b{re.escape(term)}\b", q) and canonical not in endpoints:
            endpoints.append(canonical)
    if endpoints:
        filters["endpoints"] = endpoints

    if re.search(r"\b(homo sapiens|human)\b", q):
        filters["organism"] = "Homo sapiens"
    elif re.search(r"\b(rat|rattus)\b", q):
        filters["organism"] = "Rattus norvegicus"
    elif re.search(r"\b(mouse|mice|mus musculus)\b", q):
        filters["organism"] = "Mus musculus"

    # Numeric potency thresholds:  "<= 50 nM",  "< 100 nm",  "≤ 1 μM",  "> 10 nM"
    unit_to_nm = {"nm": 1.0, "um": 1000.0, "μm": 1000.0, "mm": 1_000_000.0,
                  "pm": 0.001, "fm": 0.000001}
    cmp_pattern = re.compile(
        r"(?:ic50|ec50|ki|kd|pchembl|potency)\s*([<>]=?|≤|≥)\s*([\d.]+)\s*(nm|um|μm|mm|pm|fm)?",
        re.IGNORECASE,
    )
    for op, val, unit in cmp_pattern.findall(q):
        try:
            v = float(val)
        except ValueError:
            continue
        u = (unit or "nm").lower()
        v_nm = v * unit_to_nm.get(u, 1.0)
        if op in ("<", "<=", "≤"):
            filters["value_max_nm"] = min(v_nm, float(filters.get("value_max_nm", v_nm)))
        elif op in (">", ">=", "≥"):
            filters["value_min_nm"] = max(v_nm, float(filters.get("value_min_nm", v_nm)))

    # Bare "< 50 nM" without an endpoint prefix
    if "value_max_nm" not in filters:
        m = re.search(r"([<>]=?|≤|≥)\s*([\d.]+)\s*(nm|um|μm|mm)\b", q, re.IGNORECASE)
        if m:
            op, val, unit = m.groups()
            try:
                v_nm = float(val) * unit_to_nm.get(unit.lower(), 1.0)
                if op in ("<", "<=", "≤"):
                    filters["value_max_nm"] = v_nm
                elif op in (">", ">=", "≥"):
                    filters["value_min_nm"] = v_nm
            except ValueError:
                pass

    if re.search(r"\b(non[-\s]?cell|binding[-\s]?only|biochemical)\b", q):
        filters["exclude_cell_based"] = True

    return filters


def _extract_requested_fields(query: str) -> List[str]:
    q = (query or "").lower()
    out: List[str] = []
    for field, terms in _REQUESTED_FIELD_TERMS.items():
        for t in terms:
            if re.search(rf"\b{re.escape(t)}\b", q):
                out.append(field)
                break
    # Stable de-dup
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


# ---------------------------------------------------------------------------
# ChEMBL resolution — turns lexical candidates into confidence-scored entities
# ---------------------------------------------------------------------------

# Default minimum confidence; below this a candidate is dropped entirely.
MIN_CONFIDENCE = 0.75


class ResolvedMolecule(BaseModel):
    """One molecule candidate resolved against ChEMBL with a confidence score."""
    candidate: str                    # original token from the user query
    chembl_id: Optional[str] = None
    pref_name: Optional[str] = None
    confidence: float = 0.0           # 0.0 – 1.0
    exact_match: bool = False         # candidate == ChEMBL pref_name (case-insensitive) / direct ID / valid SMILES


def _name_similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def resolve_candidates_with_confidence(
    candidates: List[str],
    *,
    min_confidence: float = MIN_CONFIDENCE,
) -> List[ResolvedMolecule]:
    """Resolve each lexical candidate against ChEMBL and assign a confidence.

    Confidence rules (highest → lowest):
    * ChEMBL ID present in input  → 1.0, exact_match=True
    * Real SMILES token           → 1.0, exact_match=True
    * Candidate equals top hit's pref_name (case-insensitive) → 1.0, exact_match=True
    * Otherwise                   → string similarity, with penalties:
        - ×0.7 if the candidate is not a substring of pref_name
        - ×0.6 if the candidate is shorter than 4 characters

    Candidates with confidence below ``min_confidence`` are discarded.
    """
    if not candidates:
        return []
    try:
        from app.services.chembl_service import ChemblService
        svc = ChemblService()
    except Exception as exc:
        logger.warning("[QPARSE] ChEMBL service unavailable: %s", exc)
        return []

    resolved: List[ResolvedMolecule] = []
    for cand in candidates:
        c = (cand or "").strip()
        if not c:
            continue

        # 1. ChEMBL ID — definitive
        if _CHEMBL_ID_RE.fullmatch(c):
            resolved.append(
                ResolvedMolecule(
                    candidate=c, chembl_id=c.upper(), pref_name=None,
                    confidence=1.0, exact_match=True,
                )
            )
            continue

        # 2. SMILES — definitive (downstream RDKit will validate structure)
        if _SMILES_REQUIRED_CHARS.intersection(c) and _looks_like_real_smiles(c):
            resolved.append(
                ResolvedMolecule(
                    candidate=c, chembl_id=None, pref_name=None,
                    confidence=1.0, exact_match=True,
                )
            )
            continue

        # 3. Name lookup
        try:
            rows = svc.search_by_name(c, limit=5)
        except Exception as exc:
            logger.debug("[QPARSE] name search error for %r: %s", c, exc)
            continue

        if not rows:
            continue

        top = rows[0]
        top_name = (top.get("pref_name") or "").strip()
        cid = top.get("chembl_id")

        # Exact case-insensitive name match → 1.0
        if top_name and top_name.lower() == c.lower():
            resolved.append(
                ResolvedMolecule(
                    candidate=c, chembl_id=cid, pref_name=top_name,
                    confidence=1.0, exact_match=True,
                )
            )
            continue

        # Otherwise compute similarity with penalties
        sim = _name_similarity(c, top_name) if top_name else 0.0
        if c.lower() not in top_name.lower():
            sim *= 0.7   # candidate isn't even a substring → likely unrelated
        if len(c) < 4:
            sim *= 0.6   # very short tokens are noisy ("CC", "PD")

        if sim >= min_confidence:
            resolved.append(
                ResolvedMolecule(
                    candidate=c, chembl_id=cid, pref_name=top_name or None,
                    confidence=round(sim, 3), exact_match=False,
                )
            )

    resolved.sort(key=lambda r: r.confidence, reverse=True)
    return resolved


# Back-compat shim for the previous internal helper name.
def _verify_in_chembl(candidates: List[str]) -> List[str]:
    """Return only candidate strings that resolve to ≥ MIN_CONFIDENCE in ChEMBL."""
    return [r.candidate for r in resolve_candidates_with_confidence(candidates)]


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def build_normalized_request(query: str, *, verify: bool = True) -> ParsedQuery:
    """Parse ``query`` end-to-end.

    Args:
        query: Raw user input.
        verify: If True (default) lexical molecule candidates are verified
            against ChEMBL via :func:`_verify_in_chembl`.  Disable for unit
            tests that should not hit Postgres.

    Returns:
        :class:`ParsedQuery` with all extracted entities.
    """
    raw = (query or "").strip()

    raw_candidates = extract_molecule_candidates(raw)
    targets = extract_targets(raw)

    # Strip targets that are substrings of any SMILES candidate — e.g. "CC1"
    # appears inside "CC1=CC(=O)NC(=O)N1" and isn't a biological target.
    smiles_in_candidates = [c for c in raw_candidates if _SMILES_REQUIRED_CHARS.intersection(c)]
    if smiles_in_candidates:
        targets = [t for t in targets if not any(t in s for s in smiles_in_candidates)]

    # Strip any candidate that is *actually* one of our extracted targets — gene
    # symbols (JAK2, BRD4, EGFR, …) belong in ``targets``, not ``molecules``.
    targets_upper = {t.upper() for t in targets}
    raw_candidates = [c for c in raw_candidates if c.upper() not in targets_upper]

    molecules = _verify_in_chembl(raw_candidates) if verify else raw_candidates

    intent = detect_intent(raw)
    qtype = classify_query_type(raw)

    # Promote target_query whenever a target was found and the query carries
    # no concrete molecule — catches phrasings like "List compounds active on
    # JAK2 with IC50 < 50 nM" that don't include the literal word
    # "target"/"inhibitor"/"ligand".  Preserve sar_analysis intent if already set.
    if targets and not molecules:
        qtype = "target_query"
        if intent != "sar_analysis":
            intent = "target_lookup"

    parsed = ParsedQuery(
        raw_query=raw,
        query_type=qtype,
        molecules=molecules,
        targets=targets,
        intent=intent,
        requested_fields=_extract_requested_fields(raw),
        filters=extract_filters(raw),
    )
    logger.info(
        "[QPARSE] raw=%r → type=%s intent=%s mol=%s tgt=%s fields=%s filters=%s",
        raw,
        parsed.query_type,
        parsed.intent,
        parsed.molecules,
        parsed.targets,
        parsed.requested_fields,
        parsed.filters,
    )
    return parsed
