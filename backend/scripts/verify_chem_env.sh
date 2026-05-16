#!/usr/bin/env bash
# ChemSynth / discovery-agent — verify RDKit runs in the intended conda env.
#
#   conda activate chemdev_clean
#   ./scripts/verify_chem_env.sh
#
set -euo pipefail
if [[ -n "${CONDA_DEFAULT_ENV:-}" ]]; then
  echo "CONDA_DEFAULT_ENV=${CONDA_DEFAULT_ENV}"
else
  echo "WARNING: no active conda env; expected: chemdev_clean" >&2
fi
python <<'PY'
from rdkit import Chem

m = Chem.MolFromSmiles("CCO")
assert m is not None, "RDKit failed to parse ethanol"
print("RDKit OK:", Chem.MolToSmiles(m, canonical=True))
PY
echo "Chemistry environment check passed."
