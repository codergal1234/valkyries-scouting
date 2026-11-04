# Request 001: Transition offense and defense

**From:** basketball ops (Slack, #scouting)
**Message:** "Can the report show how dangerous they are in transition, and how we've been at
getting back? Atlanta ran us off the floor in Game 3."

## What a scout wants to see

- Share of their points that come in transition, and their league rank.
- Points per transition possession, theirs and ours (how efficient it is).
- The same numbers on defense: transition points allowed.
- One "how to guard them" bullet when it matters (top 4 in transition share).

## Suggested definition (confirm or improve)

A transition shot is a field-goal attempt within 8 seconds of the team gaining possession
via a defensive rebound or an opponent turnover. Use the play-by-play clock. Count free
throws only if they come from a shooting foul in that window.

## Done when

- New section "Transition" in the report, all numbers through the Ledger.
- Definition added to `scout/metrics.py` docstring.
- Test on the fixture.
- `make check` passes.
