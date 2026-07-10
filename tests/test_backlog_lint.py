from tools.check_backlog import canonical_items, lint


def test_active_backlog_is_consistent():
    assert lint() == []


def test_canonical_queue_detects_duplicate_ids():
    text = "### Jetzt ausführbar\n1. **QA-11** — x\n2. **QA-11** — y\n### Wartet auf Produktentscheidung"
    assert canonical_items(text) == ["QA-11", "QA-11"]
