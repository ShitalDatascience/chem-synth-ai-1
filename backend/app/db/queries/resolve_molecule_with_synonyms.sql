-- Resolve a free-text token to one or more ChEMBL molecules using:
--   1. exact pref_name match
--   2. molecule_synonyms exact match (Aspirin, Tylenol, AZD9291, Osimertinib, …)
--   3. fuzzy pref_name LIKE
--
-- Returns the union, ranked: exact pref_name → exact synonym → fuzzy.
WITH exact_pref AS (
    SELECT
        md.molregno, md.chembl_id, md.pref_name,
        cs.canonical_smiles,
        1.0::float AS confidence,
        'pref_name' AS match_type
    FROM public.molecule_dictionary md
    LEFT JOIN public.compound_structures cs ON cs.molregno = md.molregno
    WHERE UPPER(md.pref_name) = UPPER(%(name)s)
),
exact_syn AS (
    SELECT DISTINCT ON (md.molregno)
        md.molregno, md.chembl_id, md.pref_name,
        cs.canonical_smiles,
        0.95::float AS confidence,
        'synonym' AS match_type
    FROM public.molecule_synonyms ms
    JOIN public.molecule_dictionary md  ON md.molregno = ms.molregno
    LEFT JOIN public.compound_structures cs ON cs.molregno = md.molregno
    WHERE UPPER(ms.synonyms) = UPPER(%(name)s)
),
fuzzy_pref AS (
    SELECT
        md.molregno, md.chembl_id, md.pref_name,
        cs.canonical_smiles,
        0.70::float AS confidence,
        'fuzzy' AS match_type
    FROM public.molecule_dictionary md
    LEFT JOIN public.compound_structures cs ON cs.molregno = md.molregno
    WHERE UPPER(md.pref_name) LIKE UPPER(%(name_like)s)
      AND UPPER(md.pref_name) != UPPER(%(name)s)
    LIMIT 10
)
SELECT * FROM exact_pref
UNION ALL
SELECT * FROM exact_syn
UNION ALL
SELECT * FROM fuzzy_pref
LIMIT 25;
