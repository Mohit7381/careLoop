from app.agents.analyst.aggregate_tool import AggregateTool


def test_whitelist_rejection(cohort_cuts, journey_cfg):
    tool = AggregateTool(cohort_cuts, journey_cfg["drilldown_dimensions"])
    out = tool.aggregate("confirmed", "user_phone_number")
    assert "error" in out and "not whitelisted" in out["error"]


def test_rx_cut_gives_the_real_multiplier(cohort_cuts, journey_cfg):
    tool = AggregateTool(cohort_cuts, journey_cfg["drilldown_dimensions"])
    out = tool.aggregate("confirmed", "consultation_required")
    rates = {r["segment"]: r["rate"] for r in out["rows"]}
    assert abs(rates["rx_gated"] - 0.300) < 0.001
    assert abs(rates["non_rx"] - 0.390) < 0.001  # the -9pp finding


def test_distribution_only_cut_has_no_rates(cohort_cuts, journey_cfg):
    tool = AggregateTool(cohort_cuts, journey_cfg["drilldown_dimensions"])
    out = tool.aggregate("confirmed", "pd_category")
    assert out["distribution_only"] is True
    assert all("rate" not in r for r in out["rows"] if not r.get("suppressed"))


def test_k_floor_suppresses_small_segments(cohort_cuts, journey_cfg):
    tool = AggregateTool(cohort_cuts, journey_cfg["drilldown_dimensions"])
    out = tool.aggregate("confirmed", "pd_category")
    small = [r for r in out["rows"] if r.get("segment") == "small_segment_example"]
    assert small and small[0]["suppressed"] is True


def test_no_data_dimension_is_distinct_from_not_whitelisted(cohort_cuts, journey_cfg):
    """Whitelisted-but-dataless must read as no_data, not as a rejection.

    Uses an explicit whitelist rather than the journey config: every dimension
    the config lists is now required to have cohort data (the config used to
    advertise four it could not answer), so there is deliberately no dataless
    dimension left in it to point at.
    """
    whitelist = [*journey_cfg["drilldown_dimensions"], "dimension_with_no_fixture"]
    tool = AggregateTool(cohort_cuts, whitelist)
    out = tool.aggregate("confirmed", "dimension_with_no_fixture")
    assert out.get("no_data") is True
    assert "dimension_with_no_fixture" not in out["dimensions_with_data"]
    assert "consultation_required" in out["dimensions_with_data"]


def test_every_whitelisted_dimension_has_data(cohort_cuts, journey_cfg):
    """The config is a promise the fixture has to keep — a dimension the LLM is
    told it may query, that then answers no_data, burns a drill-down turn."""
    dataless = [d for d in journey_cfg["drilldown_dimensions"] if d not in cohort_cuts]
    assert not dataless, f"whitelisted but no cohort data: {dataless}"
