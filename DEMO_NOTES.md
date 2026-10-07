# Demo notes (not for the final product)

- The team scenario (index page section 04b, `data/scenarios/demo_roster.csv`,
  `src/demo_roster.py`, `results/demo_scenario_results.csv`) uses illustrative team
  profiles written for the panel presentation. They are not a validated model.
- Team source labels in the roster (for example "SoSafe 2021", "4C Group", "UW Study")
  are the author's pointers and must be checked against the original sources before anyone
  cites them.
- The scenario run is separate from the headline results; it does not change them.
- The email preview (page `showcase/emails.html`) and the quiz (`showcase/quiz.html`) are
  demonstrations, not finished products.
- The live scorer (`showcase/live.html`, `showcase/live_examples.json`,
  `scripts/build_live_examples.py`) uses a THIRD population (the generic 30-agent
  copula sample in `server/scorer.py`, via `build_correlated_agents`), not the
  six-department scenario behind the headline numbers. Its scores are a relative,
  within-model susceptibility index, explicitly labelled as such on the page itself.
- Before a real study: ethics approval, consent wording, and removal of real personal data
  from the legitimate emails are still open.
- See `PANEL_QA.md` for a Q&A walkthrough of every design choice (agent instantiation,
  fatigue formulas, decision loop, corpus fixes), with file:line references, written
  for panel prep, not for the panel to read directly.
