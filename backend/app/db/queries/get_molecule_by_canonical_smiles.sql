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
FROM public.compound_structures cs
JOIN public.molecule_dictionary md ON md.molregno = cs.molregno
LEFT JOIN public.compound_properties cp ON cp.molregno = md.molregno
WHERE cs.canonical_smiles = %(smiles)s
LIMIT 1;
