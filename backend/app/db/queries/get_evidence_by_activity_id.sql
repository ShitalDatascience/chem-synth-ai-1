-- Minimal evidence fetch by activity_id (Phase 2).
-- Returns: assay info (if available), target info, standard_type, value_nm, pchembl.
SELECT
  act.activity_id,
  act.standard_type,
  act.standard_value,
  act.standard_units,
  act.pchembl_value,
  act.assay_id,
  ass.chembl_id                AS assay_chembl_id,
  ass.assay_type,
  ass.confidence_score,
  ass.description              AS assay_description,
  ass.tid,
  td.chembl_id                 AS target_chembl_id,
  td.pref_name                 AS target_pref_name,
  td.target_type,
  td.organism                  AS target_organism
FROM public.activities act
LEFT JOIN public.assays ass ON ass.assay_id = act.assay_id
LEFT JOIN public.target_dictionary td ON td.tid = ass.tid
WHERE act.activity_id = %(activity_id)s
LIMIT 1;

