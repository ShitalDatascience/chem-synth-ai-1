-- Aggregates: total row count from activities for molregno; targets/types from joined rows.
WITH elig AS (
    SELECT
        a.activity_id,
        td.pref_name AS target_pref_name,
        CASE
            WHEN POSITION('prostaglandin g/h synthase 2' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                OR POSITION('prostaglandin-endoperoxide synthase 2' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                OR POSITION('ptgs2' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                OR (POSITION('cyclooxygenase' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                    AND POSITION('2' IN COALESCE(td.pref_name, '')) > 0
                    AND POSITION('1' IN COALESCE(td.pref_name, '')) = 0)
                THEN 'COX-2'
            WHEN POSITION('prostaglandin g/h synthase 1' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                OR POSITION('prostaglandin-endoperoxide synthase 1' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                OR POSITION('ptgs1' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                OR (POSITION('cyclooxygenase' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                    AND POSITION('1' IN COALESCE(td.pref_name, '')) > 0)
                THEN 'COX-1'
            WHEN POSITION('cyclooxygenase' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                AND POSITION('prostaglandin' IN LOWER(COALESCE(td.pref_name, ''))) = 0
                THEN 'COX-1'
            ELSE TRIM(COALESCE(td.pref_name, ''))
        END AS target_pref_name_norm,
        a.standard_type,
        s.assay_type,
        td.organism AS target_organism
    FROM public.activities a
    JOIN public.assays s ON a.assay_id = s.assay_id
    JOIN public.target_dictionary td ON s.tid = td.tid
    WHERE a.molregno = %(molregno)s
),
total AS (
    SELECT COUNT(*)::bigint AS n
    FROM public.activities a
    WHERE a.molregno = %(molregno)s
),
g AS (
    SELECT
        target_pref_name_norm AS target_pref_name,
        standard_type,
        COUNT(*)::bigint AS cnt
    FROM elig
    GROUP BY target_pref_name_norm, standard_type
),
target_rank AS (
    SELECT
        target_pref_name_norm AS target,
        COUNT(*)::bigint AS act_count,
        MAX(
            CASE
                WHEN LOWER(COALESCE(target_organism, '')) = 'homo sapiens' THEN 1
                ELSE 0
            END
        ) AS is_human,
        MAX(
            CASE
                WHEN POSITION('cox' IN LOWER(COALESCE(target_pref_name, ''))) > 0
                  OR POSITION('cyclooxygenase' IN LOWER(COALESCE(target_pref_name, ''))) > 0
                    THEN 1
                ELSE 0
            END
        ) AS is_enzyme
    FROM elig
    WHERE target_pref_name_norm IS NOT NULL
      AND target_pref_name_norm <> ''
      AND LOWER(TRIM(target_pref_name_norm)) NOT IN (
          'unchecked',
          'no relevant target',
          'non-protein target',
          'admet',
          'homo sapiens',
          'rattus norvegicus',
          'mus musculus',
          'plasma',
          'blood',
          'brain',
          'platelet',
          'hepatotoxicity',
          'serum',
          'liver',
          'kidney',
          'heart',
          'lung',
          'skin',
          'human',
          'mouse',
          'rat'
      )
      AND POSITION('molecular identity unknown' IN LOWER(target_pref_name_norm)) = 0
      AND POSITION('blood' IN LOWER(target_pref_name_norm)) = 0
      AND POSITION('brain' IN LOWER(target_pref_name_norm)) = 0
      AND POSITION('plasma' IN LOWER(target_pref_name_norm)) = 0
      AND POSITION('serum' IN LOWER(target_pref_name_norm)) = 0
      AND POSITION('platelet' IN LOWER(target_pref_name_norm)) = 0
      AND POSITION('unknown' IN LOWER(target_pref_name_norm)) = 0
    GROUP BY target_pref_name_norm
),
top_t AS (
    SELECT target, act_count
    FROM target_rank
    ORDER BY is_human DESC, is_enzyme DESC, act_count DESC, target ASC
    LIMIT 10
),
actypes AS (
    -- Pharmacological endpoints only (excludes clinical chem e.g. WEIGHT, RBC, HGB).
    SELECT
        standard_type AS st,
        COUNT(*)::bigint AS c
    FROM elig
    WHERE UPPER(TRIM(COALESCE(standard_type, ''))) IN (
        'IC50',
        'KI',
        'EC50',
        'ED50',
        'AC50',
        'GI50',
        'INHIBITION',
        'ACTIVITY'
    )
    GROUP BY standard_type
),
assays AS (
    SELECT
        COALESCE(assay_type, 'UNKNOWN') AS k,
        COUNT(*)::bigint AS c
    FROM elig
    GROUP BY COALESCE(assay_type, 'UNKNOWN')
),
target_rollup AS (
    SELECT
        target_pref_name_norm AS target_pref_name,
        target_organism,
        COUNT(*)::bigint AS act_count
    FROM elig
    GROUP BY target_pref_name_norm, target_organism
),
clusters AS (
    SELECT
        CASE
            -- Avoid percent signs in SQL text (psycopg placeholder parsing).
            WHEN POSITION('cyclooxygenase' IN LOWER(COALESCE(target_pref_name, ''))) > 0
              OR POSITION('prostaglandin g/h synthase' IN LOWER(COALESCE(target_pref_name, ''))) > 0
              OR POSITION('cox' IN LOWER(COALESCE(target_pref_name, ''))) > 0
                THEN 'enzyme'
            WHEN LOWER(COALESCE(target_organism, '')) = 'homo sapiens'
                THEN 'human'
            WHEN LOWER(COALESCE(target_organism, '')) IN ('mus musculus', 'rattus norvegicus', 'rattus')
                THEN 'rodent'
            ELSE 'others'
        END AS cluster,
        target_pref_name,
        act_count
    FROM target_rollup
    WHERE target_pref_name IS NOT NULL
      AND LOWER(TRIM(target_pref_name)) NOT IN (
          'unchecked',
          'no relevant target',
          'non-protein target',
          'admet'
      )
      AND POSITION('blood' IN LOWER(target_pref_name)) = 0
      AND POSITION('brain' IN LOWER(target_pref_name)) = 0
      AND POSITION('plasma' IN LOWER(target_pref_name)) = 0
      AND POSITION('serum' IN LOWER(target_pref_name)) = 0
      AND POSITION('platelet' IN LOWER(target_pref_name)) = 0
      AND POSITION('unknown' IN LOWER(target_pref_name)) = 0
),
clusters_merged AS (
    -- Merge duplicates within each cluster (e.g., same pref_name across organisms/whitespace/casing).
    SELECT
        cluster,
        MIN(TRIM(target_pref_name)) AS target,
        SUM(act_count)::bigint AS count
    FROM clusters
    WHERE TRIM(COALESCE(target_pref_name, '')) <> ''
    GROUP BY cluster, LOWER(TRIM(target_pref_name))
),
potency_rows AS (
    SELECT
        CASE
            WHEN POSITION('prostaglandin g/h synthase 2' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                OR POSITION('prostaglandin-endoperoxide synthase 2' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                OR POSITION('ptgs2' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                OR (POSITION('cyclooxygenase' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                    AND POSITION('2' IN COALESCE(td.pref_name, '')) > 0
                    AND POSITION('1' IN COALESCE(td.pref_name, '')) = 0)
                THEN 'COX-2'
            WHEN POSITION('prostaglandin g/h synthase 1' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                OR POSITION('prostaglandin-endoperoxide synthase 1' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                OR POSITION('ptgs1' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                OR (POSITION('cyclooxygenase' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                    AND POSITION('1' IN COALESCE(td.pref_name, '')) > 0)
                THEN 'COX-1'
            WHEN POSITION('cyclooxygenase' IN LOWER(COALESCE(td.pref_name, ''))) > 0
                AND POSITION('prostaglandin' IN LOWER(COALESCE(td.pref_name, ''))) = 0
                THEN 'COX-1'
            ELSE TRIM(COALESCE(td.pref_name, ''))
        END AS target,
        UPPER(TRIM(COALESCE(a.standard_type, ''))) AS standard_type,
        a.standard_value AS standard_value,
        LOWER(TRIM(COALESCE(a.standard_units, ''))) AS standard_units,
        CASE
            WHEN LOWER(TRIM(COALESCE(a.standard_units, ''))) = 'nm' THEN a.standard_value
            WHEN LOWER(TRIM(COALESCE(a.standard_units, ''))) IN ('um', 'µm') THEN a.standard_value * 1000.0
            WHEN LOWER(TRIM(COALESCE(a.standard_units, ''))) = 'mm' THEN a.standard_value * 1000000.0
            ELSE NULL
        END AS value_nm
    FROM public.activities a
    JOIN public.assays s ON a.assay_id = s.assay_id
    JOIN public.target_dictionary td ON s.tid = td.tid
    WHERE a.molregno = %(molregno)s
      AND a.standard_value IS NOT NULL
      AND a.standard_units IS NOT NULL
      AND a.standard_value > 0
      AND UPPER(TRIM(COALESCE(a.standard_type, ''))) IN ('IC50', 'KI', 'EC50')
),
major_targets AS (
    SELECT target
    FROM top_t
    LIMIT 5
),
potency_stats AS (
    SELECT
        pr.target,
        pr.standard_type AS activity_type,
        COUNT(*)::bigint AS sample_size,
        MIN(pr.value_nm) AS min_value,
        MAX(pr.value_nm) AS max_value,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pr.value_nm) AS median_value
    FROM potency_rows pr
    JOIN major_targets mt ON mt.target = pr.target
    WHERE pr.value_nm IS NOT NULL
      AND pr.value_nm > 0
      AND pr.value_nm <= 1000000000::double precision
      AND pr.target IS NOT NULL
      AND pr.target <> ''
    GROUP BY pr.target, pr.standard_type
),
target_clusters AS (
    SELECT json_agg(row_to_json(sub)) AS v
    FROM (
        SELECT
            cluster,
            SUM(act_count)::bigint AS total_activities,
            (
                SELECT json_agg(row_to_json(t2))
                FROM (
                    SELECT c2.target, c2.count
                    FROM clusters_merged c2
                    WHERE c2.cluster = c1.cluster
                    ORDER BY c2.count DESC, c2.target ASC
                    LIMIT 10
                ) t2
            ) AS top_targets
        FROM clusters c1
        GROUP BY cluster
        ORDER BY SUM(act_count) DESC
    ) sub
)
SELECT json_build_object(
    'total_activities', (SELECT n FROM total),
    'top_targets',
    COALESCE(
        (
            SELECT json_agg(row_to_json(sub))
            FROM (
                SELECT target, act_count AS count
                FROM top_t
                ORDER BY act_count DESC, target ASC
            ) sub
        ),
        '[]'::json
    ),
    'activity_types',
    COALESCE((SELECT json_object_agg(st, c) FROM actypes), '{}'::json),
    'assay_counts',
    COALESCE((SELECT json_object_agg(k, c) FROM assays), '{}'::json),
    'potency_stats_by_target',
    COALESCE(
        (
            SELECT json_agg(row_to_json(psub))
            FROM (
                SELECT
                    target,
                    activity_type,
                    median_value,
                    min_value,
                    max_value,
                    'nM'::text AS unit,
                    sample_size
                FROM potency_stats
                ORDER BY sample_size DESC, target ASC, activity_type ASC
                LIMIT 25
            ) psub
        ),
        '[]'::json
    ),
    'target_clusters',
    COALESCE((SELECT v FROM target_clusters), '[]'::json)
) AS evidence_bundle;
