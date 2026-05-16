-- Detail rows for a single compound: filter by molregno (exact), not name/chembl pattern matching.
SELECT
    act.activity_id,
    act.molregno,
    md.chembl_id,
    act.assay_id,
    td.chembl_id AS target_chembl_id,
    td.pref_name AS target_pref_name,
    td.organism AS target_organism,
    ass.assay_type,
    act.standard_type,
    act.standard_value,
    act.standard_units,
    act.pchembl_value,
    ass.confidence_score
FROM public.activities act
JOIN public.molecule_dictionary md ON md.molregno = act.molregno
JOIN public.assays ass ON ass.assay_id = act.assay_id
JOIN public.target_dictionary td ON td.tid = ass.tid
WHERE act.molregno = %(molregno)s
ORDER BY ass.confidence_score DESC NULLS LAST, act.pchembl_value DESC NULLS LAST
LIMIT %(limit)s;
