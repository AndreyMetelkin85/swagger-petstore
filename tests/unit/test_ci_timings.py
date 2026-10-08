"""Timing reports must separate cache export, execution and queue durations."""

from docker.ci_timings import cache_export_seconds, elapsed


def test_registry_export_duration_is_not_total_build_or_another_step():
    log = "#8 exporting layers\n#8 DONE 120.5s\n#18 exporting cache to registry\n#19 DONE 60s\n#18 DONE 2.5s"
    assert cache_export_seconds(log) == 2.5
    assert cache_export_seconds("#1 exporting cache to registry") is None


def test_missing_and_skipped_timestamps_do_not_invent_durations():
    assert elapsed(None, "2026-10-08T16:00:00Z") is None
    assert elapsed("2026-10-08T16:00:01Z", "2026-10-08T16:00:00Z") == 0
    assert elapsed("2026-10-08T16:00:00Z", "2026-10-08T16:01:48.44Z") == 108.44
