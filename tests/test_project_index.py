from pathlib import Path

from app.files.project_index import analyze_project, format_project_report


def test_analyze_project_counts_languages_and_detects_frameworks(tmp_path: Path):
    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("django\nrequests\n", encoding="utf-8")
    (tmp_path / "web.js").write_text("console.log('ok')", encoding="utf-8")
    (tmp_path / "manage.py").write_text("# django", encoding="utf-8")

    report = analyze_project(tmp_path)

    assert report["files_scanned"] == 4
    assert report["languages"]["Python"] == 2
    assert report["languages"]["JavaScript"] == 1
    assert "Django" in report["frameworks"]
    assert report["total_size_bytes"] > 0


def test_analyze_project_excludes_venv_hidden_and_sensitive_files(tmp_path: Path):
    (tmp_path / "app.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=do-not-read", encoding="utf-8")
    (tmp_path / "private.pem").write_text("private", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("ignored", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "python.py").write_text("ignored", encoding="utf-8")

    report = analyze_project(tmp_path)

    assert report["files_scanned"] == 1
    assert report["largest_files"][0]["path"] == "app.py"


def test_analyze_project_obeys_file_limit(tmp_path: Path):
    for index in range(5):
        (tmp_path / f"file_{index}.py").write_text("pass", encoding="utf-8")

    report = analyze_project(tmp_path, max_files=2)

    assert report["files_scanned"] == 2
    assert report["truncated"] is True


def test_project_report_is_readable_and_metadata_only(tmp_path: Path):
    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")
    report = format_project_report(analyze_project(tmp_path))

    assert "LANGUAGES:" in report
    assert "Python: 1 files" in report
    assert "metadata-only" in report


def test_analyze_project_rejects_symlink_workspace(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)

    try:
        analyze_project(link)
    except ValueError as exc:
        assert "Symbolic-link" in str(exc)
    else:
        raise AssertionError("Expected symlink workspace to be rejected")
