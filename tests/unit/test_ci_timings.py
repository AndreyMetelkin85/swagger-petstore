"""Timing reports must separate cache export, execution and queue durations."""

from urllib.request import Request

from docker.ci_timings import GitHubRedirect, cache_export_seconds, elapsed


def test_registry_export_duration_is_not_total_build_or_another_step():
    log = "#8 exporting layers\n#8 DONE 120.5s\n#18 exporting cache to registry\n#19 DONE 60s\n#18 DONE 2.5s"
    assert cache_export_seconds(log) == 2.5
    assert cache_export_seconds("#1 exporting cache to registry") is None


def test_missing_and_skipped_timestamps_do_not_invent_durations():
    assert elapsed(None, "2026-10-08T16:00:00Z") is None
    assert elapsed("2026-10-08T16:00:01Z", "2026-10-08T16:00:00Z") == 0
    assert elapsed("2026-10-08T16:00:00Z", "2026-10-08T16:01:48.44Z") == 108.44


def test_signed_log_redirect_does_not_forward_github_authorization():
    request = Request("https://api.github.com/logs", headers={"Authorization": "Bearer test-token"})
    redirect = GitHubRedirect().redirect_request(request, None, 302, "Found", {}, "https://blob.example/log")
    assert redirect.get_header("Authorization") is None
    same_host = GitHubRedirect().redirect_request(
        request, None, 302, "Found", {}, "https://api.github.com/new"
    )
    assert same_host.get_header("Authorization") == "Bearer test-token"
