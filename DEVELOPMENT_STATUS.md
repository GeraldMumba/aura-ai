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
- [x] Bounded source-content search exposed as a read-only AI tool
- [x] Persistent local project index with refresh and cached source search
- [ ] Connect selected workspace context to chat and coding workflows
- [ ] Symbol-aware retrieval and file relationship analysis
- [ ] Safe multi-file edit proposals and diffs
- [ ] Controlled test/debug workflow
- [ ] Model and application settings UI
- [ ] Document intelligence
- [ ] Full integration, tests, packaging, and release

## Current project-understanding milestone

AURA can build and refresh a local SQLite index of supported source/text files in a selected workspace. Search returns compact line-numbered excerpts from the cached index. Hidden/generated and sensitive files are excluded, files larger than 512 KB are skipped, and likely secret assignments are redacted before content is stored. The index is workspace-scoped and can be rebuilt to remove stale/deleted files.

The index is exposed to AURA through read-only tool calls. It does not execute commands or modify project files.

## Current limitations

Search is literal rather than semantic. The index must be explicitly built or refreshed after project files change. Automatic context attachment, symbol-aware retrieval, and relationship analysis remain future milestones.
