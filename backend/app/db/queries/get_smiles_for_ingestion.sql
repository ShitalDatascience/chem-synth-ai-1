-- Stream rows for Milvus ingestion (batched by molregno offset).
-- Used by jobs/build_milvus_index.py
SELECT
  md.chembl_id,
  md.molregno,
  md.pref_name,
  cs.canonical_smiles,
  cs.standard_inchi_key,
  cs.standard_inchi,
  cp.mw_freebase,
  cp.alogp,
  cp.hba,
  cp.hbd,
  cp.psa,
  cp.rtb,
  cp.ro3_pass,
  cp.num_ro5_violations,
  cp.full_mwt,
  cp.aromatic_rings,
  cp.heavy_atoms,
  cp.qed_weighted,
  cp.full_molformula,
  cp.np_likeness_score
FROM public.molecule_dictionary md
JOIN public.compound_structures cs ON cs.molregno = md.molregno
LEFT JOIN public.compound_properties cp ON cp.molregno = md.molregno
WHERE cs.canonical_smiles IS NOT NULL
  AND md.molregno > %(last_molregno)s
ORDER BY md.molregno
LIMIT %(batch_size)s;
