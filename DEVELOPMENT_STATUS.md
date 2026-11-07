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
- [ ] Searchable project index with cached results and refresh controls
- [ ] Connect selected workspace context to chat and coding workflows
- [ ] Symbol-aware retrieval and file relationship analysis
- [ ] Safe multi-file edit proposals and diffs
- [ ] Controlled test/debug workflow
- [ ] Model and application settings UI
- [ ] Document intelligence
- [ ] Full integration, tests, packaging, and release

## Current project-understanding milestone

AURA can scan project metadata and search supported source/text files for exact text matches. Content search returns a small number of line-numbered excerpts, skips hidden/generated and sensitive files, ignores files over 512 KB, and redacts likely secret assignments. It is a bounded read-only tool available to the AI; it does not write files or execute commands.

## Current limitations

Content search is literal, not semantic. It does not yet build a persistent cache, understand language symbols, or automatically attach project context to every chat. Those are separate next steps.
