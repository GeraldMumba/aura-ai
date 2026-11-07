from app.files.change_manager import ChangeManager


def test_trash_restore_requires_approval_and_restores_original_path(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("keep this", encoding="utf-8")
    manager = ChangeManager(tmp_path)

    deletion = manager.propose_delete(target)
    deleted = manager.approve(deletion["id"])
    assert not target.exists()

    trash_id = deleted["result"]["trash_id"]
    assert len(manager.list_trash()) == 1

    restoration = manager.propose_restore_trash(trash_id)
    assert restoration["status"] == "awaiting_approval"
    assert not target.exists()

    result = manager.approve(restoration["id"])
    assert result["status"] == "approved"
    assert target.read_text(encoding="utf-8") == "keep this"
    assert manager.list_trash() == []


def test_backup_restore_is_a_proposed_edit_and_preserves_current_version(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("version one\n", encoding="utf-8")
    manager = ChangeManager(tmp_path)

    edit = manager.propose_edit_file(target, "version two\n")
    manager.approve(edit["id"])
    assert target.read_text(encoding="utf-8") == "version two\n"

    backups = manager.list_backups()
    assert len(backups) == 1
    restore = manager.propose_restore_backup(backups[0]["id"])

    assert restore["action"] == "edit_file"
    assert target.read_text(encoding="utf-8") == "version two\n"
    manager.approve(restore["id"])

    assert target.read_text(encoding="utf-8") == "version one\n"
    assert len(manager.list_backups()) == 2


def test_pending_proposal_survives_manager_restart(tmp_path):
    target = tmp_path / "draft.txt"
    target.write_text("before", encoding="utf-8")

    first = ChangeManager(tmp_path)
    proposal = first.propose_edit_file(target, "after")

    second = ChangeManager(tmp_path)
    assert proposal["id"] in second.pending
    second.approve(proposal["id"])
    assert target.read_text(encoding="utf-8") == "after"
