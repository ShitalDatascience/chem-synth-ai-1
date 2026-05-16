-- Look up activity rows for a target name / ChEMBL target ID.
--
-- Filters
--   :name              text          target pref_name OR ChEMBL ID (case-insensitive)
--   :endpoints         text[]        accepted standard_type values, e.g. {'IC50','Ki'}
--   :value_max_nm      numeric|NULL  upper-bound for standard_value (nM)
--   :value_min_nm      numeric|NULL  lower-bound for standard_value (nM)
--   :organism          text|NULL     e.g. 'Homo sapiens' (ILIKE)
--   :exclude_cell_based bool         when TRUE we keep only assay_type 'B' (binding) and 'A' (ADMET)
--   :has_assay_allowlist bool        when TRUE, require assay_type ∈ :assay_types_allowlist
--   :assay_types_allowlist text[]      e.g. {'B','F'} for binding + functional inhibition
--   :standard_units_allowed text[]    default {'nM'}; safety mode may include percent-type units
--   :limit             int           row cap
WITH t AS (
    -- 1. Direct pref_name / ChEMBL ID match
    SELECT tid, chembl_id, pref_name, organism
    FROM public.target_dictionary
    WHERE UPPER(pref_name) LIKE UPPER(%(name_like)s)
       OR UPPER(chembl_id) = UPPER(%(name)s)

    UNION

    -- 2. Gene-symbol / synonym match (DRD2 → D(2) dopamine receptor, JAK2, BRD4, …)
    SELECT td.tid, td.chembl_id, td.pref_name, td.organism
    FROM public.component_synonyms cs
    JOIN public.target_components tc ON tc.component_id = cs.component_id
    JOIN public.target_dictionary  td ON td.tid          = tc.tid
    WHERE UPPER(cs.component_synonym) = UPPER(%(name)s)
)
SELECT
    md.chembl_id            AS chembl_id,
    md.pref_name            AS molecule_name,
    t.chembl_id             AS target_chembl_id,
    t.pref_name             AS target_pref_name,
    t.organism              AS organism,
    act.standard_type       AS standard_type,
    act.standard_value      AS standard_value,
    act.standard_units      AS standard_units,
    act.pchembl_value       AS pchembl_value,
    ass.assay_type          AS assay_type,
    ass.confidence_score    AS confidence_score,
    cs.canonical_smiles     AS canonical_smiles,
    cp.mw_freebase          AS mw_freebase,
    cp.alogp                AS alogp,
    cp.psa                  AS psa,
    cp.hba                  AS hba,
    cp.hbd                  AS hbd,
    cp.aromatic_rings       AS aromatic_rings,
    cp.qed_weighted         AS qed_weighted
FROM t
JOIN public.assays ass             ON ass.tid = t.tid
JOIN public.activities act         ON act.assay_id = ass.assay_id
JOIN public.molecule_dictionary md ON md.molregno = act.molregno
LEFT JOIN public.compound_structures cs ON cs.molregno = md.molregno
LEFT JOIN public.compound_properties  cp ON cp.molregno = md.molregno
WHERE act.standard_type = ANY(%(endpoints)s)
  AND act.standard_units = ANY(%(standard_units_allowed)s::text[])
  AND act.standard_value IS NOT NULL
  AND act.standard_value > 0
  AND (
    act.standard_units IS DISTINCT FROM 'nM'::text
    OR (
      (%(value_max_nm)s::numeric IS NULL OR act.standard_value <= %(value_max_nm)s::numeric)
      AND (%(value_min_nm)s::numeric IS NULL OR act.standard_value >= %(value_min_nm)s::numeric)
    )
  )
  AND (%(organism)s::text IS NULL OR t.organism ILIKE %(organism)s)
  AND (
    (%(has_assay_allowlist)s = FALSE AND (%(exclude_cell_based)s = FALSE OR ass.assay_type IN ('B','A')))
    OR
    (%(has_assay_allowlist)s = TRUE AND ass.assay_type = ANY(%(assay_types_allowlist)s::text[]))
  )
ORDER BY
    act.pchembl_value DESC NULLS LAST,
    act.standard_value ASC NULLS LAST
LIMIT %(limit)s;
