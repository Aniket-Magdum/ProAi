# PRO Instant Coach

A real-time battle coach for **Pokemon Revolution Online (PRO)** PvP / Random Ranked battles.
It watches the game window, reads the battle live, and tells you what to do — **instantly, locally,
with no AI server in the loop for routine calls**. The chat AI (a second brain you ping in ZCode)
handles deep prediction calls by reading the same state file the overlay uses.

> **Ethics line (by design):** the coach is *read-only*. It never clicks, never touches the game
> process or network. You make every move — it advises, like a coach sitting next to you.
> Input automation would be botting, violate PRO's rules, and risk your account. It will not be added.

---

## 1. How it works (the pipeline)

```
PROClient window (Unity game)
        │  win32gui finds window, tracks position/size every tick
        ▼
capture.py ── mss screen grabs of fixed regions (fractions of the client area):
        │       log panel | move/switch menu | opponent zone | your zone | party panel
        ▼
┌── per tick (~1s on a low-end PC) ──────────────────────────────────────────┐
│ 1. MENU OCR (fast, advice-gating):  "Choose Attack" / "Choose Pokemon"     │
│ 2. FIELD PIXEL SCAN (hp.py): finds each HP bar (colored-pixel run),        │
│    reads fill % and bar position; bar move = new mon in                    │
│ 3. LABEL OCR (tiny crop above each bar): who is actually on the field      │
│    → self-corrects actives every 2.5s even if log lines are missed         │
│ 4. PARTY OCR (every 5s): your 6 slots (names + levels) = ground truth      │
│    bench; stale entries from previous battles get pruned                   │
│ 5. LOG OCR (slowest, capped, incremental): reads only the newest slice of
│    the panel every 2s + a full resync every 12s → the scout sheet.
│    Runs on the fast engine (no angle-classifier, 320px det cap);
│    small accuracy-critical crops use the quality engine.
└────────────────────────────────────────────────────────────────────────────┘
        ▼
state.py — BattleState (the scout sheet, persisted to battlestate.json):
        • both active mons + full bench (names, types, levels, HP%)
        • every revealed move/item/ability/status per mon, both sides
        • faint inference: new send-out without "Come back" = previous mon died
        • new-battle auto-reset when the turn counter drops back to 1-2
        ▼
advisor.py + calc.py — instant rules engines (no AI, <1ms):
        • full 18-type chart × STAB × accuracy        → USE / AVOID
        • damage estimation (gen 3+ formula, assumed neutral spreads, scouted
          item multipliers like Life Orb / Choice Band) → KO % branching
        • speed estimate (levels read live; Choice Scarf detected) → who moves first
        • danger engine   → SWITCH NOW (hopeless matchup / lethal threat at low HP)
        • finish engine   → FINISH IT (their HP in KO range of your best move)
        • switch ranking  → best bench mon vs their active (resist/threat score)
        • opponent-switch prediction → PIVOT WATCH (they hold Flip Turn/U-turn…),
          pull-back warnings when their mon is low
        • Smogon-weighted predictions → THEIR LIKELY MOVES before they act
        ▼
        ├── overlay.py — always-on-top advice window next to the game
        │     (borderless: drag title bar to move, ⛶ grip to resize, ✕ to close;
        │      action lines sorted to top: SWITCH NOW > USE > EXPECT > info)
        └── state.txt — human-readable snapshot, read by the chat AI for
              mind-game calls (double-switches, set reads, traps) in seconds
```

**Two-tier coaching model:**

| Layer | Where | Latency | Handles |
|---|---|---|---|
| Instant coach | your PC (rules + OCR) | < 1s | type matchups, damage ranges, KO odds, switch picks, threats |
| Deep coach | chat AI (cloud) | ~3-5s | set reads, prediction/traps, sacking plays, team building |

---

## 2. Project structure

```
pro-coach/
├── run_coach.bat            # double-click launcher (overlay, below-normal CPU priority)
├── main.py                  # tick loop: capture → read → state → advise → overlay/state.txt
├── test_all.py              # 31-check self-test suite (replays real log lines)
├── bench_ticks.py           # measures real per-tick latency on this machine
├── bench_ocr2.py            # compares OCR engine configs on live pixels
├── capture_samples.py       # snapshots live regions to data/samples/ + engine comparison
├── fetch_smogon.py          # one-time: builds Smogon usage DB from pkmn/smogon mirrors
├── state.txt                # live battle snapshot (chat AI reads this)
├── battlestate.json         # runtime persistence (survives coach restarts)
├── coach.lock               # single-instance guard (PID liveness check)
├── procoach/                # the package
│   ├── capture.py           # window discovery (win32gui) + region grabs (mss)
│   ├── ocr.py               # RapidOCR wrapper: preprocess (upscale/contrast) + read
│   ├── hp.py                # HP-bar locator: colored-run scan, fill fraction, 2x downscale
│   ├── state.py             # BattleState: log parsing, scout sheet, persistence, fuzzy dex match
│   ├── advisor.py           # all advice engines (type chart, danger, switch, predictions)
│   ├── calc.py              # damage/speed estimation + item multipliers + KO probability
│   ├── overlay.py           # always-on-top tkinter advice window: drag/resize/close, threaded
│   └── parse_data.py        # one-time: Showdown pokedex/moves/learnsets → JSON
└── data/
    ├── dex.json             # 1481 species: name, types, base stats (Showdown)
    ├── moves.json           # 953 moves: type, power, category, accuracy
    ├── learnsets.json       # 1233 species: full learnable move pools
    ├── smogon_sets.json     # 555 species: real usage freq for moves/items/abilities
    ├── samples/             # live-captured region PNGs (OCR regression fixtures)
    └── *.ts                 # raw Showdown sources (kept for rebuilds)
```

### Advice catalog (what you'll see)

| Line | Meaning |
|---|---|
| `USE <MOVE>: ~34-40% vs ~100% HP - NO KO (you hit first)` | best move + damage branch + speed |
| `USE <MOVE>: LIKELY KO (you hit first)` | damage range covers their current HP |
| `EXPECT: switch to <mon> (absorbs your X, threatens you)` | their best response to your move |
| `YOUR <MON> FAINTED - SWITCH -> <MON>` | instant pick the moment a faint is read |
| `SWITCH NOW: you can't hurt <mon> and it threatens you -> send <mon>` | hopeless matchup, with the pick |
| `SWITCH NOW: <move> KOs you at ~35% HP -> send <mon>` | lethal threat at low HP, with the pick |
| `FINISH IT: <move> KOs <mon> at ~28%` | kill window — don't switch |
| `PIVOT WATCH: <mon> has Flip Turn - expect <mon> in` | their pivot prediction |
| `<mon> is low - expect a pull-back` | don't chase with anything frail |
| `BEWARE: ... / THEIR LIKELY MOVES: ...?` | threats + Smogon-ranked predictions |
| `no battle on screen - queue up` | battle-presence guard (no phantom reads) |

---

## 3. Installation & usage

```
pip install mss pillow pywin32 rapidocr-onnxruntime
```
(Windows OCR was unavailable on this system; RapidOCR is pip-only, no admin needed.)

**Run:** double-click `run_coach.bat` (or `python main.py`). The overlay parks itself
next to the game window: **drag the title bar to move it, drag the ⛶ corner grip to
resize, ✕ closes it**. A lock file (`coach.lock`) refuses a second instance.

**The three rules:**
1. Keep the PRO window **visible** — the coach reads physical screen pixels (closing or
   covering the game flips the overlay to "PROClient not found" / "no battle on screen"
   instead of showing stale data).
2. Keep the in-game **Battle Log panel open**, docked bottom-left.
3. **One instance only** — the lock file enforces it; two coaches = double CPU = game lag.

**Rebuild databases** (only if you want to refresh them):
`python procoach/parse_data.py` then `python fetch_smogon.py`

**Self-test:** `python test_all.py` — replays real battle-log lines through the whole
stack (parsing, faint inference, dead-switch inference, new-battle reset, damage calc,
KO branching, scarf detection, switch ranking, Smogon predictions, persistence). 31 checks.

---

## 4. Performance engineering (why it keeps up on a low-end PC)

Measured on the target machine (RapidOCR ONNX, CPU-only): mean tick **~2.5s**,
fast path (nothing to read) **~0.4s** — down from 4.6s mean / 7.5s max before
optimization.

- **Two OCR engines**: fast engine (no angle-classifier, 320px det cap) for the big
  log region; quality engine for small accuracy-critical crops. Engine configs were
  benchmarked on live game pixels before being chosen.
- **Incremental log read**: only the newest panel slice every 2s; full-panel resync
  every 12s. ~60% fewer pixels per read.
- **Advice-critical reads first**: nameplate/menu reads precede log OCR in every tick
- **HP scan at half resolution** — 4x fewer pixels, coords scaled back for label crops
- **Tiny-crop OCR**: nameplates are cropped from a 34px strip above the located bar,
  never the full zone
- **Throttles**: log 1/2s, nameplate 1/2.5s per side, party 1/5s, plus image-signature
  change-gating (no OCR when pixels didn't change)
- **Tick budget**: party OCR defers a cycle when the tick is already slow
- **Worker thread**: capture/OCR runs off the UI thread — the overlay repaints at ~2Hz
  regardless of OCR latency
- **Idle skip**: when no battle is on screen, pixel scans stop entirely
- **Low process priority** (`run_coach.bat`): the game always wins CPU contention

---

## 5. Known limitations

- **OCR typos** on exotic names — mitigated by fuzzy dex matching (short names like Mew
  get a looser cutoff); a truly garbled read delays that mon's registration ~2.5s
- **OCR per-call cost** (~0.5-1.5s on this CPU) is the hard floor — optimizations cut
  the *number and size* of calls, not the model speed. Next lever: lighter ONNX model
  or the Windows OCR language pack
- **Aggressive downscaling loses lines**: scale-1 log reads dropped send-out lines in
  live validation — the log stays at scale=2 on the fast engine (validated choice)
- **OCR level misreads** on the party panel ("Lv 815" → 15) — levels only feed speed
  estimates; your active's and the opponent's levels come from the reliable nameplate read
- **Damage estimates are ±15%** — EVs/natures are unknowable; the calc assumes random-
  battle-average spreads (31 IV / ~85 EV, neutral nature). Item multipliers are applied
  only once an item is scouted
- **Abilities aren't modeled in calc** (Protean, Huge Power, weather boosts...) — those
  reads stay with the chat-AI layer
- **Low-tier mons lack Smogon data** (555 species covered) → learnset heuristic fallback
- **Unrevealed opponent slots** are unpredictable by design; predictions start the moment
  a mon is sent out
- **Fixed region fractions** assume the default client layout with the Battle Log panel
  docked bottom-left — dragging panels shifts capture regions

---

## 6. Design history (hard-won lessons baked into the code)

- HP bars must be located by **color-run search**, not fixed coordinates — PRO's battle
  scene shifts with window size; naive track-expansion once swallowed a dark UI row and
  reported 0% HP (now capped at 1.6x the colored run)
- Green **menu progress bars / chat text** false-positive as HP bars → battle-presence
  guard (HP only trusted within 45s of fresh battle-log signals; out of battle the
  overlay says "no battle on screen" instead of showing stale turns)
- PRO writes faints **two ways** ("X has fainted!" vs "The opposing X fainted!") — both
  parsed; faint inference covers OCR misses; a faint of YOUR mon instantly triggers the
  switch pick (it no longer waits for the short Choose-Pokemon screen)
- The party panel is **ground truth** for your team — bench entries not on it are stale
  ghosts from previous battles and get pruned
- Scout state **persists across restarts**; new battles auto-reset (turn counter dropping
  back to 1-2 is the boundary signal)
- Status lines arrive with trailing text ("...paralyzed! It may be unable to move!") —
  regexes match prefixes, not full lines
- Fast battles scroll log lines past the OCR between ticks → actives **self-correct from
  the field nameplates every 2.5s**, so a missed line costs seconds, not the turn
- A field replacement **without a logged "Come back" is a faint** (that's the only other
  way an active leaves the field) — the old mon is marked dead so the bench ranker never
  recommends a corpse; the mark **self-heals** if the mon re-enters the field
- **Chat contamination**: when another window covers the game, the "log region" reads
  that window's text — and keywords like "battle" in chat fooled the presence guard into
  keeping stale intel alive forever. Presence now requires a *real state change*, never
  a keyword match
- **Always validate OCR changes on real captures**: the synthetic-text benchmark said
  scale-1 was fine; live PRO text proved it drops send-out lines. `capture_samples.py`
  exists so no OCR setting ships without a live-pixel check
- The overlay UI must never block on OCR → capture/read runs on a **worker thread**;
  advice lines are **prioritized** (action first) and persist until superseded

---

## 7. Roadmap

**Next up**
- [ ] Region auto-calibration: detect the battle UI dynamically (find nameplates by
      template) instead of fixed fractions — survives any layout/dragging
- [ ] Party-panel slot HP colors → know which bench mons are damaged
- [ ] Level-parse hardening: cross-check party OCR levels against nameplate reads
- [ ] Ability modeling in damage calc (scouted Rough Skin, Intimidate stages, Choice
      lock inference from repeated same-move turns)
- [ ] EV/nature back-calculation: refine damage estimates from observed roll bounds
      over multiple hits (Bayesian, per-mon)
- [ ] Overlay polish: per-line colors (engine already emits categories), opacity
      setting, region/layout config file

**Later**
- [ ] Self-learning PRO meta DB: log every observed set per species across battles →
      PRO-specific usage frequencies (the Smogon DB generalizes; this one wouldn't)
- [ ] Per-player memory for Normal Ranked (opponent reuses teams/sets)
- [ ] Sound/flash alerts for SWITCH NOW when the overlay is obscured
- [ ] Battle replay export: full parsed log per battle for post-game review
- [ ] Alternate OCR backend (Windows OCR language pack or lighter ONNX model) for
      even lower latency on weak hardware

**Done recently**
- ✅ Overlay drag/resize/close; single-instance lock; game-closed/zombie-state detection
- ✅ Faint-triggered instant switch picks, advice persistence + priority sorting
- ✅ Dead-switch inference (field replacement without Come back = faint) + self-heal
- ✅ Latency round: two OCR engines, incremental log slices, tick budgeting —
      mean tick 4.6s → 2.5s, fast path 0.4s
- ✅ Noise gate: BEWARE only fires on real threats; predictions capped to top 3
- ✅ Stale-intel fix: presence requires real state changes (chat keywords can't fake it)
- ✅ Live-sample fixture library (`capture_samples.py`) for OCR regression testing

**Explicitly not planned**
- Any input automation / auto-playing (botting = ban risk; read-only coach by design)

---

## 8. File-by-file quick reference

| File | Read it when… |
|---|---|
| `main.py` | changing tick order, throttles, or the worker/overlay split |
| `procoach/state.py` | log lines parse wrong, scout sheet misbehaves, persistence |
| `procoach/advisor.py` | advice wording/logic, type chart, danger/switch engines |
| `procoach/calc.py` | damage/speed math, item multipliers, KO probability |
| `procoach/hp.py` | HP% reads wrong or lags |
| `procoach/capture.py` | game window regions shift (layout change) |
| `procoach/ocr.py` | OCR quality/speed issues |
| `procoach/overlay.py` | overlay display, line priority |
| `test_all.py` | any behavior change — run it before and after |
