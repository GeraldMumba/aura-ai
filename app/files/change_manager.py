from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.database.db import (
    delete_pending_change, get_change_history, get_pending_changes,
    initialize_database, initialize_change_tables, record_change_history, save_pending_change,
)


class ChangeManager:
    """Workspace-confined file changes requiring preview and explicit approval."""

    MAX_TEXT_SIZE = 512 * 1024
    RESERVED = {".aura_trash", ".aura_backups"}

    def __init__(self, workspace_root: str | Path):
        requested = Path(workspace_root).expanduser()
        if requested.is_symlink():
            raise ValueError("Workspace cannot be a symbolic link.")
        self.workspace_root = requested.resolve(strict=True)
        if not self.workspace_root.is_dir():
            raise ValueError("Workspace must be a directory.")
        self.pending: dict[str, dict[str, Any]] = {}
        initialize_database()
        initialize_change_tables()
        self._load_pending()

    def _path(self, value: str | Path) -> Path:
        requested = Path(value).expanduser()
        if not requested.is_absolute():
            requested = self.workspace_root / requested
        current = Path(self.workspace_root.anchor)
        try:
            relative = requested.relative_to(self.workspace_root)
        except ValueError as exc:
            raise ValueError("Path is outside the selected workspace.") from exc
        if not relative.parts:
            raise ValueError("The workspace root itself cannot be changed.")
        for part in relative.parts:
            if part in self.RESERVED:
                raise ValueError("AURA recovery storage is protected.")
            current = current / part
            if current.is_symlink():
                raise ValueError("Symbolic-link paths are not permitted.")
        resolved = requested.resolve(strict=False)
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError as exc:
            raise ValueError("Resolved path is outside the workspace.") from exc
        return resolved

    def _snapshot(self, path: Path) -> str | None:
        if not path.exists():
            return None
        if path.is_symlink():
            raise ValueError("Symbolic links are not permitted.")
        digest = hashlib.sha256()
        if path.is_file():
            if path.stat().st_size > self.MAX_TEXT_SIZE:
                raise ValueError("File exceeds the 512 KB change-management limit.")
            digest.update(path.read_bytes())
        elif path.is_dir():
            for item in sorted(path.rglob("*")):
                if item.is_symlink():
                    raise ValueError("Directories containing symbolic links are not supported.")
                if item.is_file():
                    digest.update(str(item.relative_to(path)).encode())
                    digest.update(hashlib.sha256(item.read_bytes()).digest())
        else:
            raise ValueError("Unsupported filesystem object.")
        return digest.hexdigest()

    def _store(self, action: str, details: dict, preview: dict) -> dict:
        proposal = {
            "id": uuid.uuid4().hex[:12],
            "action": action,
            "details": details,
            "preview": preview,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        save_pending_change(self.workspace_root, proposal)
        self.pending[proposal["id"]] = proposal
        return {
            "success": True, "status": "awaiting_approval",
            "id": proposal["id"], "action": action, "preview": preview,
        }

    def _load_pending(self):
        for proposal in get_pending_changes(self.workspace_root):
            try:
                action = proposal.get("action")
                if action not in {"create_file", "edit_file", "create_folder", "delete", "restore_trash"}:
                    continue
                details = proposal.get("details", {})
                target = self._path(details["path"])
                expected = details.get("expected")
                if action == "restore_trash":
                    trash_path = self._trash_item_path(details["trash_id"])
                    valid = self._snapshot(target) == expected and self._snapshot(trash_path) == details.get("trash_expected")
                else:
                    valid = self._snapshot(target) == expected
                if valid:
                    self.pending[proposal["id"]] = proposal
            except (KeyError, TypeError, ValueError, OSError):
                continue

    def propose_create_file(self, path: str, content: str = "") -> dict:
        target = self._path(path)
        if target.exists():
            raise FileExistsError("Destination already exists; AURA will not overwrite it.")
        if not target.parent.is_dir():
            raise FileNotFoundError("Parent directory does not exist.")
        if not isinstance(content, str) or len(content.encode("utf-8")) > self.MAX_TEXT_SIZE:
            raise ValueError("Content must be text no larger than 512 KB.")
        diff = difflib.unified_diff([], content.splitlines(), fromfile="/dev/null",
                                    tofile=str(target), lineterm="")
        return self._store("create_file", {"path": str(target), "content": content, "expected": None},
                           {"target": str(target), "diff": "\n".join(diff)})

    def propose_edit_file(self, path: str, new_content: str) -> dict:
        target = self._path(path)
        if not target.is_file():
            raise ValueError("Only existing regular files can be edited.")
        if target.stat().st_size > self.MAX_TEXT_SIZE:
            raise ValueError("Existing file exceeds 512 KB.")
        if not isinstance(new_content, str) or len(new_content.encode("utf-8")) > self.MAX_TEXT_SIZE:
            raise ValueError("New content must be text no larger than 512 KB.")
        try:
            old = target.read_text(encoding="utf-8")
        except (UnicodeError, OSError) as exc:
            raise ValueError(f"File cannot be safely edited as UTF-8 text: {exc}") from exc
        if old == new_content:
            raise ValueError("There are no changes to apply.")
        diff = difflib.unified_diff(old.splitlines(), new_content.splitlines(),
                                    fromfile=str(target), tofile=f"{target} (proposed)",
                                    lineterm="")
        return self._store("edit_file", {
            "path": str(target), "content": new_content, "expected": self._snapshot(target),
        }, {"target": str(target), "diff": "\n".join(diff),
            "old_size": len(old), "new_size": len(new_content)})

    def propose_create_folder(self, path: str) -> dict:
        target = self._path(path)
        if target.exists():
            raise FileExistsError("Destination already exists.")
        if not target.parent.is_dir():
            raise FileNotFoundError("Parent directory does not exist.")
        return self._store("create_folder", {"path": str(target), "expected": None},
                           {"target": str(target), "description": "Create directory."})

    def propose_delete(self, path: str) -> dict:
        target = self._path(path)
        if not target.exists():
            raise FileNotFoundError("Target does not exist.")
        if target.is_dir():
            for item in target.rglob("*"):
                if item.is_symlink():
                    raise ValueError("Cannot trash a directory containing symbolic links.")
                if item.is_dir() and item.name in self.RESERVED:
                    raise ValueError("Cannot trash AURA recovery storage.")
        return self._store("delete", {"path": str(target), "expected": self._snapshot(target)},
                           {"target": str(target), "description": "Move into recoverable AURA trash."})

    def approve(self, change_id: str) -> dict:
        proposal = self.pending.get(change_id)
        if proposal is None:
            raise ValueError("Proposal not found or already processed.")
        details = proposal["details"]
        target = self._path(details["path"])
        if self._snapshot(target) != details.get("expected"):
            raise ValueError("File state changed after preview. No operation was applied; create a fresh proposal.")
        action = proposal["action"]
        result = {}
        if action == "create_file":
            if target.exists():
                raise FileExistsError("Destination now exists.")
            self._atomic_write(target, details["content"])
            result = {"path": str(target)}
        elif action == "edit_file":
            if not target.is_file():
                raise ValueError("Target is no longer a regular file.")
            self._backup(target)
            self._atomic_write(target, details["content"])
            result = {"path": str(target), "backup_created": True}
        elif action == "create_folder":
            target.mkdir()
            result = {"path": str(target)}
        elif action == "delete":
            trash_id = uuid.uuid4().hex
            trash_root = self._internal_dir(".aura_trash")
            destination = trash_root / trash_id
            shutil.move(str(target), str(destination))
            metadata = {"id": trash_id, "original_path": str(target), "created_at": datetime.now().isoformat()}
            (destination.parent / f"{trash_id}.json").write_text(json.dumps(metadata), encoding="utf-8")
            result = {"trash_id": trash_id, "original_path": str(target)}
        elif action == "restore_trash":
            trash_path = self._trash_item_path(details["trash_id"])
            if target.exists() or self._snapshot(trash_path) != details.get("trash_expected"):
                raise ValueError("The restore destination or trash item changed after preview.")
            shutil.move(str(trash_path), str(target))
            metadata_path = trash_path.parent / f"{details['trash_id']}.json"
            if metadata_path.exists():
                metadata_path.unlink()
            result = {"path": str(target), "restored_from_trash": details["trash_id"]}
        delete_pending_change(change_id, self.workspace_root)
        self.pending.pop(change_id, None)
        record_change_history(self.workspace_root, change_id, action, "approved",
                              {"preview": proposal["preview"], "result": result})
        return {"success": True, "status": "approved", "result": result}

    def _atomic_write(self, target: Path, content: str):
        temporary = target.with_name(f".{target.name}.aura-{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _internal_dir(self, name: str) -> Path:
        if name not in self.RESERVED:
            raise ValueError("Invalid recovery directory.")
        directory = self.workspace_root / name
        if directory.is_symlink():
            raise ValueError("Recovery directory cannot be a symbolic link.")
        directory.mkdir(exist_ok=True)
        return directory

    def _backup(self, target: Path) -> str:
        backup_id = uuid.uuid4().hex
        folder = self._internal_dir(".aura_backups") / backup_id
        folder.mkdir()
        shutil.copy2(target, folder / "content")
        (folder / "metadata.json").write_text(
            json.dumps({"id": backup_id, "original_path": str(target)}), encoding="utf-8"
        )
        return backup_id

    def cancel(self, change_id: str) -> dict:
        proposal = self.pending.pop(change_id, None)
        if proposal is None:
            raise ValueError("Proposal not found or already processed.")
        delete_pending_change(change_id, self.workspace_root)
        record_change_history(self.workspace_root, change_id, proposal["action"], "cancelled",
                              {"preview": proposal["preview"]})
        return {"success": True, "status": "cancelled", "id": change_id}

    def list_history(self, limit: int = 50) -> list[dict]:
        return get_change_history(self.workspace_root, limit=limit)


    def _trash_item_path(self, trash_id: str) -> Path:
        if not isinstance(trash_id, str) or len(trash_id) != 32 or any(
            char not in "0123456789abcdef" for char in trash_id
        ):
            raise ValueError("Invalid trash identifier.")
        root = self._internal_dir(".aura_trash")
        item = root / trash_id
        if item.is_symlink() or not item.exists():
            raise FileNotFoundError("Trash item was not found.")
        return item

    def list_trash(self) -> list[dict]:
        root = self.workspace_root / ".aura_trash"
        if root.is_symlink() or not root.exists():
            return []
        items = []
        for metadata_path in sorted(root.glob("*.json")):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                trash_id = metadata.get("id", "")
                item = self._trash_item_path(trash_id)
                items.append({
                    "id": trash_id,
                    "original_path": metadata["original_path"],
                    "created_at": metadata.get("created_at", ""),
                    "is_directory": item.is_dir(),
                })
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
        return items

    def propose_restore_trash(self, trash_id: str) -> dict:
        trash_path = self._trash_item_path(trash_id)
        metadata_path = trash_path.parent / f"{trash_id}.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            target = self._path(metadata["original_path"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Trash metadata is invalid: {exc}") from exc
        if target.exists():
            raise FileExistsError("The original location is occupied. Move or rename that item first.")
        if not target.parent.is_dir():
            raise FileNotFoundError("The original parent folder no longer exists.")
        return self._store(
            "restore_trash",
            {"path": str(target), "expected": None, "trash_id": trash_id,
             "trash_expected": self._snapshot(trash_path)},
            {"target": str(target), "description": f"Restore item {trash_id} from AURA trash."},
        )

    def list_backups(self) -> list[dict]:
        root = self.workspace_root / ".aura_backups"
        if root.is_symlink() or not root.exists():
            return []
        items = []
        for metadata_path in sorted(root.glob("*/metadata.json")):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                content = metadata_path.parent / "content"
                if content.is_file() and not content.is_symlink():
                    items.append({
                        "id": metadata["id"],
                        "original_path": metadata["original_path"],
                        "created_at": metadata_path.stat().st_mtime,
                    })
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
        return items

    def propose_restore_backup(self, backup_id: str) -> dict:
        if not isinstance(backup_id, str) or len(backup_id) != 32 or any(
            char not in "0123456789abcdef" for char in backup_id
        ):
            raise ValueError("Invalid backup identifier.")
        root = self._internal_dir(".aura_backups")
        folder = root / backup_id
        metadata_path = folder / "metadata.json"
        content_path = folder / "content"
        if folder.is_symlink() or content_path.is_symlink() or metadata_path.is_symlink():
            raise ValueError("Backup symbolic links are not permitted.")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            target = self._path(metadata["original_path"])
            content = content_path.read_text(encoding="utf-8")
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Backup cannot be restored: {exc}") from exc
        if not target.is_file():
            raise FileNotFoundError("The original file no longer exists. Backup restoration only replaces existing files.")
        return self.propose_edit_file(target, content)
