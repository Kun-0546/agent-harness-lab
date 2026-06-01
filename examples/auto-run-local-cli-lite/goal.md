# Goal — the runtime handles each case deterministically and leaves evidence

This tiny workspace exists to demonstrate the v1 **Auto Run** pipeline end to end
(dispatch → evidence → evaluation → report). The "agent" is a deterministic echo,
so there is nothing to discover here — the point is to show what AHL produces when
it drives a `local_cli` runtime over a set of cases. No network, no external APIs.
