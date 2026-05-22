from outfitmatch.metrics.outfit import compatibility_auc, fitb_accuracy


def test_fitb_accuracy_all_correct():
    assert fitb_accuracy([1, 0, 3], [1, 0, 3]) == 1.0


def test_fitb_accuracy_half():
    assert fitb_accuracy([0, 1], [0, 0]) == 0.5


def test_fitb_accuracy_empty():
    assert fitb_accuracy([], []) == 0.0


def test_compatibility_auc_separable():
    scores = [0.9, 0.8, 0.2, 0.1]
    labels = [1, 1, 0, 0]
    assert compatibility_auc(scores, labels) == 1.0


def test_compatibility_auc_random():
    scores = [0.5, 0.5, 0.5, 0.5]
    labels = [1, 0, 1, 0]
    assert 0.0 <= compatibility_auc(scores, labels) <= 1.0
