"""
test_extractor_provider.py — Phase 6.5 step 5 (extractor -> provider migration).

Verifies the extractor now calls get_provider().generate(...) with the right
options, preserves output shapes, and degrades safely on provider failure.
Mocked provider only (no network). Run from the backend dir:

    python test_extractor_provider.py
"""

import ai_semantic_extractor as ext
from llm.base import GenerationResult
from llm.errors import ProviderError

GRAPH = {
    "tables": [
        {"table_name": "owners", "columns": [{"column_name": "oid"}, {"column_name": "lastname"}]},
        {"table_name": "pets", "columns": [{"column_name": "petid"}, {"column_name": "species"}]},
    ],
    "relationships": [],
}

VALID_IR = ('{"tables":["owners","pets"],'
            '"select":[{"table":"owners","column":"lastname"}],'
            '"filters":[{"table":"pets","column":"species","op":"=","value":"dog"}],'
            '"aggregations":[],"group_by":[],"having":[],"order_by":[],'
            '"limit":null,"distinct":true}')

VALID_SINGLE = ('{"entity":"owners","select":["lastname"],"filters":[],'
                '"aggregation":null,"group_by":null,"sort":null,"limit":null}')

EMPTY_IR = {
    "tables": [], "select": [], "filters": [], "aggregations": [],
    "group_by": [], "having": [], "order_by": [], "limit": None, "distinct": False,
}


class FakeProvider:
    def __init__(self, texts=None, raise_error=False):
        # `texts` may be a single string or a list consumed per call
        self.texts = texts
        self.raise_error = raise_error
        self.calls = []

    def generate(self, prompt, options=None):
        self.calls.append({"prompt": prompt, "options": options})
        if self.raise_error:
            raise ProviderError("provider down")
        if isinstance(self.texts, list):
            text = self.texts[min(len(self.calls) - 1, len(self.texts) - 1)]
        else:
            text = self.texts
        return GenerationResult(text=text or "", model="fake")


def use(fake):
    ext.get_provider = lambda: fake
    return fake


def test_multitable_calls_provider_with_options():
    fake = use(FakeProvider(VALID_IR))
    out = ext.extract_multitable_ir_extraction("Which owners have dogs?", GRAPH)
    assert len(fake.calls) == 1, "valid first response -> no retry"
    opts = fake.calls[0]["options"]
    assert opts == {"temperature": 0, "num_predict": 700, "think": False}, opts
    assert "/no_think" in fake.calls[0]["prompt"]      # /no_think preserved
    print("[1] multitable calls provider.generate with options + /no_think -> OK")


def test_multitable_output_shape_unchanged():
    use(FakeProvider(VALID_IR))
    out = ext.extract_multitable_ir_extraction("Which owners have dogs?", GRAPH)
    assert set(out.keys()) == set(EMPTY_IR.keys())     # canonical 9-key shape
    assert out["tables"] == ["owners", "pets"]
    assert out["select"] == [{"table": "owners", "column": "lastname"}]
    assert out["distinct"] is True
    print("[2] multitable normalized output shape unchanged -> OK")


def test_multitable_provider_failure_safe_empty():
    use(FakeProvider(raise_error=True))
    out = ext.extract_multitable_ir_extraction("Which owners have dogs?", GRAPH)
    assert out == EMPTY_IR, out                          # safe empty, no crash
    print("[3] provider failure -> safe empty extraction (no crash) -> OK")


def test_multitable_retry_uses_shorter_num_predict():
    # empty first response triggers the fallback prompt at num_predict=500
    fake = use(FakeProvider(texts=["", VALID_IR]))
    out = ext.extract_multitable_ir_extraction("Which owners have dogs?", GRAPH)
    assert len(fake.calls) == 2
    assert fake.calls[0]["options"]["num_predict"] == 700
    assert fake.calls[1]["options"]["num_predict"] == 500
    assert out["tables"] == ["owners", "pets"]
    print("[4] empty-first -> retry at num_predict=500 (fallback) -> OK")


def test_single_table_through_provider():
    fake = use(FakeProvider(VALID_SINGLE))
    data = ext.extract_semantics("show owners", "owners(oid, lastname)")
    assert data is not None and data["entity"] == "owners"
    assert fake.calls[0]["options"] == {"temperature": 0, "num_predict": 500, "think": False}
    assert "/no_think" in fake.calls[0]["prompt"]
    print("[5] single-table extract_semantics routed through provider -> OK")


def test_single_table_provider_failure_returns_none():
    use(FakeProvider(raise_error=True))
    assert ext.extract_semantics("show owners", "owners(oid)") is None
    print("[6] single-table provider failure -> None (safe) -> OK")


def main():
    original = ext.get_provider
    tests = [
        test_multitable_calls_provider_with_options,
        test_multitable_output_shape_unchanged,
        test_multitable_provider_failure_safe_empty,
        test_multitable_retry_uses_shorter_num_predict,
        test_single_table_through_provider,
        test_single_table_provider_failure_returns_none,
    ]
    try:
        passed = 0
        for t in tests:
            t()
            passed += 1
        print(f"\nRESULT: {passed}/{len(tests)} passed — extractor provider migration verified")
    finally:
        ext.get_provider = original


if __name__ == "__main__":
    main()