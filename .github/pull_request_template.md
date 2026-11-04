## Summary

<!-- What changes and why. One request or one fix per PR (AGENTS.md rule 6). -->

Closes #<!-- issue --> / Implements `docs/requests/<!-- NNN-name -->.md`

## Changes

-

## Checklist

- [ ] No validator weakened, contract loosened or test deleted to make a check pass
- [ ] Nothing written to `data/raw/`
- [ ] Every number in report text goes through `Ledger.num`, `Ledger.rank` or `Ledger.text`
- [ ] Reports use only games before `as_of`
- [ ] New metric: SQL + docstring definition + test + report section (`.factory/skills/new-metric/SKILL.md`)
- [ ] Docs (`AGENTS.md`, `README.md`) updated if commands or behavior changed

## Testing

<!-- Paste the full `make check` output. It must end with "make check: all green". -->

```
$ make check

```
