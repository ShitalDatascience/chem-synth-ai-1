"""Unit tests for fingerprint normalization (requires RDKit)."""

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("rdkit") is None,
    reason="rdkit required — e.g. conda activate chemdev_clean",
)


def test_canonicalize_ethanol():
    from app.services import rdkit_service

    n = rdkit_service.canonicalize_smiles("CCO")
    assert n
    assert n == rdkit_service.canonicalize_smiles(n)


def test_normalize_idempotent():
    from app.services import rdkit_service

    a = rdkit_service.normalize_for_fingerprint("CCO")
    b = rdkit_service.normalize_for_fingerprint(a)
    assert a == b


def test_morgan_fp_parity_report():
    from app.services import rdkit_service

    q = "CCO"
    stored = "CCO"  # as stored after ingestion normalization
    rep = rdkit_service.fp_parity_report(q, stored)
    assert rep["inchikey_match"] is True
    assert rep["normalized_smiles_match"] is True
