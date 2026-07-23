# Day 2B LIVE — Rejected-correct (B: correct candidate generated but rejected)

_Trace-verified against the EXACT Day 2 live rerun traces (day2_targeted_full_trace_db54..57). Candidate semantics judged manually per query. Totals: A(not-selected)=9, B(rejected)=0, C(no-correct)=12._

**0 cases.** In the Day 2 live traces, no *semantically correct* candidate was hard-rejected (fatal) or excluded before selection. Where correct candidates lost, they remained eligible (fatal_count=0) and lost on score/consensus — those are class A (see selection-loss analysis). Note DB54 t452's correct candidates were *soft*-penalised by a grain semantic-contract false-positive (scored 29, not fatal); it is reported under A with that reason.
