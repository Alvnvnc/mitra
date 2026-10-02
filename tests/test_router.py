"""Unit tests for the model router's pure logic (no network calls)."""

from mitra.models.router import CallRecord, RouterStats, estimate_cost_usd


def test_estimate_cost_ultra_full_million():
    # 1M input + 1M output on Ultra = $1 + $3
    assert estimate_cost_usd("nvidia/Nemotron-3-Ultra-550b-a55b", 1_000_000, 1_000_000) == 4.0


def test_estimate_cost_nano_small_call():
    cost = estimate_cost_usd("nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", 10_000, 2_000)
    assert cost == (10_000 * 0.06 + 2_000 * 0.24) / 1_000_000


def test_estimate_cost_unknown_model_is_zero():
    assert estimate_cost_usd("some/unknown-model", 10_000, 10_000) == 0.0


def test_router_stats_summary_aggregates_by_purpose():
    stats = RouterStats()
    stats.add(CallRecord("m1", "chat", 1.0, 100, 50, 0.001))
    stats.add(CallRecord("m1", "chat", 2.0, 100, 50, 0.001))
    stats.add(CallRecord("m2", "reasoning", 5.0, 200, 100, 0.002))

    summary = stats.summary()
    assert summary["calls"] == 3
    assert abs(summary["total_cost_usd"] - 0.004) < 1e-12
    assert summary["by_purpose"]["chat"]["calls"] == 2
    assert summary["by_purpose"]["chat"]["latency_s"] == 3.0
    assert summary["by_purpose"]["reasoning"]["calls"] == 1