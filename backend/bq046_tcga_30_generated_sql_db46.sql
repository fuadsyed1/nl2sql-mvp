SELECT r.case_gdc_id, r.url
FROM rel15_fileData_current r
WHERE r.project_short_name = 'TCGA'
  AND r.project_disease_type = 'BRCA'
  AND r.file_state = 'current'
  AND r.case_gdc_id IN (
    SELECT case_gdc_id
    FROM rel15_fileData_current
    WHERE project_short_name = 'TCGA'
      AND project_disease_type = 'BRCA'
    GROUP BY case_gdc_id
    HAVING SUM(CASE WHEN experimental_strategy = 'Radiation Therapy' THEN 1 ELSE 0 END) = 0
       AND SUM(CASE WHEN experimental_strategy = 'Prior Malignancy' THEN 1 ELSE 0 END) = 0
  )
  AND r.case_gdc_id IN (
    SELECT case_gdc_id
    FROM rel15_fileData_current
    WHERE project_short_name = 'TCGA'
      AND project_disease_type = 'BRCA'
    GROUP BY case_gdc_id
    HAVING MIN(CAST(SUBSTR(created_datetime, 1, 4) AS INTEGER)) <= 30
  );

WITH current_files AS (
  SELECT 
    cases__case_id,
    COUNT(*) AS current_count,
    COUNT(DISTINCT COALESCE(file_id, file_gdc_id)) AS distinct_gdc_ids
  FROM (
    SELECT cases__case_id, file_id, NULL AS file_gdc_id FROM rel12_fileData_current
    UNION ALL
    SELECT cases__case_id, file_id, NULL AS file_gdc_id FROM rel13_fileData_current
    UNION ALL
    SELECT case_gdc_id AS cases__case_id, file_id, file_gdc_id FROM rel14_fileData_current
    UNION ALL
    SELECT case_gdc_id AS cases__case_id, file_id, file_gdc_id FROM rel15_fileData_current
  )
  GROUP BY cases__case_id
),
legacy_files AS (
  SELECT 
    cases__case_id,
    COUNT(*) AS legacy_count,
    COUNT(DISTINCT file_id) AS distinct_gdc_ids_legacy
  FROM (
    SELECT cases__case_id, file_id FROM rel12_fileData_legacy
    UNION ALL
    SELECT cases__case_id, file_id FROM rel13_fileData_legacy
  )
  GROUP BY cases__case_id
)
SELECT 
  c.cases__case_id,
  c.current_count,
  l.legacy_count,
  (c.distinct_gdc_ids + l.distinct_gdc_ids_legacy) AS total_distinct_gdc_ids
FROM current_files c
JOIN legacy_files l ON c.cases__case_id = l.cases__case_id
GROUP BY c.cases__case_id, c.current_count, l.legacy_count, c.distinct_gdc_ids, l.distinct_gdc_ids_legacy
HAVING c.current_count >= 1 AND l.legacy_count >= 1;

SELECT p.gdc_id, p.file_name
FROM PanCanAtlas_manifest p
WHERE NOT EXISTS (
    SELECT 1
    FROM rel12_caseData c
    WHERE c.file_id = p.gdc_id
);

SELECT "rel14_filedata_current"."file_gdc_id", COUNT(*) AS "url_count" FROM "rel14_filedata_current" GROUP BY "rel14_filedata_current"."file_gdc_id" HAVING "url_count" > ?;

SELECT gsa.baseid, gsa.file_name, gsa.release, gso.release
FROM GDC_sync_active_20190115 gsa
JOIN GDC_sync_obsolete_20190115 gso
ON gsa.baseid = gso.baseid;

SELECT T1.cases__project__disease_type
FROM rel12_fileData_current AS T1
GROUP BY T1.cases__project__disease_type
HAVING COUNT(DISTINCT T1.associated_entities__case_id) > (
  SELECT COUNT(DISTINCT T2.associated_entities__case_id)
  FROM rel12_fileData_legacy AS T2
  WHERE T2.cases__project__disease_type = T1.cases__project__disease_type
);

SELECT t1.project_id
FROM GDC_sync_active_20190104 t1
JOIN GDC_sync_active_20190115 t2
  ON t1.file_name = t2.file_name
WHERE t1.md5 != t2.md5;

WITH ranked_categories AS (
  SELECT
    project_disease_type,
    data_category,
    COUNT(DISTINCT file_id) AS distinct_file_count,
    SUM(file_size) AS total_file_size
  FROM rel14_fileData_current
  GROUP BY project_disease_type, data_category
),
ranked AS (
  SELECT
    project_disease_type,
    data_category,
    distinct_file_count,
    total_file_size,
    ROW_NUMBER() OVER (
      PARTITION BY project_disease_type
      ORDER BY distinct_file_count DESC
    ) AS rank_num
  FROM ranked_categories
)
SELECT
  project_disease_type,
  data_category
FROM ranked
WHERE rank_num <= 5;

-- NO SQL GENERATED

-- NO SQL GENERATED

SELECT c.file_id, c.file_name, c.data_type
FROM rel12_fileData_current c
JOIN rel12_fileData_legacy l ON c.cases__case_id = l.cases__case_id
JOIN DLBC_affected_files d ON c.cases__case_id = d.case_submitter_id AND c.file_name = d.file_name
WHERE c.cases__project__program__name = 'BRCA'
  AND c.data_type != l.data_type;

SELECT t1.type, t1.project_id
FROM GDC_sync_legacy_20190115 t1
WHERE NOT EXISTS (
    SELECT 1
    FROM GDC_sync_legacy_20190104 t2
    WHERE t1.file_name = t2.file_name
)
GROUP BY t1.type, t1.project_id;

SELECT c.case_gdc_id, c.gender, m.file_name
FROM clinical c
LEFT JOIN PanCanAtlas_manifest m ON c.case_gdc_id = m.gdc_id
WHERE c.gender = 'female'
AND NOT EXISTS (
    SELECT 1
    FROM PanCanAtlas_manifest m2
    WHERE m2.gdc_id = c.case_gdc_id
    AND m2.file_name IS NOT NULL
);

SELECT T1.case_gdc_id
FROM rel15_fileData_current T1
GROUP BY T1.case_gdc_id
HAVING COUNT(DISTINCT T1.data_category) = (
    SELECT COUNT(DISTINCT T2.data_category)
    FROM rel15_fileData_current T2
    WHERE T2.project_disease_type = (
        SELECT T3.project_disease_type
        FROM rel15_fileData_current T3
        WHERE T3.case_gdc_id = T1.case_gdc_id
        LIMIT 1
    )
);

SELECT "file_id" FROM "rel12_fileData_current" WHERE NOT EXISTS (SELECT 1 FROM "GDC_sync_active_20190104" WHERE "GDC_sync_active_20190104"."baseid" = "rel12_fileData_current"."file_id" AND "GDC_sync_active_20190104"."url" IS NOT NULL);

SELECT project_disease_type
FROM rel15_fileData_current
GROUP BY project_disease_type
HAVING COUNT(DISTINCT file_id) > 5
ORDER BY COUNT(DISTINCT file_id) DESC;

WITH current_counts AS (
  SELECT cases__case_id, COUNT(file_id) AS current_count
  FROM (
    SELECT cases__case_id, file_id, NULL AS file_gdc_id FROM rel12_fileData_current
    UNION ALL
    SELECT cases__case_id, file_id, NULL AS file_gdc_id FROM rel13_fileData_current
    UNION ALL
    SELECT case_gdc_id AS cases__case_id, file_id, file_gdc_id FROM rel14_fileData_current
    UNION ALL
    SELECT case_gdc_id AS cases__case_id, file_id, file_gdc_id FROM rel15_fileData_current
  )
  GROUP BY cases__case_id
),
legacy_counts AS (
  SELECT cases__case_id, COUNT(file_id) AS legacy_count
  FROM (
    SELECT cases__case_id, file_id, NULL AS file_gdc_id FROM rel12_fileData_legacy
    UNION ALL
    SELECT cases__case_id, file_id, NULL AS file_gdc_id FROM rel13_fileData_legacy
    UNION ALL
    SELECT case_gdc_id AS cases__case_id, file_id, file_gdc_id FROM rel14_fileData_legacy
  )
  GROUP BY cases__case_id
)
SELECT c.cases__case_id
FROM legacy_counts l
JOIN current_counts c ON l.cases__case_id = c.cases__case_id
WHERE l.legacy_count > c.current_count;

SELECT DISTINCT c.data_type
FROM rel12_fileData_current c
WHERE c.cases__project__program__name = 'BRCA'
  AND NOT EXISTS (
    SELECT 1
    FROM rel12_fileData_legacy l
    WHERE l.cases__project__program__name = 'BRCA'
      AND l.data_type = c.data_type
  );

SELECT case_gdc_id,
       SUM(CASE WHEN access = 'open' THEN 1 ELSE 0 END) AS open_count,
       SUM(CASE WHEN access = 'controlled' THEN 1 ELSE 0 END) AS controlled_count
FROM rel15_fileData_current
GROUP BY case_gdc_id
HAVING SUM(CASE WHEN access = 'open' THEN 1 ELSE 0 END) > 0
   AND SUM(CASE WHEN access = 'controlled' THEN 1 ELSE 0 END) > 0;

SELECT g.file_name, g.state, g.url
FROM GDC_sync_active_20190115 g
WHERE EXISTS (
    SELECT 1
    FROM GDC_sync_obsolete_20190115 o
    WHERE g.file_name = o.file_name
);

SELECT c.case_gdc_id, COUNT(*) AS aliquot_count, c.disease_code
FROM clinical c
WHERE EXISTS (
    SELECT 1 FROM clinical c2 WHERE c2.case_gdc_id = c.case_gdc_id
)
AND NOT EXISTS (
    SELECT 1 FROM rel14_fileData_current f WHERE f.case_gdc_id = c.case_gdc_id
)
GROUP BY c.case_gdc_id, c.disease_code;

WITH case_file_counts AS (
  SELECT
    project_short_name,
    project_disease_type,
    case_gdc_id,
    COUNT(file_id) AS file_count
  FROM rel14_fileData_current
  GROUP BY project_short_name, project_disease_type, case_gdc_id
),
project_averages AS (
  SELECT
    project_short_name,
    project_disease_type,
    AVG(file_count) AS avg_file_count
  FROM case_file_counts
  GROUP BY project_short_name, project_disease_type
),
disease_averages AS (
  SELECT
    project_disease_type,
    AVG(file_count) AS avg_file_count
  FROM case_file_counts
  GROUP BY project_disease_type
)
SELECT
  cfc.project_short_name,
  cfc.project_disease_type,
  cfc.case_gdc_id
FROM case_file_counts cfc
JOIN project_averages pa
  ON cfc.project_short_name = pa.project_short_name
  AND cfc.project_disease_type = pa.project_disease_type
JOIN disease_averages da
  ON cfc.project_disease_type = da.project_disease_type
WHERE cfc.file_count > pa.avg_file_count
   OR cfc.file_count > da.avg_file_count;

-- NO SQL GENERATED

SELECT g.url
FROM GDC_sync_obsolete_20190115 g
JOIN PanCanAtlas_manifest p ON g.file_name = p.file_name
JOIN rel12_caseData r ON g.file_name = r.file_id
WHERE g.state != 'obsolete'
AND NOT EXISTS (
    SELECT 1
    FROM GDC_sync_obsolete_20190115 g2
    WHERE g2.file_name = g.file_name
    AND g2.state = 'obsolete'
);

SELECT data_category, data_type
FROM rel15_fileData_current
GROUP BY data_category, data_type
HAVING COUNT(*) > 0;

SELECT cases__case_id
FROM (
    SELECT cases__case_id,
           SUM(CASE WHEN file_id IS NOT NULL AND file_name LIKE '%.gcs%' THEN 1 ELSE 0 END) AS current_gcs_count,
           SUM(CASE WHEN file_id IS NOT NULL AND file_name LIKE '%.gcs%' THEN 1 ELSE 0 END) AS current_total,
           SUM(CASE WHEN file_id IS NOT NULL AND file_name NOT LIKE '%.gcs%' THEN 1 ELSE 0 END) AS legacy_no_gcs_count
    FROM (
        SELECT cases__case_id, file_id, file_name, 'current' AS source
        FROM rel12_fileData_current
        UNION ALL
        SELECT cases__case_id, file_id, file_name, 'current' AS source
        FROM rel13_fileData_current
        UNION ALL
        SELECT case_gdc_id AS cases__case_id, file_id, file_name, 'current' AS source
        FROM rel14_fileData_current
        UNION ALL
        SELECT case_gdc_id AS cases__case_id, file_id, file_name, 'current' AS source
        FROM rel15_fileData_current
        UNION ALL
        SELECT cases__case_id, file_id, file_name, 'legacy' AS source
        FROM rel12_fileData_legacy
        UNION ALL
        SELECT cases__case_id, file_id, file_name, 'legacy' AS source
        FROM rel13_fileData_legacy
        UNION ALL
        SELECT case_gdc_id AS cases__case_id, file_id, file_name, 'legacy' AS source
        FROM rel14_fileData_legacy
        UNION ALL
        SELECT case_gdc_id AS cases__case_id, file_id, file_name, 'legacy' AS source
        FROM rel15_fileData_legacy
    ) AS all_files
    GROUP BY cases__case_id
) AS case_stats
WHERE current_gcs_count = current_total
  AND legacy_no_gcs_count > 0;

-- NO SQL GENERATED

SELECT f.id, f.file_name, f.file_size
FROM rel12_fileData_current f
JOIN rel12_fileData_current c ON f.cases__case_id = c.cases__case_id
WHERE f.data_category = 'Raw Sequencing Data'
  AND f.cases__project__program__name = 'BRCA'
  AND c.cases__project__disease_type = 'Breast Invasive Carcinoma'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__project_id = 'TCGA-BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__program__name = 'BRCA'
  AND c.cases__project__;

WITH ranked_files AS (
  SELECT
    case_gdc_id,
    data_type,
    file_name,
    updated_datetime,
    RANK() OVER (
      PARTITION BY case_gdc_id, data_type
      ORDER BY updated_datetime DESC
    ) AS rnk
  FROM rel15_fileData_current
)
SELECT
  case_gdc_id,
  data_type,
  file_name,
  updated_datetime
FROM ranked_files
WHERE rnk = 1;

SELECT T1.case_gdc_id, COUNT(DISTINCT T1.data_format) AS distinct_format_count
FROM rel15_fileData_current T1
WHERE T1.project_disease_type IS NOT NULL
GROUP BY T1.case_gdc_id, T1.project_disease_type
HAVING COUNT(DISTINCT T1.data_format) = (
    SELECT COUNT(DISTINCT T2.data_format)
    FROM rel15_fileData_current T2
    WHERE T2.project_disease_type = T1.project_disease_type
);

