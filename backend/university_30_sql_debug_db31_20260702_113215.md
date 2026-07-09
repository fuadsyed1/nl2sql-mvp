# SpiderSQL University Research 30-Question Debug Results

## Summary

```json
{
  "database_name": "university_research",
  "database_id": 31,
  "total": 30,
  "exec_ok_count": 30,
  "exec_fail_count": 0,
  "query_family_count": 0,
  "llm_count": 30,
  "no_sql_count": 0,
  "repair_attempted_count": 8,
  "repair_selected_count": 5,
  "repair_selected_queries": [
    4,
    11,
    12,
    21,
    28
  ],
  "selected_source_breakdown": {
    "llm_sql_direct": 16,
    "llm_primary": 8,
    "llm_sql_repair": 5,
    "llm_variant": 1
  },
  "generated_at": "20260702_113215"
}
```

## Q01

**Question:** List active high-risk projects led by non-tenured faculty.

**Status:** EXEC_OK | rows=0 | selected=llm_sql_direct | family=normal_join_filter_group | conf=0.3 | time=18.215s

**SQL:**
```sql
SELECT p.project_id, p.project_title
FROM projects p
JOIN faculty f ON p.lead_faculty_id = f.faculty_id
WHERE p.status = 'active'
  AND p.risk_level = 'high'
  AND f.tenured != 'yes'
```

## Q02

**Question:** Find departments where every faculty member has at least one project.

**Status:** EXEC_OK | rows=6 | selected=llm_sql_direct | family=universal_every_all | conf=0.82 | time=15.33s

**SQL:**
```sql
SELECT d.department_name
FROM departments d
JOIN faculty f ON d.department_id = f.department_id
JOIN project_members pm ON f.faculty_id = pm.faculty_id
JOIN projects p ON pm.project_id = p.project_id
GROUP BY d.department_id
HAVING COUNT(DISTINCT f.faculty_id) = (
    SELECT COUNT(*)
    FROM faculty f2
    WHERE f2.department_id = d.department_id
)
```

## Q03

**Question:** List projects whose total approved expenses exceed their total awarded grant amount.

**Status:** EXEC_OK | rows=1 | selected=llm_primary | family=normal_join_filter_group | conf=0.3 | time=22.439s

**SQL:**
```sql
SELECT "projects"."project_id", "projects"."project_title", SUM("expenses"."amount") AS "total_approved_expenses", SUM("grants"."amount_awarded") AS "total_awarded_grant" FROM "grants" INNER JOIN "expenses" ON "grants"."grant_id" = "expenses"."grant_id" INNER JOIN "projects" ON "grants"."project_id" = "projects"."project_id" WHERE "expenses"."approved" = ? GROUP BY "projects"."project_id", "projects"."project_title" HAVING "total_approved_expenses" > "total_awarded_grant"
```

## Q04

**Question:** Find faculty who advise PhD students but are not members of any active project.

**Status:** EXEC_OK | rows=2 | selected=llm_sql_repair | family=normal_join_filter_group | conf=0.3 | time=27.572s

**Warnings:**
- all executed candidates failed hard semantic checks; low confidence
- LOW CONFIDENCE RESULT: every usable candidate failed hard semantic checks; this SQL is a best-effort fallback, NOT a normal success. Fatal reasons: illegal join: students.advisor_id = faculty.faculty_id

**SQL:**
```sql
SELECT f.faculty_id, f.faculty_name
FROM faculty f
WHERE EXISTS (
    SELECT 1
    FROM students s
    WHERE s.advisor_id = f.faculty_id
      AND s.degree_level = 'PhD'
)
AND NOT EXISTS (
    SELECT 1
    FROM project_members pm
    JOIN projects p ON pm.project_id = p.project_id
    WHERE pm.faculty_id = f.faculty_id
      AND p.status = 'active'
)
```

## Q05

**Question:** For each department, list the project with the highest total grant funding, including ties.

**Status:** EXEC_OK | rows=6 | selected=llm_sql_direct | family=derived_aggregate_cte | conf=0.85 | time=24.447s

**SQL:**
```sql
WITH dept_project_grants AS (
    SELECT 
        p.project_id,
        p.project_title,
        d.department_id,
        d.department_name,
        SUM(g.amount_awarded) AS total_grant_amount
    FROM projects p
    JOIN grants g ON p.project_id = g.project_id
    JOIN departments d ON p.department_id = d.department_id
    GROUP BY p.project_id, p.project_title, d.department_id, d.department_name
),
ranked_projects AS (
    SELECT 
        department_name,
        project_title,
        total_grant_amount,
        RANK() OVER (PARTITION BY department_id ORDER BY total_grant_amount DESC) AS grant_rank
    FROM dept_project_grants
)
SELECT 
    department_name,
    project_title
FROM ranked_projects
WHERE grant_rank = 1
```

## Q06

**Question:** Find projects with no publications but at least one federal grant.

**Status:** EXEC_OK | rows=3 | selected=llm_sql_direct | family=normal_join_filter_group | conf=0.3 | time=20.878s

**SQL:**
```sql
SELECT p.project_id, p.project_title
FROM projects p
WHERE NOT EXISTS (
    SELECT 1
    FROM publications pub
    WHERE pub.project_id = p.project_id
)
AND EXISTS (
    SELECT 1
    FROM grants g
    WHERE g.project_id = p.project_id
    AND g.grant_type = 'federal'
)
```

## Q07

**Question:** List students working on projects outside their own department.

**Status:** EXEC_OK | rows=0 | selected=llm_primary | family=normal_join_filter_group | conf=0.3 | time=18.933s

**SQL:**
```sql
SELECT DISTINCT "s"."student_id" AS "student_id", "s"."student_name" AS "student_name" FROM "students" AS "s" INNER JOIN "project_members" AS "pm" ON "s"."student_id" = "pm"."student_id" INNER JOIN "projects" AS "p" ON "pm"."project_id" = "p"."project_id" WHERE "s"."department_id" != "p"."department_id"
```

## Q08

**Question:** Find sponsors that fund projects in all colleges represented in the departments table.

**Status:** EXEC_OK | rows=7 | selected=llm_sql_direct | family=set_division_count_distinct | conf=0.85 | time=21.287s

**SQL:**
```sql
SELECT g.sponsor
FROM grants g
JOIN projects p ON g.project_id = p.project_id
JOIN departments d ON p.department_id = d.department_id
GROUP BY g.sponsor
HAVING COUNT(DISTINCT d.college) = (SELECT COUNT(DISTINCT college) FROM departments)
```

## Q09

**Question:** List equipment bought for projects whose lead faculty works in a different lab city than the department city.

**Status:** EXEC_OK | rows=30 | selected=llm_sql_direct | family=normal_join_filter_group | conf=0.3 | time=17.909s

**SQL:**
```sql
SELECT e.equipment_name, e.equipment_id
FROM equipment e
JOIN projects p ON e.project_id = p.project_id
JOIN faculty f ON p.lead_faculty_id = f.faculty_id
JOIN departments d ON p.department_id = d.department_id
WHERE f.lab_city != d.city
```

## Q10

**Question:** Find projects where every milestone is completed or late, with no pending milestones.

**Status:** EXEC_OK | rows=15 | selected=llm_sql_direct | family=universal_every_all | conf=0.82 | time=15.839s

**SQL:**
```sql
SELECT p.project_id, p.project_title
FROM projects p
WHERE NOT EXISTS (
    SELECT 1
    FROM milestones m
    WHERE m.project_id = p.project_id
      AND m.status = 'pending'
)
```

## Q11

**Question:** Find faculty whose projects have more distinct student members than faculty members.

**Status:** EXEC_OK | rows=0 | selected=llm_sql_repair | family=count_distinct_comparison | conf=0.8 | time=15.905s

**SQL:**
```sql
SELECT f.faculty_id, f.faculty_name
FROM faculty f
JOIN project_members pm ON f.faculty_id = pm.faculty_id
GROUP BY f.faculty_id, f.faculty_name
HAVING COUNT(DISTINCT pm.student_id) > COUNT(DISTINCT pm.faculty_id)
```

## Q12

**Question:** List projects funded by industry sponsors but with no approved software expenses.

**Status:** EXEC_OK | rows=3 | selected=llm_sql_repair | family=normal_join_filter_group | conf=0.3 | time=31.473s

**SQL:**
```sql
SELECT p.project_id, p.project_title
FROM projects p
WHERE EXISTS (
    SELECT 1
    FROM grants g
    WHERE g.project_id = p.project_id
      AND g.grant_type = 'industry'
      AND g.sponsor IN ('Google', 'Micron')
)
AND NOT EXISTS (
    SELECT 1
    FROM expenses e
    WHERE e.project_id = p.project_id
      AND e.category = 'software'
      AND e.approved = 'yes'
)
```

## Q13

**Question:** Find students whose advisor leads a project that the student is also a member of.

**Status:** EXEC_OK | rows=0 | selected=llm_primary | family=normal_join_filter_group | conf=0.3 | time=17.762s

**SQL:**
```sql
SELECT DISTINCT "students"."student_id", "students"."student_name" FROM "project_members" INNER JOIN "faculty" ON "project_members"."faculty_id" = "faculty"."faculty_id" INNER JOIN "projects" ON "project_members"."project_id" = "projects"."project_id" INNER JOIN "students" ON "project_members"."student_id" = "students"."student_id" WHERE "project_members"."student_id" = ? AND "project_members"."project_id" = ? AND "projects"."lead_faculty_id" = ? AND "students"."advisor_id" = ?
```

## Q14

**Question:** Find departments where the average impact score of publications is above the overall average publication impact score.

**Status:** EXEC_OK | rows=4 | selected=llm_sql_direct | family=derived_aggregate_cte | conf=0.85 | time=18.229s

**SQL:**
```sql
SELECT d.department_name
FROM departments d
JOIN projects p ON d.department_id = p.department_id
JOIN publications pub ON p.project_id = pub.project_id
GROUP BY d.department_id, d.department_name
HAVING AVG(pub.impact_score) > (SELECT AVG(impact_score) FROM publications)
```

## Q15

**Question:** List grants whose approved expenses are less than half of the awarded amount.

**Status:** EXEC_OK | rows=60 | selected=llm_primary | family=normal_join_filter_group | conf=0.3 | time=18.398s

**SQL:**
```sql
SELECT "grants"."amount_awarded", "grants"."grant_id", SUM("expenses"."amount") AS "total_approved_expenses" FROM "grants" INNER JOIN "expenses" ON "grants"."grant_id" = "expenses"."grant_id" WHERE "expenses"."approved" = ? GROUP BY "grants"."grant_id", "grants"."amount_awarded" HAVING "total_approved_expenses" < "amount_awarded"
```

## Q16

**Question:** Find project pairs in the same field that are led by faculty from different departments.

**Status:** EXEC_OK | rows=28 | selected=llm_sql_direct | family=self_join_pair | conf=0.9 | time=19.283s

**SQL:**
```sql
SELECT DISTINCT p1.project_id
FROM projects p1
JOIN projects p2 ON p1.field = p2.field AND p1.project_id < p2.project_id
JOIN faculty f1 ON p1.lead_faculty_id = f1.faculty_id
JOIN faculty f2 ON p2.lead_faculty_id = f2.faculty_id
JOIN departments d1 ON f1.department_id = d1.department_id
JOIN departments d2 ON f2.department_id = d2.department_id
WHERE d1.department_id != d2.department_id
```

## Q17

**Question:** List faculty who have open access publications but no equipment marked as shared on their led projects.

**Status:** EXEC_OK | rows=16 | selected=llm_primary | family=normal_join_filter_group | conf=0.3 | time=17.947s

**SQL:**
```sql
SELECT DISTINCT "faculty"."faculty_id", "faculty"."faculty_name" FROM "projects" INNER JOIN "equipment" ON "projects"."project_id" = "equipment"."project_id" INNER JOIN "faculty" ON "projects"."lead_faculty_id" = "faculty"."faculty_id" INNER JOIN "publications" ON "projects"."project_id" = "publications"."project_id" WHERE "publications"."open_access" = ? AND NOT EXISTS (SELECT 1 FROM "equipment" WHERE "projects"."project_id" = "equipment"."project_id" AND "projects"."lead_faculty_id" = "faculty"."faculty_id" AND "equipment"."shared" = ?)
```

## Q18

**Question:** Find active projects whose latest milestone is pending.

**Status:** EXEC_OK | rows=6 | selected=llm_sql_direct | family=latest_earliest_per_entity | conf=0.72 | time=21.046s

**SQL:**
```sql
WITH ranked_milestones AS (
    SELECT 
        m.project_id,
        m.status,
        m.due_date,
        ROW_NUMBER() OVER (PARTITION BY m.project_id ORDER BY m.due_date DESC) AS rn
    FROM milestones m
)
SELECT 
    p.project_id,
    p.project_title
FROM projects p
JOIN ranked_milestones rm ON p.project_id = rm.project_id
WHERE p.status = 'active'
  AND rm.rn = 1
  AND rm.status = 'pending'
```

## Q19

**Question:** Find departments whose students have participated in all project fields represented in projects.

**Status:** EXEC_OK | rows=6 | selected=llm_variant | family=set_division_count_distinct | conf=0.85 | time=23.582s

**SQL:**
```sql
SELECT DISTINCT "departments"."department_id", "departments"."department_name", COUNT("projects"."field") AS "student_fields_count", COUNT("projects"."field") AS "total_fields_count" FROM "project_members" INNER JOIN "projects" ON "project_members"."project_id" = "projects"."project_id" INNER JOIN "departments" ON "projects"."department_id" = "departments"."department_id" INNER JOIN "students" ON "project_members"."student_id" = "students"."student_id" GROUP BY "departments"."department_id", "departments"."department_name" HAVING "student_fields_count" = "total_fields_count"
```

## Q20

**Question:** List projects that have critical risk level and at least one unapproved expense.

**Status:** EXEC_OK | rows=2 | selected=llm_sql_direct | family=normal_join_filter_group | conf=0.3 | time=12.055s

**SQL:**
```sql
SELECT p.project_id, p.project_title
FROM projects p
JOIN expenses e ON p.project_id = e.project_id
WHERE p.risk_level = 'critical'
  AND e.approved = 'no'
```

## Q21

**Question:** List faculty who lead active projects but advise no PhD students.

**Status:** EXEC_OK | rows=4 | selected=llm_sql_repair | family=normal_join_filter_group | conf=0.3 | time=21.127s

**Warnings:**
- all executed candidates failed hard semantic checks; low confidence
- LOW CONFIDENCE RESULT: every usable candidate failed hard semantic checks; this SQL is a best-effort fallback, NOT a normal success. Fatal reasons: illegal join: students.advisor_id = faculty.faculty_id

**SQL:**
```sql
SELECT f.faculty_id, f.faculty_name
FROM faculty f
WHERE EXISTS (
    SELECT 1
    FROM projects p
    WHERE p.lead_faculty_id = f.faculty_id
      AND p.status = 'active'
)
AND NOT EXISTS (
    SELECT 1
    FROM students s
    WHERE s.advisor_id = f.faculty_id
      AND s.degree_level = 'PhD'
)
AND EXISTS (
    SELECT 1
    FROM project_members pm
    WHERE pm.faculty_id = f.faculty_id
)
```

## Q22

**Question:** Find projects where total equipment cost is greater than total approved equipment expenses charged to the project.

**Status:** EXEC_OK | rows=28 | selected=llm_primary | family=derived_aggregate_cte | conf=0.85 | time=20.267s

**SQL:**
```sql
SELECT "projects"."project_id", "projects"."project_title", SUM("equipment"."cost") AS "total_equipment_cost", SUM("expenses"."amount") AS "total_approved_expenses" FROM "projects" INNER JOIN "equipment" ON "projects"."project_id" = "equipment"."project_id" INNER JOIN "expenses" ON "projects"."project_id" = "expenses"."project_id" WHERE "expenses"."approved" = ? GROUP BY "projects"."project_id", "projects"."project_title" HAVING "total_equipment_cost" > "total_approved_expenses"
```

## Q23

**Question:** Find departments where every active project has at least one active grant.

**Status:** EXEC_OK | rows=6 | selected=llm_sql_direct | family=universal_every_all | conf=0.82 | time=27.865s

**SQL:**
```sql
SELECT d.department_id, d.department_name
FROM departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM projects p
    WHERE p.department_id = d.department_id
      AND p.status = 'active'
      AND NOT EXISTS (
          SELECT 1
          FROM grants g
          WHERE g.project_id = p.project_id
            AND g.active = 'yes'
      )
)
```

## Q24

**Question:** List students whose GPA is above the average GPA of students in their own department and who work on at least one high-risk project.

**Status:** EXEC_OK | rows=6 | selected=llm_primary | family=derived_aggregate_cte | conf=0.85 | time=21.74s

**SQL:**
```sql
SELECT DISTINCT "students"."department_id", "students"."student_id", "students"."student_name", AVG("students"."gpa") AS "dept_avg_gpa" FROM "departments" INNER JOIN "projects" ON "departments"."department_id" = "projects"."department_id" INNER JOIN "project_members" ON "projects"."project_id" = "project_members"."project_id" INNER JOIN "students" ON "departments"."department_id" = "students"."department_id" WHERE "projects"."risk_level" = ? GROUP BY "students"."department_id" HAVING "dept_avg_gpa" < "student_gpa"
```

## Q25

**Question:** Find projects where total student effort percent is greater than total faculty effort percent.

**Status:** EXEC_OK | rows=1 | selected=llm_sql_direct | family=derived_aggregate_cte | conf=0.85 | time=18.625s

**SQL:**
```sql
SELECT p.project_id, p.project_title
FROM projects p
JOIN project_members pm ON p.project_id = pm.project_id
GROUP BY p.project_id, p.project_title
HAVING SUM(CASE WHEN pm.role = 'Research Assistant' THEN pm.effort_percent ELSE 0 END) >
       SUM(CASE WHEN pm.role IN ('PI', 'Co-PI', 'Analyst', 'Engineer') THEN pm.effort_percent ELSE 0 END)
```

## Q26

**Question:** Find grants whose latest expense is unapproved.

**Status:** EXEC_OK | rows=13 | selected=llm_sql_direct | family=latest_earliest_per_entity | conf=0.72 | time=16.899s

**SQL:**
```sql
SELECT g.grant_id, g.project_id, g.sponsor, g.amount_awarded, g.grant_type, g.start_date, g.end_date, g.active
FROM grants g
JOIN expenses e ON g.grant_id = e.grant_id
WHERE e.expense_date = (
    SELECT MAX(e2.expense_date)
    FROM expenses e2
    WHERE e2.grant_id = g.grant_id
)
AND e.approved = 'no'
```

## Q27

**Question:** List pairs of faculty in the same department who are members of the same project.

**Status:** EXEC_OK | rows=111 | selected=llm_primary | family=self_join_pair | conf=0.9 | time=24.699s

**SQL:**
```sql
SELECT "f1"."faculty_name" AS "faculty_1_name", "f2"."faculty_name" AS "faculty_2_name" FROM "faculty" AS "f1" INNER JOIN "faculty" AS "f2" ON "f1"."faculty_id" < "f2"."faculty_id" INNER JOIN "project_members" AS "pm1" ON "f1"."faculty_id" = "pm1"."faculty_id" INNER JOIN "project_members" AS "pm2" ON "f2"."faculty_id" = "pm2"."faculty_id" AND "pm1"."project_id" = "pm2"."project_id" WHERE "f1"."department_id" = "f2"."department_id"
```

## Q28

**Question:** Find projects with publications after the end date of at least one grant for that project.

**Status:** EXEC_OK | rows=16 | selected=llm_sql_repair | family=normal_join_filter_group | conf=0.3 | time=23.636s

**SQL:**
```sql
SELECT DISTINCT p.project_id, p.project_title
FROM projects p
WHERE EXISTS (
    SELECT 1
    FROM publications pub
    JOIN grants g ON pub.project_id = g.project_id
    WHERE pub.project_id = p.project_id
      AND pub.publication_date > g.end_date
)
```

## Q29

**Question:** List sponsors whose total awarded amount is above the average total awarded amount per sponsor.

**Status:** EXEC_OK | rows=5 | selected=llm_sql_direct | family=derived_aggregate_cte | conf=0.85 | time=16.647s

**SQL:**
```sql
SELECT sponsor
FROM grants
GROUP BY sponsor
HAVING SUM(amount_awarded) > (
    SELECT AVG(total_amount)
    FROM (
        SELECT SUM(amount_awarded) AS total_amount
        FROM grants
        GROUP BY sponsor
    )
)
```

## Q30

**Question:** Find equipment categories used by projects in every department.

**Status:** EXEC_OK | rows=2 | selected=llm_sql_direct | family=universal_every_all | conf=0.6 | time=16.909s

**SQL:**
```sql
SELECT e.category
FROM equipment e
JOIN projects p ON e.project_id = p.project_id
JOIN departments d ON p.department_id = d.department_id
GROUP BY e.category
HAVING COUNT(DISTINCT d.department_id) = (SELECT COUNT(*) FROM departments)
```
