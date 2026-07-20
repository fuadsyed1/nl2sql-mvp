SpiderSQL Day 1 missing source artifacts

Semantic audits:
- Sales DB54: sales_db54_manual_semantic_audit.md
- Students DB55: students_db55_manual_semantic_audit.csv (and .md report)
- Doctor DB56: doctor_db56_manual_semantic_audit.csv (and .md report)
- Player DB57: player_db57_manual_semantic_audit.csv (and .md report)

Containment summaries:
- spidersql_containment_case_summary.csv
- spidersql_containment_failed_expected_edges.csv

Important:
Use the actual filenames above in go_live_targets.json. Do not require invented names such as sales_db54_500_semantic_audit.csv. The Sales audit source is Markdown; the Day 1 parser should support both CSV and Markdown semantic-audit inputs.
