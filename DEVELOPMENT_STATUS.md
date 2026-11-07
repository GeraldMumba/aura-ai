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
- [x] Explicit workspace index refresh from the desktop UI
- [x] Relevant indexed excerpts attached to chat for the selected workspace
- [ ] Extend selected workspace context to code-generation and debugging workflows
- [x] Initial static Python symbol, import, and call-candidate analysis tool
- [ ] Persisted symbol graph and more accurate cross-module relationship resolution
- [ ] Safe multi-file edit proposals and diffs
- [ ] Controlled test/debug workflow
- [ ] Model and application settings UI
- [ ] Document intelligence
- [ ] Full integration, tests, packaging, and release

## Current project-understanding milestone

AURA can build and refresh a local SQLite index of supported source/text files in a selected workspace. Search returns compact line-numbered excerpts from the cached index. Hidden/generated and sensitive files are excluded, files larger than 512 KB are skipped, and likely secret assignments are redacted before content is stored. The index is workspace-scoped and can be rebuilt to remove stale/deleted files. OAuth token files (`token.json` and files inside `tokens/`, `secrets/`, or `.ssh/`) are excluded from indexing and direct text reading.

The index is exposed to AURA through read-only tool calls. It does not execute commands or modify project files.

AURA also has an initial Python AST analyzer. It extracts module-level and scoped calls, classes, functions, imports, source line ranges, and bounded docstring summaries without importing or executing project code. It is exposed as a read-only tool and is intended to guide follow-up source inspection. Call resolution is deliberately described as approximate name-based candidates; dynamic dispatch, aliases, decorators, and generated code are not fully resolved. Analysis output is capped for small local models, and sensitive files are excluded using the same content-safety rules as the project index.

## Security hardening update

Known OAuth token files and files inside credential directories are now excluded from project indexing, direct text reading, and source-content search. Refresh the selected workspace index after updating so previously cached token-file entries are removed.

## Current limitations

Search is literal rather than semantic. The index must be explicitly built or refreshed after project files change. Python symbol analysis is an initial static aid, not a complete call graph, and currently does not analyze non-Python languages. More accurate import-aware resolution, persisted symbol metadata, and relationship-guided retrieval remain future milestones.
