# PRO AI Coach

A real-time, AI-powered battle assistant for **Pokemon Revolution Online (PRO)** PvP and Ranked battles.
Combines **local computer vision & OCR (RapidOCR)** with **instant local damage/speed math (<1ms)** and the **Gemini 2.5 Flash API** for grandmaster-level tactical battle coaching.

> **Ethics Line (by design):** The coach is *strictly read-only*. It never clicks, never sends simulated inputs, and never touches game memory or network packets. You make every play — the coach acts as an always-on-top HUD, like a competitive coach sitting next to you.

---

## 1. System Architecture

```
PROClient Window (Unity Game)
        │
        │  win32gui tracks window position; mss captures screen regions
        ▼
CaptureWorker (Background Thread)
        │  • Log OCR (Battle Log panel docked bottom-left)
        │  • HP-bar color-run detection (my HP% & foe HP%)
        │  • Active Pokemon nameplate OCR + Party panel tracking
        ▼
BattleState (Scout Sheet & Persistence)
        │  • 6v6 Team tracking (active, fainted, levels, held items)
        │  • Revealed moves, status conditions, speed stage tracking (+/-)
        │  • Smogon unrevealed move threat probabilities
        ▼
┌───────────────────────────────────────┴───────────────────────────────────────┐
│                                                                               │
▼                                                                               ▼
Instant Quick-Calc Bar (<1ms, Local)                        Gemini AI Coach (Cloud)
• Speed pill (🟢 FASTER / 🔴 SLOWER / ⚡ TIE)              • Deep tactical plays & predictions
• Scarf threat warning if opponent outspeeds               • Strict move enforcement (no hallucination)
• Real-time damage ranges & KO tags (OHKO/2HKO)            • High-priority threat avoidance & sacking
• Type effectiveness multipliers (2.0x, 0.5x, 0x)          • Context-aware switch recommendations
└───────────────────────────────────────┬───────────────────────────────────────┘
                                        │
                                        ▼
                   AIOverlay (Tkinter Always-on-Top HUD)
                   • Status bar (model, cooldown, state updates)
                   • Quick-Calc Bar (<1ms speed & damage chips)
                   • AI Strategic Advice card (What / Why / Predict)
                   • 6v6 Team Tracker view (Player 6 & Opponent 6)
                   • Showdown Team Importer modal (locks known sets)
                   • In-app Battle State Editor
```

---

## 2. Key Features

1. **Stockfish-Style Quantum Evaluation Bar & Win Probability**:
   - Computes instant (<0.2ms) Match Equity from material counts (alive mons), team HP pools, active speed tempo, and immediate OHKO threats.
   - Live visual horizontal gauge bar in HUD: `♜ EVAL: +1.8 | 68% WIN PROB [FAVORED]`.
   - Signals when to play risk-averse lead preservation (when ahead) vs high-variance comeback gambits (when behind).

2. **Choice Lock & Conditioning Bluff Protocol**:
   - **Opponent Lock Exploitation**: Automatically tracks opponent Choice items (`Choice Scarf`, `Choice Band`, `Choice Specs`). When locked, instantly flags immune teammates (e.g., Flying vs Ground, Levitate, Flash Fire, Water Absorb) or resists to seize 100% free setup turns.
   - **Player Bluff Potential**: Detects when holding a non-Choice item (Life Orb/Leftovers) on a common Choice user, recommending feigning a Choice lock to bait an opponent switch and punish it with surprise coverage.
   - **HUD Pill Alert**: Displays `🔒 FOE LOCKED: [MOVE]` in coral red or `🎭 BLUFF READY` in purple.

3. **Dual-Path Strategic Advice ("Option A" vs "Option B")**:
   - **`▶ OPTION A [SAFE PLAY]`**: Low-risk, guaranteed-value line (hazards, safe pivot, chip).
   - **`▶ OPTION B [GRANDMASTER READ]`**: High-reward prediction (punishing forced switches with 4x coverage or setup moves).
   - **Predict Opponent & Trap Watch**: Predicts what opponent will click if staying vs who they switch to, with Focus Sash & Choice Scarf trap warnings.

4. **6v6 Full Team Tracking & Held Item Management**:
   - Tracks all 6 player slots and all 6 opponent slots.
   - Assign and edit held items for both sides (e.g., Choice Scarf, Leftovers, Focus Sash, Life Orb, Megas, Gems).
   - Real-time active and fainted indicators.

5. **Showdown Team Importer & Strict Move Lock**:
   - Paste any standard Pokémon Showdown export directly into the overlay via the **Showdown Import** button.
   - Automatically populates your 6-mon team, levels, held items, and legal moves.
   - **Zero Hallucination Guarantee**: Locks your active moves to your in-game 4 moves so the AI never recommends unlearned moves.

6. **Zero-Latency Instant Quick-Calc Bar (<1ms)**:
   - Runs locally in **<0.2 milliseconds** on every turn change or state edit without waiting for API responses.
   - **Speed Pill**: Exact speed stat comparison and Choice Scarf threat alerts.
   - **Damage Chips**: Damage percentage intervals, type effectiveness (e.g., `[4.0x]`, `[0.5x]`), and KO boundaries (`OHKO`, `2HKO`, `3HKO`).

7. **Smogon-Powered Opponent Scout**:
   - Automatically calculates unrevealed move odds from competitive Smogon usage data.
   - Warns of lethal 2x / 4x super-effective coverage moves before the opponent reveals them.

8. **Integrated Battle State Editor**:
   - One-click editable state in the HUD allows you to adjust active Pokémon, HP percentages, or battle log lines on the fly.

---

## 3. Project Structure

```
pro-coach/
├── run.bat / run_ai.bat     # 1-click launchers for the AI Coach
├── main.py                  # Root application: CaptureWorker + AIOverlay + AICoach
├── ai_coach.py              # Gemini API engine with strict prompt enforcement
├── overlay.py               # Tkinter HUD: Quick-Calc Bar, 6v6 tracker, Showdown modal
├── requirements.txt         # Dependencies (mss, pillow, pywin32, rapidocr, numpy, google-genai)
├── test_all.py              # 42-check self-test suite (100% passing)
├── battlestate.json         # Runtime battle state persistence
├── state.txt                # Live formatted battle snapshot
├── procoach/                # Core local engine package
│   ├── capture.py           # Window discovery (win32gui) & screen capture (mss)
│   ├── ocr.py               # RapidOCR text recognition
│   ├── hp.py                # HP-bar locator & percentage scanner
│   ├── state.py             # BattleState, Showdown parser, Smogon threat scout
│   ├── calc.py              # Damage formulas, speed calculation, KO odds
│   ├── coach.py             # Coach capture engine & PvP scan parser
│   ├── advisor.py           # Heuristic advice rules & type charts
│   └── __init__.py          # Package initialization
└── data/                    # Cleaned 5-file database (~2.3 MB)
    ├── dex.json             # 1481 species (base stats, types, abilities)
    ├── moves.json           # 953 moves (power, category, accuracy, type)
    ├── items.json           # 583 items (held-item index & aliases)
    ├── learnsets.json       # Learnable movepools per species
    └── smogon_sets.json     # Smogon competitive sets & move usage %
```

---

## 4. Quick Start

### Installation

Ensure Python 3.10+ is installed, then install dependencies:
```bash
pip install -r requirements.txt
```

Set your Gemini API key in `.gemini_key` or as an environment variable:
```bash
set GEMINI_API_KEY=your_key_here
```

### Running the Coach

- **Double-click `run.bat`** (or `run_ai.bat`).
- Alternatively, launch from terminal:
  ```bash
  python main.py
  ```

### Battle Guidelines

1. **Keep the PROClient window visible**: The coach reads live screen pixels.
2. **Keep the Battle Log panel OPEN**: Dock the Battle Log at the bottom-left of the game screen so that move announcements, items, and send-outs are captured automatically.
3. **Import or Set Your Team**: Click **Showdown Import** on the overlay to load your team and lock your moves before battling.

---

## 5. Running Tests

Run the full 42-check self-test suite anytime:
```bash
python test_all.py
```
To verify Showdown imports, Quick-Calc latency, and Smogon threat scouting:
```bash
python scratch/test_showdown_calc_scout.py
```
