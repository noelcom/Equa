"""Pipelinen genom HTTP-API:et: förtvätt, AI-tvätt, säkerhetskontroll och bedömning."""

from helpers import cv, make_pdf

from equa_backend.config import get_settings


def _analysis(client, user, files):
    res = client.post(
        "/analyses",
        headers=user.auth,
        data={"title": "Backendutvecklare", "job_ad": "Vi söker en utvecklare."},
        files=[("files", (name, pdf, "application/pdf")) for name, pdf in files],
    )
    assert res.status_code == 201, res.text
    return res.json()


def _run(client, user, analysis_id):
    return client.post(f"/analyses/{analysis_id}/run", headers=user.auth)


def _configure(client, **overrides):
    """Åsidosätter inställningar (t.ex. parallellgränsen) för det här testet."""
    settings = get_settings().model_copy(update=overrides)
    client.app.dependency_overrides[get_settings] = lambda: settings


def _get(client, user, analysis_id):
    res = client.get(f"/analyses/{analysis_id}", headers=user.auth)
    assert res.status_code == 200, res.text
    return res.json()


def test_run_ranks_all_candidates_by_score(client, make_user):
    user = make_user()
    analysis = _analysis(
        client,
        user,
        [
            ("a.pdf", cv("Backendutvecklare i fem år.\nPOÄNG 40")),
            ("b.pdf", cv("Senior backendutvecklare.\nPOÄNG 85")),
            ("c.pdf", cv("Utvecklare med bred erfarenhet.\nPOÄNG 62")),
        ],
    )

    assert _run(client, user, analysis["id"]).status_code == 202

    body = _get(client, user, analysis["id"])
    assert [c["alias"] for c in body["candidates"]] == [
        "Kandidat #2",
        "Kandidat #3",
        "Kandidat #1",
    ]
    assert [c["assessment"]["score"] for c in body["candidates"]] == [85, 62, 40]
    assert all(c["status"] == "done" for c in body["candidates"])


CONTACT_CV = """\
Anna Andersson
anna.andersson@example.com
Telefon: 070-123 45 67
Mobil: +46 70 123 45 67
Hemtelefon: 08-123 456 78
Personnummer: 900101-1234
LinkedIn: https://www.linkedin.com/in/anna-andersson
Portfolio: www.annas-portfolio.se
github.com/annaandersson
Backendutvecklare hos Acme AB 2018-2021
Systemutvecklare hos Beta AB 2021-2024, arbetade med ASP.NET
POÄNG 70"""

CONTACT_DETAILS = [
    "anna.andersson@example.com",
    "070-123 45 67",
    "70 123 45 67",
    "08-123 456 78",
    "900101-1234",
    "linkedin.com",
    "annas-portfolio",
    "github.com/annaandersson",
]


def test_contact_details_never_reach_the_ai_but_experience_does(
    client, make_user, anthropic_fake
):
    user = make_user()
    analysis = _analysis(client, user, [("anna.pdf", cv(CONTACT_CV))])

    _run(client, user, analysis["id"])

    sent = anthropic_fake.texts_sent("wash") + anthropic_fake.texts_sent("assess")
    assert sent, "AI:n anropades aldrig"
    for text in sent:
        for secret in CONTACT_DETAILS:
            assert secret not in text, f"{secret!r} nådde AI:n"
    # Yrkeshistoriken ska finnas kvar, annars förstörs bedömningen.
    washed_input = anthropic_fake.texts_sent("wash")[0]
    assert "2018-2021" in washed_input
    assert "2021-2024" in washed_input
    assert "ASP.NET" in washed_input


def test_cv_with_contact_details_left_after_ai_wash_is_stopped_before_assessment(
    client, make_user, anthropic_fake
):
    # AI-tvätten "glömmer" en e-postadress i det första CV:t.
    anthropic_fake.wash_override = lambda text: (
        text + "\nMejla hemlig.person@example.com" if "LÄCKAN" in text else text
    )
    user = make_user()
    analysis = _analysis(
        client,
        user,
        [
            ("a.pdf", cv("LÄCKAN Backendutvecklare.\nPOÄNG 90")),
            ("b.pdf", cv("Backendutvecklare.\nPOÄNG 60")),
        ],
    )

    _run(client, user, analysis["id"])

    body = _get(client, user, analysis["id"])
    # Det rena CV:t rankas. Det stoppade visas ändå, sist och utan poäng, aldrig som 0.
    assert [c["alias"] for c in body["candidates"]] == ["Kandidat #2", "Kandidat #1"]
    stopped = body["candidates"][1]
    assert stopped["status"] == "failed"
    assert stopped["assessment"] is None
    assert stopped["failure_reason"]
    # Det stoppade CV:t nådde aldrig bedömningssteget.
    assessed = anthropic_fake.texts_sent("assess")
    assert len(assessed) == 1
    assert all("hemlig.person" not in text for text in assessed)


def test_washed_text_is_never_stored(client, make_user, anthropic_fake, admin):
    anthropic_fake.wash_override = lambda text: text + "\nTVÄTTAD-MARKÖR-QX7"
    user = make_user()
    analysis = _analysis(client, user, [("a.pdf", cv("Backendutvecklare.\nPOÄNG 70"))])

    _run(client, user, analysis["id"])

    # Markören nådde bedömningssteget, så den finns i den tvättade texten...
    assert "TVÄTTAD-MARKÖR-QX7" in anthropic_fake.texts_sent("assess")[0]
    # ...men får inte finnas någonstans i det som sparats eller returneras.
    stored = admin.table("candidates").select("*").eq("analysis_id", analysis["id"])
    assert "TVÄTTAD-MARKÖR-QX7" not in str(stored.execute().data)
    assert "TVÄTTAD-MARKÖR-QX7" not in str(_get(client, user, analysis["id"]))
    assert "Backendutvecklare" not in str(stored.execute().data)


def test_ai_answer_that_breaks_the_schema_fails_the_cv_instead_of_scoring_it_zero(
    client, make_user, anthropic_fake
):
    def assess(text: str) -> dict:
        return {"score": 150} if "TRASIGT" in text else _valid_assessment(text)

    anthropic_fake.assess_override = assess
    user = make_user()
    analysis = _analysis(
        client,
        user,
        [
            ("a.pdf", cv("TRASIGT svar väntas.\nPOÄNG 30")),
            ("b.pdf", cv("Backendutvecklare.\nPOÄNG 55")),
        ],
    )

    _run(client, user, analysis["id"])

    body = _get(client, user, analysis["id"])
    assert [c["alias"] for c in body["candidates"]] == ["Kandidat #2", "Kandidat #1"]
    broken = body["candidates"][1]
    assert broken["status"] == "failed"
    assert broken["assessment"] is None
    assert "tolkas" in broken["failure_reason"]


def _valid_assessment(text: str) -> dict:
    from helpers import score_marker

    return {
        "score": score_marker(text) or 50,
        "years_experience": 3,
        "education_match": "Relevant.",
        "concrete_results": "Flera projekt.",
        "key_skills": ["Python"],
        "missing_requirements": "Inga.",
        "rationale": "Bra.",
    }


def test_progress_is_visible_through_the_api_while_the_run_is_in_progress(
    client, make_user, anthropic_fake
):
    _configure(client, max_parallel_cvs=1)  # en i taget gör ordningen deterministisk
    user = make_user()
    analysis = _analysis(
        client,
        user,
        [(f"{n}.pdf", cv(f"Utvecklare.\nPOÄNG {n}0")) for n in (1, 2, 3)],
    )
    seen = []

    def watch(_text):
        body = _get(client, user, analysis["id"])
        working = [c for c in body["candidates"] if c["status"] == "processing"]
        seen.append((body["state"], body["progress"], [c["step"] for c in working]))

    anthropic_fake.on_assess = watch

    _run(client, user, analysis["id"])

    # Vid varje bedömning syntes hur många som redan var klara, och att just ett CV
    # arbetade i bedömningssteget.
    assert seen == [
        ("running", {"total": 3, "finished": 0}, ["assessment"]),
        ("running", {"total": 3, "finished": 1}, ["assessment"]),
        ("running", {"total": 3, "finished": 2}, ["assessment"]),
    ]
    done = _get(client, user, analysis["id"])
    assert done["state"] == "finished"
    assert done["progress"] == {"total": 3, "finished": 3}


def test_parallel_limit_is_configurable(client, make_user, anthropic_fake):
    _configure(client, max_parallel_cvs=2)
    anthropic_fake.delay = 0.5  # så att anrop hinner överlappa
    user = make_user()
    analysis = _analysis(
        client,
        user,
        [(f"{n}.pdf", cv(f"Utvecklare.\nPOÄNG {n}0")) for n in (1, 2, 3, 4)],
    )

    _run(client, user, analysis["id"])

    assert anthropic_fake.max_in_flight == 2
    body = _get(client, user, analysis["id"])
    assert [c["status"] for c in body["candidates"]] == ["done"] * 4


def test_scanned_cv_without_text_is_listed_as_failed_and_never_sent_to_the_ai(
    client, make_user, anthropic_fake
):
    user = make_user()
    analysis = _analysis(
        client,
        user,
        [
            ("scan.pdf", make_pdf("")),  # ingen text, som en inskannad bild
            ("ok.pdf", cv("Backendutvecklare.\nPOÄNG 55")),
        ],
    )

    _run(client, user, analysis["id"])

    body = _get(client, user, analysis["id"])
    assert [c["alias"] for c in body["candidates"]] == ["Kandidat #2", "Kandidat #1"]
    scanned = body["candidates"][1]
    assert scanned["status"] == "failed"
    assert scanned["assessment"] is None
    assert "inskannad" in scanned["failure_reason"]
    assert len(anthropic_fake.texts_sent("wash")) == 1


def test_one_cv_crashing_does_not_stop_the_others(client, make_user, anthropic_fake):
    def wash(text: str) -> str:
        if "KRASCH" in text:
            raise RuntimeError("Anthropic låg nere")
        return text

    anthropic_fake.wash_override = wash
    user = make_user()
    analysis = _analysis(
        client,
        user,
        [
            ("a.pdf", cv("KRASCH Utvecklare.\nPOÄNG 80")),
            ("b.pdf", cv("Utvecklare.\nPOÄNG 45")),
        ],
    )

    assert _run(client, user, analysis["id"]).status_code == 202

    body = _get(client, user, analysis["id"])
    assert [c["status"] for c in body["candidates"]] == ["done", "failed"]
    assert body["candidates"][1]["assessment"] is None
    assert body["state"] == "finished"


def test_run_requires_login_and_own_analysis_and_something_to_run(client, make_user):
    alice, bob = make_user(), make_user()
    analysis = _analysis(client, alice, [("a.pdf", cv("Utvecklare.\nPOÄNG 50"))])
    url = f"/analyses/{analysis['id']}/run"

    assert client.post(url).status_code == 401
    assert client.post(url, headers=bob.auth).status_code == 404

    assert client.post(url, headers=alice.auth).status_code == 202
    # Redan körd: inget nytt att köra.
    assert client.post(url, headers=alice.auth).status_code == 409


def test_wash_uses_haiku_assessment_uses_sonnet_and_shared_prompt_is_cached(
    client, make_user, anthropic_fake
):
    user = make_user()
    analysis = _analysis(
        client,
        user,
        [
            ("a.pdf", cv("Utvecklare.\nPOÄNG 50")),
            ("b.pdf", cv("Utvecklare.\nPOÄNG 60")),
        ],
    )

    _run(client, user, analysis["id"])

    wash = [kw for kind, kw in anthropic_fake.calls if kind == "wash"]
    assess = [kw for kind, kw in anthropic_fake.calls if kind == "assess"]
    assert len(wash) == len(assess) == 2
    assert all("haiku" in kw["model"] for kw in wash)
    assert all("sonnet" in kw["model"] for kw in assess)
    for kw in assess:
        # Instruktionen och annonsen är gemensamma för alla CV:n och cachas. CV:t, som
        # skiljer sig åt, kommer sist och cachas inte.
        assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
        job_ad, cv_text = kw["messages"][0]["content"]
        assert job_ad["cache_control"] == {"type": "ephemeral"}
        assert "cache_control" not in cv_text
