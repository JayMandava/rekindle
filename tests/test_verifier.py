from rekindle.config import Merchant
from rekindle.models import Claim, DraftOut, Fact
from rekindle.verifier import verify

M = Merchant()
FACTS = [
    Fact(id="F1", label="Customer first name", value="Priya"),
    Fact(id="F2", label="Last session", value="Newborn session on 14 March 2025"),
    Fact(id="F3", label="Sessions booked so far", value="2"),
    Fact(id="F4", label="Child's first name", value="Aarav"),
    Fact(id="F5", label="Upcoming milestone", value="Aarav turns 1 year on 2 November 2026"),
]


def d(text, claims, offer=None, subject=None):
    return DraftOut(text=text, claims=[Claim(span=s, fact_id=f) for s, f in claims], offer_id=offer, subject=subject)


def test_grounded_draft_passes():
    v = verify(d("We still remember Aarav and the Newborn session.", [("Aarav", "F4"), ("Newborn session", "F2")]), FACTS, "whatsapp", M)
    assert v.passed and v.confidence > 0.7


def test_invented_number_blocked():
    v = verify(d("Aarav turns 2 years soon.", [("Aarav", "F4")]), FACTS, "whatsapp", M)
    assert not v.passed and any("numbers not supported" in i for i in v.hard_issues)


def test_invented_name_midsentence_blocked():
    v = verify(d("Our colleague Rohan will call about Aarav.", [("Aarav", "F4")]), FACTS, "whatsapp", M)
    assert not v.passed and any("names not in source data" in i for i in v.hard_issues)


def test_invented_name_at_sentence_start_fails_closed():
    v = verify(d("We remember Aarav. Rohan will call you.", [("Aarav", "F4")]), FACTS, "whatsapp", M)
    assert not v.passed and any("Rohan" in i for i in v.hard_issues)


def test_discount_without_approved_offer_blocked():
    v = verify(d("Aarav deserves a treat, enjoy 20% off.", [("Aarav", "F4")]), FACTS, "whatsapp", M)
    assert not v.passed and any("without an approved offer" in i for i in v.hard_issues)


def test_approved_offer_passes_and_unknown_offer_fails():
    ok = verify(d("Aarav is welcome back with a complimentary mini print set with your next session.", [("Aarav", "F4")], offer="O1"), FACTS, "whatsapp", M)
    assert ok.passed
    bad = verify(d("Aarav is welcome back.", [("Aarav", "F4")], offer="O9"), FACTS, "whatsapp", M)
    assert not bad.passed


def test_claim_must_quote_message_and_cite_real_fact():
    assert not verify(d("Hello there, Aarav.", [("Newborn session", "F2")]), FACTS, "whatsapp", M).passed
    assert not verify(d("Hello there, Aarav.", [("Aarav", "F99")]), FACTS, "whatsapp", M).passed
    assert not verify(d("Hello there, Aarav.", []), FACTS, "whatsapp", M).passed


def test_claim_unsupported_by_cited_fact():
    v = verify(d("Aarav loved the Newborn session.", [("Aarav loved the Newborn session", "F2")]), FACTS, "whatsapp", M)
    assert not v.passed


def test_policy_pressure_links_and_length():
    for text in ("Last chance for Aarav!", "Aarav, see www.example.com", "Aarav " + "x" * 300):
        assert not verify(d(text, [("Aarav", "F4")]), FACTS, "whatsapp", M).passed


def test_email_needs_subject():
    assert not verify(d("Hi Priya, Aarav has grown.", [("Aarav", "F4")]), FACTS, "email", M).passed
    assert verify(d("Hi Priya, Aarav has grown.", [("Aarav", "F4")], subject="Aarav"), FACTS, "email", M).passed


def test_hindi_message_numbers_still_checked():
    ok = verify(d("हमें Aarav का सत्र याद है।", [("Aarav", "F4")]), FACTS, "whatsapp", M)
    assert ok.passed
    bad = verify(d("हमें Aarav याद है, 50 रुपये की छूट।", [("Aarav", "F4")]), FACTS, "whatsapp", M)
    assert not bad.passed


def test_number_true_elsewhere_but_wrong_here_is_blocked():
    # "2" is a real fact (sessions booked) but it does not support "turns 2 years"
    v = verify(d("Aarav turns 2 years soon.", [("Aarav", "F4")]), FACTS, "whatsapp", M)
    assert not v.passed
    ok = verify(d("Aarav turns 1 year on 2 November 2026.", [("Aarav turns 1 year on 2 November 2026", "F5")]), FACTS, "whatsapp", M)
    assert ok.passed


def test_fabricated_recollection_without_numbers_or_names_is_blocked():
    v = verify(d("We remember Aarav. You told us you loved the outdoor shoot.", [("Aarav", "F4")]), FACTS, "whatsapp", M)
    assert not v.passed and any("unsupported recollection" in i for i in v.hard_issues)


def test_recollection_is_fine_when_covered_by_a_claim():
    v = verify(d("You loved the Newborn session on 14 March 2025.", [("Newborn session on 14 March 2025", "F2")]), FACTS, "whatsapp", M)
    assert not any("recollection" in i for i in v.hard_issues)


def test_long_uncited_sentence_blocked():
    long = "It would be wonderful to welcome your family back into the studio again sometime in the coming weeks for a relaxed afternoon."
    v = verify(d("We remember Aarav. " + long, [("Aarav", "F4")]), FACTS, "whatsapp", M)
    assert not v.passed and any("long sentence" in i for i in v.hard_issues)
