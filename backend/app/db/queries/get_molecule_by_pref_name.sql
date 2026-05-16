SELECT
  md.chembl_id,
  md.molregno,
  md.pref_name,
  cs.canonical_smiles,
  cs.standard_inchi,
  cs.standard_inchi_key,
  cp.mw_freebase,
  cp.alogp,
  cp.psa,
  cp.hba,
  cp.hbd,
  cp.rtb,
  cp.full_molformula
FROM public.molecule_dictionary md
JOIN public.compound_structures cs
  ON cs.molregno = md.molregno
LEFT JOIN public.compound_properties cp
  ON cp.molregno = md.molregno
WHERE LOWER(md.pref_name) = LOWER(%(name)s)
LIMIT 1;
