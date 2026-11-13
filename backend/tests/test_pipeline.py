"""Pipelinen genom HTTP-API:et: förtvätt, AI-tvätt, säkerhetskontroll och bedömning."""

from helpers import cv, file_exists, make_pdf, original_paths

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


def test_truncated_assessment_gets_its_own_reason_and_is_logged_not_scored_zero(
    client, make_user, anthropic_fake, monkeypatch, caplog
):
    from equa_backend import pipeline

    monkeypatch.setattr(pipeline, "ASSESS_MAX_TOKENS", 1_000)
    user = make_user()
    analysis = _analysis(client, user, [("a.pdf", cv("Utvecklare.\nPOÄNG 66"))])

    with caplog.at_level("WARNING"):
        _run(client, user, analysis["id"])

    [candidate] = _get(client, user, analysis["id"])["candidates"]
    assert candidate["status"] == "failed"
    assert candidate["assessment"] is None
    assert candidate["failure_reason"] == "Bedömningen blev för lång och avbröts."
    assert "max_tokens" in caplog.text
    assert "Utvecklare" not in caplog.text


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


def _long_cv(chars: int, score: int) -> bytes:
    line = (
        "Ledde migreringen av tolv tjänster till Kubernetes utan driftstopp, 2021-2023."
    )
    lines = [line] * (chars // (len(line) + 1))
    return cv("\n".join(lines) + f"\nPOÄNG {score}")


def test_long_cv_is_scored_although_thinking_shares_the_token_budget(
    client, make_user, anthropic_fake
):
    # Ungefär sex sidor svensk text, som mätningen i #24. Thinking räknas mot max_tokens
    # och fick tidigare både tvätt och bedömning att klippas.
    user = make_user()
    analysis = _analysis(client, user, [("lang.pdf", _long_cv(20_000, 77))])

    _run(client, user, analysis["id"])

    [candidate] = _get(client, user, analysis["id"])["candidates"]
    assert candidate["status"] == "done", candidate["failure_reason"]
    assert candidate["assessment"]["score"] == 77


def test_cv_far_beyond_ten_pages_is_stopped_as_too_long(
    client, make_user, anthropic_fake
):
    user = make_user()
    analysis = _analysis(client, user, [("enorm.pdf", _long_cv(60_000, 77))])

    _run(client, user, analysis["id"])

    [candidate] = _get(client, user, analysis["id"])["candidates"]
    assert candidate["status"] == "failed"
    assert candidate["failure_reason"] == "CV:t var för långt för att anonymiseras."
    assert anthropic_fake.texts_sent("assess") == []


def test_empty_wash_answer_fails_the_cv_instead_of_scoring_it(
    client, make_user, anthropic_fake
):
    # Haiku svarar tomt (t.ex. en vägran) för det första CV:t.
    anthropic_fake.wash_override = lambda text: "" if "VÄGRAN" in text else text
    user = make_user()
    analysis = _analysis(
        client,
        user,
        [
            ("a.pdf", cv("VÄGRAN Utvecklare.\nPOÄNG 90")),
            ("b.pdf", cv("Utvecklare.\nPOÄNG 60")),
        ],
    )

    _run(client, user, analysis["id"])

    body = _get(client, user, analysis["id"])
    assert [c["alias"] for c in body["candidates"]] == ["Kandidat #2", "Kandidat #1"]
    stopped = body["candidates"][1]
    assert stopped["status"] == "failed"
    assert stopped["assessment"] is None
    assert "anonymiseras" in stopped["failure_reason"]
    assert len(anthropic_fake.texts_sent("assess")) == 1


PHONE_FORMATS = [
    "070 - 123 45 67",
    "(070) 123 45 67",
    "0046 70 123 45 67",
    "0046-70-123 45 67",
    "+46 (0)70-123 45 67",
]


def test_phone_numbers_in_unusual_formats_never_reach_the_ai(
    client, make_user, anthropic_fake
):
    user = make_user()
    body = "\n".join(f"Ring {n}" for n in PHONE_FORMATS)
    analysis = _analysis(
        client, user, [("a.pdf", cv(f"{body}\nUtvecklare 2018-2021.\nPOÄNG 60"))]
    )

    _run(client, user, analysis["id"])

    sent = anthropic_fake.texts_sent("wash")[0]
    assert "123" not in sent and "45 67" not in sent
    assert "2018-2021" in sent


def test_safety_check_stops_unusual_phone_formats_left_by_the_ai_wash(
    client, make_user, anthropic_fake
):
    anthropic_fake.wash_override = lambda text: text + "\nRing (070) 123 45 67"
    user = make_user()
    analysis = _analysis(client, user, [("a.pdf", cv("Utvecklare.\nPOÄNG 60"))])

    _run(client, user, analysis["id"])

    stopped = _get(client, user, analysis["id"])["candidates"][0]
    assert stopped["status"] == "failed"
    assert anthropic_fake.texts_sent("assess") == []


def _status_error(cls, status_code):
    import httpx

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("fel", response=httpx.Response(status_code, request=request), body=None)


def _flaky(anthropic_fake, kind, error, failures):
    """Låter de första `failures` anropen av `kind` kasta `error`, därefter går de bra."""
    real = getattr(anthropic_fake, kind)
    state = {"left": failures}

    def wrapper(**kwargs):
        if state["left"] > 0:
            state["left"] -= 1
            raise error
        return real(**kwargs)

    setattr(anthropic_fake, kind, wrapper)


def test_transient_anthropic_errors_are_retried_and_the_cv_still_gets_scored(
    client, make_user, anthropic_fake
):
    import anthropic

    _configure(client, anthropic_retry_backoff_seconds=0, anthropic_max_attempts=3)
    _flaky(anthropic_fake, "wash", _status_error(anthropic.RateLimitError, 429), 1)
    _flaky(
        anthropic_fake, "assess", _status_error(anthropic.InternalServerError, 503), 2
    )
    user = make_user()
    analysis = _analysis(client, user, [("a.pdf", cv("Utvecklare.\nPOÄNG 66"))])

    _run(client, user, analysis["id"])

    candidate = _get(client, user, analysis["id"])["candidates"][0]
    assert candidate["status"] == "done"
    assert candidate["assessment"]["score"] == 66


def test_anthropic_outage_that_outlasts_the_retries_gets_a_clear_reason(
    client, make_user, anthropic_fake
):
    import anthropic
    import httpx

    _configure(client, anthropic_retry_backoff_seconds=0, anthropic_max_attempts=2)
    error = anthropic.APITimeoutError(
        httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )
    _flaky(anthropic_fake, "wash", error, 99)
    user = make_user()
    analysis = _analysis(client, user, [("a.pdf", cv("Utvecklare.\nPOÄNG 66"))])

    _run(client, user, analysis["id"])

    candidate = _get(client, user, analysis["id"])["candidates"][0]
    assert candidate["status"] == "failed"
    assert "tillfälligt" in candidate["failure_reason"]


def _stick(admin, analysis_id, status, minutes_ago):
    """Simulerar ett CV som fastnat: en körning som dog innan CV:t blev klart."""
    from datetime import UTC, datetime, timedelta

    last_progress_at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    admin.table("candidates").update(
        {"status": status, "last_progress_at": last_progress_at.isoformat()}
    ).eq("analysis_id", analysis_id).execute()


def test_cv_stuck_in_progress_is_picked_up_again_by_run(
    client, make_user, anthropic_fake, admin
):
    user = make_user()
    analysis = _analysis(client, user, [("a.pdf", cv("Utvecklare.\nPOÄNG 70"))])
    _stick(admin, analysis["id"], "processing", minutes_ago=60)
    assert _get(client, user, analysis["id"])["state"] == "running"

    assert _run(client, user, analysis["id"]).status_code == 202

    candidate = _get(client, user, analysis["id"])["candidates"][0]
    assert candidate["status"] == "done"
    assert candidate["assessment"]["score"] == 70


def test_cv_that_was_just_started_is_not_run_twice(
    client, make_user, anthropic_fake, admin
):
    user = make_user()
    analysis = _analysis(client, user, [("a.pdf", cv("Utvecklare.\nPOÄNG 70"))])
    _stick(admin, analysis["id"], "queued", minutes_ago=1)

    assert _run(client, user, analysis["id"]).status_code == 409
    assert anthropic_fake.calls == []


def test_ai_error_that_is_not_transient_fails_the_cv_with_a_clear_reason(
    client, make_user, anthropic_fake
):
    import anthropic

    _flaky(anthropic_fake, "assess", _status_error(anthropic.BadRequestError, 400), 99)
    user = make_user()
    analysis = _analysis(client, user, [("a.pdf", cv("Utvecklare.\nPOÄNG 66"))])

    _run(client, user, analysis["id"])

    candidate = _get(client, user, analysis["id"])["candidates"][0]
    assert candidate["status"] == "failed"
    assert candidate["assessment"] is None
    assert "AI-tjänsten" in candidate["failure_reason"]
    assert "Oväntat" not in candidate["failure_reason"]


def test_empty_assessment_answer_fails_the_cv_instead_of_scoring_it_zero(
    client, make_user, anthropic_fake
):
    from types import SimpleNamespace

    def empty(**kwargs):
        return SimpleNamespace(content=[], stop_reason="refusal")

    anthropic_fake.assess = empty
    user = make_user()
    analysis = _analysis(client, user, [("a.pdf", cv("Utvecklare.\nPOÄNG 66"))])

    _run(client, user, analysis["id"])

    candidate = _get(client, user, analysis["id"])["candidates"][0]
    assert candidate["status"] == "failed"
    assert candidate["assessment"] is None
    assert "tolkas" in candidate["failure_reason"]


def _usage_logs(admin, user):
    return (
        admin.table("usage_logs").select("*").eq("customer_id", user.id).execute().data
    )


def _candidate_count(admin, analysis_id):
    return len(
        admin.table("candidates")
        .select("id")
        .eq("analysis_id", analysis_id)
        .execute()
        .data
    )


def test_delete_now_in_the_middle_of_a_run_succeeds_and_nothing_is_recreated(
    client, make_user, anthropic_fake, admin
):
    _configure(client, max_parallel_cvs=1)
    user = make_user()
    analysis = _analysis(client, user, [("a.pdf", cv("Utvecklare.\nPOÄNG 80"))])
    paths = original_paths(admin, analysis["id"])
    statuses = []

    def delete_now(_text):
        res = client.delete(f"/analyses/{analysis['id']}", headers=user.auth)
        statuses.append(res.status_code)

    anthropic_fake.on_assess = delete_now

    run = _run(client, user, analysis["id"])

    assert statuses == [204]
    assert run.status_code == 202
    _assert_analysis_gone(client, admin, user, analysis["id"], paths)


def test_purge_job_deleting_an_expired_analysis_mid_run_has_the_same_outcome(
    client, make_user, anthropic_fake, admin
):
    from datetime import UTC, datetime, timedelta

    from equa_backend.retention import run_purge_job

    _configure(client, max_parallel_cvs=1)
    user = make_user()
    analysis = _analysis(client, user, [("a.pdf", cv("Utvecklare.\nPOÄNG 80"))])

    def expire_and_purge(_text):
        admin.table("analysis_batches").update(
            {"expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()}
        ).eq("id", analysis["id"]).execute()
        run_purge_job(admin)

    paths = original_paths(admin, analysis["id"])
    anthropic_fake.on_assess = expire_and_purge

    run = _run(client, user, analysis["id"])

    assert run.status_code == 202
    _assert_analysis_gone(client, admin, user, analysis["id"], paths)


def test_cv_assessed_after_the_analysis_was_deleted_is_not_counted_but_tokens_are_logged(
    client, make_user, anthropic_fake, admin
):
    _configure(client, max_parallel_cvs=1)
    user = make_user()
    analysis = _analysis(client, user, [("a.pdf", cv("Utvecklare.\nPOÄNG 80"))])
    anthropic_fake.on_assess = lambda _t: client.delete(
        f"/analyses/{analysis['id']}", headers=user.auth
    )

    _run(client, user, analysis["id"])

    (log,) = _usage_logs(admin, user)
    assert log["cv_count"] == 0
    assert log["input_tokens"] > 0 and log["output_tokens"] > 0


def test_delete_now_during_the_ai_wash_succeeds_and_nothing_is_recreated(
    client, make_user, anthropic_fake, admin
):
    _configure(client, max_parallel_cvs=1)
    user = make_user()
    analysis = _analysis(client, user, [("a.pdf", cv("Utvecklare.\nPOÄNG 80"))])
    paths = original_paths(admin, analysis["id"])
    statuses = []

    def delete_now_then_wash(text):
        res = client.delete(f"/analyses/{analysis['id']}", headers=user.auth)
        statuses.append(res.status_code)
        return text

    anthropic_fake.wash_override = delete_now_then_wash

    run = _run(client, user, analysis["id"])

    assert statuses == [204]
    assert run.status_code == 202
    _assert_analysis_gone(client, admin, user, analysis["id"], paths)
    # Pipelinen kontrollerar inte om analysen finns kvar, så bedömningen skickas
    # ändå. Både tvättens och bedömningens tokens loggas, men CV:t räknas inte
    # mot kvoten (ADR 0007).
    assert len(anthropic_fake.texts_sent("assess")) == 1
    (log,) = _usage_logs(admin, user)
    assert log["cv_count"] == 0
    # Exakt två AI-anrop (tvätt + bedömning) à fakens fasta 100/50 tokens.
    assert log["input_tokens"] == 2 * 100 and log["output_tokens"] == 2 * 50


def _assert_analysis_gone(client, admin, user, analysis_id, paths):
    """Varken analysrad, kandidatrader eller originalfiler finns kvar."""
    assert _candidate_count(admin, analysis_id) == 0
    assert (
        admin.table("analysis_batches")
        .select("id")
        .eq("id", analysis_id)
        .execute()
        .data
        == []
    )
    assert client.get(f"/analyses/{analysis_id}", headers=user.auth).status_code == 404
    assert paths and not any(file_exists(admin, p) for p in paths)
