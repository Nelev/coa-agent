from dataset.eval.check_extraction import compare
from dataset.ground_truth import truth
from dataset.make_data import scenarios


def test_a_perfect_extraction_has_no_differences():
    for s in scenarios():
        assert compare(truth(s), truth(s)) == []


def test_every_kind_of_difference_is_reported():
    want = truth(scenarios()[1])
    results = list(want.results)
    results[1] = results[1].model_copy(
        update={"value": 98.5, "page": 2, "confidence": 0.5}
    )
    got = want.model_copy(update={"lot": "X", "results": results[:-1]})
    text = "\n".join(compare(got, want))
    for expected in ("lot:", "5 rows", "Assay.value", "Assay.page", "confidence 0.5"):
        assert expected in text
