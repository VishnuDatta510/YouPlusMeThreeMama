from app.services.pico import extract_pico


def tags(text):
    return {(s["type"], s["text"]) for s in extract_pico(text)}


def test_rct_sentence():
    text = (
        "We enrolled adults with type 2 diabetes. Participants were randomized to metformin, "
        "compared with placebo. The primary outcome was change in HbA1c at 24 weeks."
    )
    spans = extract_pico(text)
    assert {s["type"] for s in spans} == {"P", "I", "C", "O"}
    assert all(text[s["start"] : s["end"]] == s["text"] for s in spans)
    assert ("P", "adults with type 2 diabetes") in tags(text)
    assert ("I", "randomized to metformin") in tags(text)
    assert ("C", "compared with placebo") in tags(text)


def test_versus_and_outcome():
    text = "Children aged 5-12 received drug A versus drug B; outcomes were measured at 6 months."
    assert tags(text) == {
        ("P", "Children aged 5-12"),
        ("I", "received drug A"),
        ("C", "versus drug B"),
        ("O", "outcomes were measured at 6 months"),
    }


def test_spans_split_at_next_trigger_and_never_overlap():
    spans = extract_pico("Patients with asthma treated with inhaled steroids versus placebo.")
    assert [(s["type"], s["text"]) for s in spans] == [
        ("P", "Patients with asthma"),
        ("I", "treated with inhaled steroids"),
        ("C", "versus placebo"),
    ]
    assert all(a["end"] <= b["start"] for a, b in zip(spans, spans[1:]))
    assert extract_pico("") == []
