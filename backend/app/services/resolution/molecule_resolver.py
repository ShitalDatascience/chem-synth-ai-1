"""Molecule resolver — Phase 2.

Uses ChemblService directly.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.services.chembl_service import ChemblService

logger = logging.getLogger(__name__)

# 🔧 DB CONFIG
config = {
    "host": "localhost",
    "database": "chembl",
    "user": "shitalkale",
    "password": ""
}

# 🔧 GLOBAL SERVICE (shared)
_svc = ChemblService(config)
_svc.connect()


class MoleculeResolver:

    @staticmethod
    def resolve_by_name(name: str) -> List[Dict[str, Any]]:
        try:
            return _svc.search_by_name(name)
        except Exception as exc:
            logger.error("[resolve_by_name] %s", exc)
            return []

    @staticmethod
    def resolve_by_chembl_id(chembl_id: str) -> Optional[Dict[str, Any]]:
        try:
            return _svc.get_by_chembl_id(chembl_id)
        except Exception as exc:
            logger.error("[resolve_by_chembl_id] %s", exc)
            return None

    @staticmethod
    def resolve_by_inchi_key(inchi_key: str) -> Optional[Dict[str, Any]]:
        try:
            return _svc.get_molecule_by_inchi_key(inchi_key)
        except Exception as exc:
            logger.error("[resolve_by_inchi_key] %s", exc)
            return None