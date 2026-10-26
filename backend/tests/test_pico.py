import pytest

from app.services.pico import extract_pico


def tags(text):
    return {(s["type"], s["text"]) for s in extract_pico(text)}


def test_rct_sentence():
    text = (
        "We enrolled adults with type 2 diabetes. Participants were randomized to metformin, "
        "compared with placebo. The primary outcome was change in HbA1c at 24 weeks."
    )
    spans = extract_pico(text)
    assert all(text[s["start"] : s["end"]] == s["text"] for s in spans)
    assert tags(text) == {
        ("P", "adults with type 2 diabetes"),
        ("I", "metformin"),
        ("C", "placebo"),
        ("O", "change in HbA1c"),
    }


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "Adults with type 2 diabetes received metformin or placebo for 12 weeks; "
            "the primary outcome was change in HbA1c.",
            {
                ("P", "Adults with type 2 diabetes"),
                ("I", "metformin"),
                ("C", "placebo"),
                ("O", "change in HbA1c"),
            },
        ),
        (
            "We randomized 120 patients with hypertension to amlodipine versus lisinopril. "
            "The primary endpoint was systolic blood pressure at 6 months.",
            {
                ("P", "patients with hypertension"),
                ("I", "amlodipine"),
                ("C", "lisinopril"),
                ("O", "systolic blood pressure"),
            },
        ),
        (
            "Children aged 6-12 years with asthma were assigned to inhaled budesonide or usual care. "
            "Outcomes included exacerbation rate.",
            {
                ("P", "Children aged 6-12 years with asthma"),
                ("I", "inhaled budesonide"),
                ("C", "usual care"),
                ("O", "exacerbation rate"),
            },
        ),
        (
            "Participants were randomly assigned to receive either 10 mg daily dapagliflozin or matching placebo.",
            {("I", "10 mg daily dapagliflozin"), ("C", "matching placebo")},
        ),
    ],
)
def test_trigger_words_and_durations_stay_out_of_spans(text, expected):
    assert tags(text) == expected


def test_spans_split_at_next_trigger_and_never_overlap():
    spans = extract_pico("Patients with asthma treated with inhaled steroids versus placebo.")
    assert [(s["type"], s["text"]) for s in spans] == [
        ("P", "Patients with asthma"),
        ("I", "inhaled steroids"),
        ("C", "placebo"),
    ]
    assert all(a["end"] <= b["start"] for a, b in zip(spans, spans[1:]))
    assert extract_pico("") == []


def test_age_range_and_trial_aim_do_not_cut_or_fake_spans():
    text = (
        "This trial aimed to evaluate whether patients aged 18 to 65 years with depression benefit from yoga."
    )
    assert tags(text) == {("P", "patients aged 18 to 65 years with depression")}


def test_decimals_do_not_end_a_span():
    assert ("P", "adults with HbA1c 6.8-8.5%") in tags("We enrolled adults with HbA1c 6.8-8.5%. Then...")


def test_results_lines_and_statistics_are_not_tagged():
    text = (
        "METHODS: Sixty patients with NAFLD were randomly assigned to receive EMPA 10 mg/day or PGZ 30 mg/day.\n"
        "RESULTS: Waist circumference fell more with EMPA compared to PGZ (-4.4 ± 2.39 vs -2.05, p<0.001) "
        "and with MET compared to baseline (P < 0.05)."
    )
    assert tags(text) == {("P", "patients with NAFLD"), ("I", "EMPA 10 mg/day"), ("C", "PGZ 30 mg/day")}
    assert tags("We compared drug A versus placebo in women with PCOS (P < 0.05).") == {
        ("C", "placebo"),
        ("P", "women with PCOS"),
    }
