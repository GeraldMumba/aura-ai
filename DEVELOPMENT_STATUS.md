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
- [x] Workspace selector and safe read-only file browser
- [x] File search, metadata, and bounded text reading
- [x] Safe change proposals, previews, approval, backups, and trash
- [x] Project metadata scanner and language/framework overview
- [ ] Searchable project index and symbol-aware retrieval
- [ ] Connect project context to chat and coding workflows
- [ ] Safe multi-file edit proposals and diffs
- [ ] Controlled test/debug workflow
- [ ] Model and application settings UI
- [ ] Document intelligence
- [ ] Full integration, tests, packaging, and release

## Current project-understanding milestone

AURA can now produce a deterministic, metadata-only project overview. It excludes hidden folders, virtual environments, common build/cache directories, symbolic links, and sensitive credential files. It does not send project files to Ollama. Searchable content indexing and bounded context retrieval are the next steps.

## Current limitations

Project analysis currently identifies common languages and framework manifests; it does not yet build a symbol graph or infer all dependencies. The scan is bounded to 10,000 files by default.
