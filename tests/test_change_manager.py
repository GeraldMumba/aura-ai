import pytest

from app.files.change_manager import ChangeManager


def test_edit_requires_approval_and_creates_backup(tmp_path):
    target = tmp_path / "hello.py"
    target.write_text("print('old')\n", encoding="utf-8")
    manager = ChangeManager(tmp_path)
    proposal = manager.propose_edit_file(target, "print('new')\n")
    assert target.read_text(encoding="utf-8") == "print('old')\n"
    assert "print('new')" in proposal["preview"]["diff"]
    result = manager.approve(proposal["id"])
    assert result["success"] is True
    assert target.read_text(encoding="utf-8") == "print('new')\n"
    assert list((tmp_path / ".aura_backups").glob("*/content"))


def test_rejects_path_outside_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manager = ChangeManager(workspace)
    with pytest.raises(ValueError, match="outside"):
        manager.propose_create_file(tmp_path / "outside.txt", "no")


def test_snapshot_change_invalidates_proposal(tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("original", encoding="utf-8")
    manager = ChangeManager(tmp_path)
    proposal = manager.propose_edit_file(target, "proposed")
    target.write_text("changed externally", encoding="utf-8")
    with pytest.raises(ValueError, match="changed after preview"):
        manager.approve(proposal["id"])
    assert target.read_text(encoding="utf-8") == "changed externally"


def test_cancel_removes_pending_proposal(tmp_path):
    manager = ChangeManager(tmp_path)
    proposal = manager.propose_create_file("new.txt", "hello")
    result = manager.cancel(proposal["id"])
    assert result["status"] == "cancelled"
    assert not (tmp_path / "new.txt").exists()
    assert manager.list_history()[0]["status"] == "cancelled"


def test_delete_moves_file_to_recoverable_trash(tmp_path):
    target = tmp_path / "remove-me.txt"
    target.write_text("recover me", encoding="utf-8")
    manager = ChangeManager(tmp_path)
    proposal = manager.propose_delete(target)
    assert target.exists()
    result = manager.approve(proposal["id"])
    assert not target.exists()
    trash_id = result["result"]["trash_id"]
    assert (tmp_path / ".aura_trash" / trash_id).read_text(encoding="utf-8") == "recover me"
