"""Gemini AI deep coach: sends battle state for strategic analysis."""
import os
import threading
import time
from pathlib import Path

_KEY_FILES = [
    Path(__file__).resolve().parent / ".gemini_key",
    Path(__file__).resolve().parent.parent / ".gemini_key",
]

SYSTEM_PROMPT = """You are an elite competitive Pokemon battle coach for Pokemon Revolution Online (PRO).
You receive a live battle state snapshot and must give high-impact tactical advice with tournament-level Game Theory (Minimax).

You must ALWAYS format your response in these exact structured sections:

MATCH CONTEXT:
- [Win-Con & Positioning]: State match equity/evaluation (e.g. lead preservation if ahead, comeback plan if behind) and key win-condition Pokémon to preserve.
- [Trap & Choice-Lock Warning]: Alert Focus Sash, Choice Scarf, or active Choice-lock on opponent.

▶ OPTION A [SAFE PLAY / LOW-RISK]:
- The exact action: state the specific MOVE to use (e.g. USE STEALTH ROCK, USE U-TURN, USE THUNDERBOLT) or safe SWITCH.
- Why: Explain why this is the consistent, lowest-risk play with guaranteed value (hazards, safe pivot, chip damage). When holding a solid lead (e.g. +1.5+ Eval / >70% Win Prob), focus on zero-risk lead preservation.

▶ OPTION B [GRANDMASTER READ / HIGH-REWARD]:
- The prediction play: state the specific MOVE (e.g. USE FIRE FANG, USE SWORDS DANCE) or predict-switch (e.g. SWITCH TO VOLCARONA).
- Read & Outcome:
  * If Opponent is CHOICE-LOCKED: Exploit their locked move by switching into an immune or resisting teammate for a 100% free setup or momentum turn.
  * If Player BLUFF OPPORTUNITY: Suggest feigning a choice-lock to condition the opponent and punish their switch.
  * If Facing HIGH SWITCH PRESSURE: Catch their switch-in with super-effective coverage or click a setup move.
  * If in a DEFICIT (<40% Win Prob): Suggest a high-variance read or aggressive gambit to turn the match around.

PREDICT OPPONENT:
- Predictive move / play read: what will the opponent click if they stay in, who will they switch to if they switch, and warn about lethal surprise coverage moves.

CRITICAL RULES:
1. STRICT MOVE SELECTION & ZERO HALLUCINATIONS:
- Under BOTH Option A and Option B, if recommending an attack, you must STRICTLY and ONLY recommend a move that is explicitly listed in 'LOCKED KNOWN MOVES', 'AVAILABLE IN-GAME ATTACKS', or 'MY MOVES'.
- The Pokémon in-game ONLY possesses these exact 4 moves. Recommending ANY move outside this list (e.g. suggesting Ice Beam when the Pokémon only knows U-turn, Darkest Lariat, Power Whip, Close Combat) is a fatal failure and completely unusable in-game.
- If moves are 'Unknown (attack menu closed / unscanned)', recommend a safe SWITCH to an advantageous bench Pokémon, or advise clicking 'Attack' to reveal moves.

2. OPPONENT UNREVEALED THREATS & ITEM TRAPS:
- Factor in 'OPPONENT UNREVEALED THREATS', 'OPPONENT ITEM TRAP ALERTS', and 'OPPONENT CHOICE-LOCK' (e.g. Focus Sash survival, Choice Scarf outspeed, locked attacks). Explicitly mention them in MATCH CONTEXT and PREDICT OPPONENT.

3. TACTICAL SWITCH PRESSURE & EVALUATION CONTEXT:
- Tailor aggression to match state: When ahead, protect your lead with Option A; when behind, use Option B to mount a comeback.
- When 'TACTICAL SWITCH PRESSURE' is HIGH, Option B should aggressively capitalize on the opponent's panic switch or forced free turn (e.g. Swords Dance, coverage snipe on the predicted switch-in, or double-switch).

4. STYLE & CONCISENESS:
- Keep the entire advice crisp, direct, and actionable (under 12-14 lines total).
- Use POKEMON and MOVE names in CAPS.
- If in team preview, recommend the best LEAD Pokémon and explain why.
"""


class AICoach:
    def __init__(self, model=None):
        self.model_name = model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.client = None
        self.last_response = ""
        self.last_state = ""
        self.busy = False
        self.enabled = False
        self.last_call = 0.0
        self.cooldown = 8.0
        self.error = None
        self._current_req_id = 0

    def _get_api_key(self):
        key = os.environ.get("GEMINI_API_KEY")
        if key:
            return key.strip()
        for kf in _KEY_FILES:
            if kf.exists():
                txt = kf.read_text().strip()
                if txt:
                    return txt
        return None

    def cancel(self):
        """Cancel any pending AI requests and drop their callbacks."""
        self._current_req_id += 1
        self.busy = False
        self.last_state = ""

    def reset_chat(self):
        """Reset conversation memory for a new battle."""
        self.cancel()

    def init(self):
        """Initialize the Gemini client. Returns True on success."""
        if self.client is not None:
            return True
        key = self._get_api_key()
        if not key:
            self.error = "No API key found"
            self.last_response = (
                "Set GEMINI_API_KEY env var\n"
                "or create .gemini_key file in pro-coach/ or progemini/"
            )
            return False
        try:
            from google import genai
            self.client = genai.Client(api_key=key)
            self.enabled = True
            self.error = None
            return True
        except ImportError:
            self.error = "pip install google-genai"
            self.last_response = "Run: pip install google-genai"
            return False
        except Exception as e:
            self.error = str(e)
            self.last_response = f"Gemini init failed: {e}"
            return False

    def ask(self, state_text, callback=None, turn=None):
        """Send state to Gemini in a background thread."""
        if self.busy:
            return
        if not self.enabled and not self.init():
            if callback:
                callback(self.last_response, turn)
            return

        self._current_req_id += 1
        my_req_id = self._current_req_id
        self.busy = True
        self.last_response = "AI thinking..."
        self.last_state = state_text

        def _worker():
            try:
                models_to_try = [self.model_name]
                for fb in ("gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash"):
                    if fb not in models_to_try:
                        models_to_try.append(fb)

                res_text = ""
                last_err = None
                for mdl in models_to_try:
                    try:
                        chat = self.client.chats.create(
                            model=mdl,
                            config={
                                "system_instruction": SYSTEM_PROMPT,
                                "temperature": 0.2,
                                "max_output_tokens": 800,
                            },
                        )
                        if "ATTACK MENU OPEN" in state_text or "menu: attack" in state_text:
                            prompt = (
                                "Current battle state (Player clicked Attack):\n"
                                "```\n" + state_text + "\n```\n\n"
                                "Analyze the available attack choices against the opponent and give your WHAT TO DO, WHY, and PREDICT OPPONENT advice."
                            )
                        else:
                            prompt = (
                                "Current battle state:\n"
                                "```\n" + state_text + "\n```\n\n"
                                "Give your strategic WHAT TO DO, WHY, and PREDICT OPPONENT advice for THIS turn."
                            )
                        response = chat.send_message(prompt)
                        res_text = response.text.strip()
                        self.model_name = mdl
                        break
                    except Exception as e:
                        last_err = e
                        if any(err_code in str(e) for err_code in ("429", "RESOURCE_EXHAUSTED", "NOT_FOUND", "404")):
                            continue
                        raise e

                if not res_text and last_err:
                    res_text = f"AI error: {last_err}"
            except Exception as e:
                res_text = f"AI error: {e}"

            # Only deliver response if this request has not been superseded or cancelled
            if self._current_req_id == my_req_id:
                self.last_response = res_text
                self.busy = False
                self.last_call = time.time()
                if callback:
                    callback(self.last_response, turn)
            else:
                self.busy = False

        threading.Thread(target=_worker, daemon=True).start()

    def can_auto(self):
        """True if enough time has passed for an auto-triggered call."""
        return (
            not self.busy
            and self.enabled
            and time.time() - self.last_call >= self.cooldown
        )
