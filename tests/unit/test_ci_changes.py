"""Release selection must skip docs while failing closed for executable changes."""

from docker.ci_changes import classify


def test_docs_and_already_published_branch_sync_do_not_rebuild():
    assert not any(classify([]).values())
    assert not any(classify(["README.md", "docs/DEVELOPMENT.md", ".gitignore"]).values())


def test_ui_and_photo_changes_keep_runtime_checks_without_backend_repeat():
    for paths in (["ui/src/catalog.tsx"], ["resources/demo-catalog/manifest.json"]):
        result = classify(paths)
        assert result == {"backend": False, "ui": True, "runtime": True, "build": True}


def test_backend_pipeline_tests_and_unknown_files_require_full_checks():
    for path in (
        "src/petstore/app.py",
        ".github/workflows/python.yml",
        "tests/integration/test_commerce.py",
        "unknown-script",
    ):
        assert all(classify([path]).values())
