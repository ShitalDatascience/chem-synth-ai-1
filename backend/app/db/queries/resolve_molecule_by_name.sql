SELECT
    md.chembl_id,
    md.pref_name,
    cs.canonical_smiles,
    cs.standard_inchi_key
FROM molecule_dictionary md
LEFT JOIN compound_structures cs
    ON md.molregno = cs.molregno
WHERE
    LOWER(TRIM(md.pref_name)) = LOWER(TRIM(%(name)s))
    OR md.pref_name ILIKE %(name_like)s
ORDER BY
    CASE
        WHEN LOWER(TRIM(md.pref_name)) = LOWER(TRIM(%(name)s)) THEN 1
        ELSE 2
    END,
    md.pref_name
LIMIT %(limit)s;
