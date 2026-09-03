from app.agents.code_scout.routing import repos_for_stage


def test_all_four_routing_stages_resolve():
    for stage in ("consultation", "pharmacy_checkout", "payments", "re_engagement"):
        repos = repos_for_stage(stage)
        assert len(repos) >= 1
        for r in repos:
            assert "service" in r and "repo" in r


def test_pharmacy_checkout_routes_to_two_repos():
    repos = repos_for_stage("pharmacy_checkout")
    assert [r["repo"] for r in repos] == ["timor/oms", "timor/fulfilment"]


def test_consultation_routes_to_bintan():
    assert repos_for_stage("consultation") == [
        {"service": "consultation", "repo": "bintan/consultation"}
    ]
