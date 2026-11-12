## Summary
<!-- Briefly describe what this pull request changes and why. -->

## Checklist
- [ ] Follows Zero Data Fabrication rules (missing values remain `None` / `UNAVAILABLE`, never `$0.00`).
- [ ] Strictly read-only trace collection with no prompts, source code, thinking prose, keys, or network calls.
- [ ] Added or updated offline unit tests under `tests/` using isolated temporary directories.
- [ ] `python -m unittest discover -s tests -v` passes with zero failures.
- [ ] Updated relevant documentation (`README.md`, `docs/`, `CHANGELOG.md`).

