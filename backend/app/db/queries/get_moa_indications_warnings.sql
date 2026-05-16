-- Fetch MOA, drug indications, and drug warnings for a chembl_id.
-- Used in the report narrative section.

-- MOA
SELECT
  'moa'              AS section,
  dm.mechanism_of_action,
  dm.action_type,
  dm.direct_interaction,
  dm.disease_efficacy,
  dm.molecular_mechanism,
  mr.ref_type,
  mr.ref_id,
  mr.ref_url
FROM public.drug_mechanism dm
JOIN public.molecule_dictionary md ON md.molregno = dm.molregno
LEFT JOIN public.mechanism_refs mr ON mr.mec_id = dm.mec_id
WHERE md.chembl_id = %(chembl_id)s

UNION ALL

-- Indications
SELECT
  'indication'       AS section,
  di.efo_term        AS mechanism_of_action,
  di.max_phase_for_ind::text AS action_type,
  NULL::bool         AS direct_interaction,
  NULL::bool         AS disease_efficacy,
  NULL::bool         AS molecular_mechanism,
  ir.ref_type,
  ir.ref_id,
  ir.ref_url
FROM public.drug_indication di
JOIN public.molecule_dictionary md ON md.molregno = di.molregno
LEFT JOIN public.indication_refs ir ON ir.drugind_id = di.drugind_id
WHERE md.chembl_id = %(chembl_id)s

UNION ALL

-- Warnings
SELECT
  'warning'          AS section,
  dw.warning_type    AS mechanism_of_action,
  dw.warning_class   AS action_type,
  NULL::bool         AS direct_interaction,
  NULL::bool         AS disease_efficacy,
  NULL::bool         AS molecular_mechanism,
  wr.ref_type,
  wr.ref_id,
  wr.ref_url
FROM public.drug_warning dw
JOIN public.molecule_dictionary md ON md.molregno = dw.molregno
LEFT JOIN public.warning_refs wr ON wr.warning_id = dw.warning_id
WHERE md.chembl_id = %(chembl_id)s;
