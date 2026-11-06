# AURA AI Development Status

## Principles

1. Implement in small, verifiable milestones.
2. Keep the GUI responsive; network and file-heavy work belongs in workers.
3. Prefer deterministic Python tools for routine file operations.
4. Keep Ollama prompts and context sizes modest for CPU-only computers.
5. Never let the AI bypass the safe file-change approval workflow.
6. Add tests alongside each feature.

## Milestones

- [x] Repository and project foundation
- [x] Initial PySide6 desktop shell
- [x] Ollama chat worker and connectivity feedback
- [x] SQLite conversation persistence
- [ ] Model and application settings UI
- [ ] Workspace selector and safe read-only file browser
- [ ] File search, metadata, and bounded text reading
- [ ] Safe change proposals, previews, approval, backups, and trash
- [ ] Coding assistant workflows
- [ ] System monitor
- [ ] Document intelligence
- [ ] Full integration, tests, packaging, and release

## Current limitations

The initial chat milestone is intentionally small. It does not yet edit files, run commands, or expose destructive tools to the model. Those capabilities must be implemented behind explicit user approval and tested before being enabled.
