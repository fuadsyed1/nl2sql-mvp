"""
test_relationship_detector_pk.py

Unit test for the spurious key-to-key edge suppression in relationship
detection. Tests the pure decision helper (no database required).

Run:  python -m tests.test_relationship_detector_pk
"""

from schema.relationship_detector import _is_pk_to_pk_crosslink


def _col(name, is_pk):
    return {"column_name": name, "is_primary_key_candidate": is_pk}


def test_spurious_cross_pk_is_suppressed():
    # patient_id (PK of patients) vs medication_id (PK of medications) -> drop.
    assert _is_pk_to_pk_crosslink(
        _col("patient_id", True), "patients", _col("medication_id", True), "medications")
    assert _is_pk_to_pk_crosslink(
        _col("student_id", True), "students", _col("course_id", True), "courses")
    print("[1] cross-table key<->key with different names is suppressed -> OK")


def test_flag_off_own_key_still_suppressed():
    # Even with is_primary_key_candidate False, the name names the table's key
    # (student_id in students, course_id in courses) -> still suppressed.
    assert _is_pk_to_pk_crosslink(
        _col("student_id", False), "students", _col("course_id", False), "courses")
    assert _is_pk_to_pk_crosslink(
        _col("patient_id", False), "patients", _col("medication_id", False), "medications")
    print("[2] flag-off own-key crosslink (by name) still suppressed -> OK")


def test_real_fk_is_kept():
    # enrollments.student_id (FK, not enrollments' own key) -> students.student_id.
    assert not _is_pk_to_pk_crosslink(
        _col("student_id", False), "enrollments", _col("student_id", True), "students")
    # medications.visit_id (FK) -> visits.visit_id.
    assert not _is_pk_to_pk_crosslink(
        _col("visit_id", False), "medications", _col("visit_id", True), "visits")
    print("[3] real FK (from-column not its own table's key) is kept -> OK")


def test_same_named_shared_key_is_kept():
    # 1:1 extension: profile.user_id (PK) <-> users.user_id (PK), same name -> keep.
    assert not _is_pk_to_pk_crosslink(
        _col("user_id", True), "profiles", _col("user_id", True), "users")
    print("[4] same-named key<->key (1:1 extension) is kept -> OK")


def main():
    tests = [
        test_spurious_cross_pk_is_suppressed,
        test_flag_off_own_key_still_suppressed,
        test_real_fk_is_kept,
        test_same_named_shared_key_is_kept,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- relationship_detector key suppression verified")


if __name__ == "__main__":
    main()
