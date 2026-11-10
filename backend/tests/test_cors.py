def _preflight(client, origin):
    return client.options(
        "/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )


def test_frontend_origin_is_allowed_to_call_the_api(client):
    res = _preflight(client, "http://localhost:3000")

    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_unknown_origin_is_not_allowed(client):
    res = _preflight(client, "https://evil.example")

    assert "access-control-allow-origin" not in res.headers
