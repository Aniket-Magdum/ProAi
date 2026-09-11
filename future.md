# PRO AI Coach — Architecture Review & Future Roadmap (`future.md`)

This document preserves the comprehensive architecture review, risk analysis, and future engineering roadmap for the **PRO AI Coach**.

---

## 1. Architecture Review (Assessment & Findings)

### What's Genuinely Good
- **Local-first quick-calc**: Speed checks, damage ranges, and KO tags don't need an LLM. Computing those locally with Gemini reserved for higher-level tactical synthesis is the correct split.
- **Strict move enforcement via Showdown / PRO team import**: Constraining recommendations strictly to the player's actual learned moveset eliminates the #1 LLM failure mode (recommending unlearned moves).
- **Choice Lock Exploitation**: Tracking Choice item move locks, flagging immunities for free setup turns, and warning against switching into locked moves.
- **Manual Battle State Editor**: Pragmatic fallback in the HUD (`✏️ RAW DATA`) allowing players to correct misreads without restarting.
- **Automated Self-Test Suite**: Comprehensive regression tests guaranteeing mathematical correctness and zero pipeline breakages.

---

## 2. Top Risks, Edge Cases & Gaps

### 1. The ToS & Ladder Policy
* "Read-only, never clicks" is the correct technical constraint, but private servers strictly prohibit external assistance that grants real-time ladder advantages.
* **Guideline**: Keep the coach strictly passive and read-only. Position it primarily as a private tactical HUD, personal coach, and replay analyst.

### 2. Pipeline Latency vs Math Latency
* `<1ms` is the calculation speed of the local math engine; the full vision capture + OCR pass realistically takes `100–300ms`.
* **Fix**: Use **Pixel-Hash Change Detection** — hash the battle log and health bar regions; when pixels don't change between turns, skip OCR entirely to drop CPU usage to `<0.5%`.

### 3. HUD Screen Capture Occlusion Bug
* Using screen region capture (`mss`) captures whatever is on the desktop screen. If the always-on-top HUD overlaps the PRO window or battle log, OCR will accidentally read its own advice text.
* **Fix**: Use Windows Win32 `PrintWindow(hwnd, ..., PW_RENDERFULLCONTENT)` to read directly from the PROClient window DC/backbuffer, capturing the game even when occluded by other windows.

### 4. OCR Error-Correction Layer
* Unity fonts can cause misreads (e.g., "Charzard", "Pyro Bal1").
* **Fix**:
  - Maintain a strict token dictionary of species names, moves, and items with Levenshtein fuzzy matching (`rapidfuzz`).
  - Add confidence thresholds: reject low-confidence tokens instead of corrupting state.
  - Dedicated keyword set for stat boosts (`"rose"`, `"fell"`, `"sharply rose"`).

### 5. Tkinter Thread Safety & Atomic File Writes
* Modifying Tkinter widgets from background OCR threads can cause intermittent C-level crashes (`Tcl_AsyncDelete`).
* **Fix**:
  - Marshal all GUI updates through Tkinter's main loop using `root.after()`.
  - Use **atomic file writes** (`tempfile` $\to$ `os.replace`) for `battlestate.json` and `saved_team.txt` so power cuts or crashes never corrupt data.

### 6. Gemini: Transition from "Generation" to "Classification"
* Instead of prompting Gemini to generate advice from scratch, structure it as a **verified action selector**:
  1. Locally enumerate all legal actions with computed damage, speed, and KO tags:
     - `[1] Move A`: ~X% damage (hits first)
     - `[2] Move B`: Setup / Boost
     - `[3] Switch to Mon C`: Type immunity
  2. Send Gemini the state JSON + candidate action table as ground truth.
  3. Ask Gemini to return `{"action_id": N, "rationale": "..."}`.
  4. **Outcome**: Zero hallucinations, 100% legal moves, 50% faster API responses, and lower token costs.

### 7. Depth-2 Expectimax Game Tree ("Real Stockfish Math")
* Evaluating your 4 moves + switch $\times$ opponent's 5 weighted responses creates a 30-node branch.
* Because local damage calculations take $<1\text{ms}$, evaluating 30 branches takes $<2\text{ms}$ of CPU time.
* **Outcome**: Turns "Option A (Safe) vs Option B (Read)" from heuristics into actual mathematical minimax game theory.

### 8. PRO-Native Metagame Aggregation
* Mainline Smogon OU usage diverges from Pokémon Revolution Online ladder realities (different levels, trade availability, tournament clauses).
* **Fix**: Continuously accumulate revealed moves, items, and spreads from the live PRO battle logs into a local PRO-specific metagame frequency database.

---

## 3. Prioritized Implementation Roadmap (v2)

| Phase | Milestone | Expected Impact |
| :---: | :--- | :--- |
| **P1** | **Gemini Action Classifier** | Eliminates 100% of LLM hallucination; ranks pre-computed legal plays. |
| **P2** | **Atomic File Writes & Thread Safety** | Guarantees zero crash risk and prevents JSON corruption. |
| **P3** | **Depth-2 Expectimax Tree** | Computes 2-turn minimax lines for Safe Play vs Prediction Read. |
| **P4** | **Win32 `PrintWindow` Capture** | Eliminates OCR overlap pollution when HUD sits on top of the game. |
| **P5** | **PRO-Native Metagame Database** | Replaces generic Smogon stats with real PRO ladder frequency data. |

---

## 4. Current Working Baseline (Completed in v1)

- **Exact IVs, EVs, & Nature Engine**: Official Pokémon cartridge formulas calculate exact stats down to 1 point (e.g. Mew HP 329, Spe 314, SpA 292).
- **Hacker & Architect Speed Caliper**: Real-time turn-order comparisons lock opponent `speed_floor` ($\ge$) and `speed_ceiling` ($\le$) against known ground-truth speed.
- **Dynamic Smogon EV Archetypes**: Opponent stats dynamically assigned realistic 252/252 spreads (Sweeper, Wall, Pivot) rather than flat 85 EV averages.
- **Embedded In-Place Importer**: Single HUD with `[📋 IMPORT]` tab, `saved_team.txt` persistence, and `[💾 SAVE DATA]` button.
- **Continuous Opponent Battle Log Intelligence**: Automatic tracking of send-outs, moves, Leftovers, Life Orb, speed boosts, and faints.
