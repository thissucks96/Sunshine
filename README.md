
Use a **dynamic budgeter** before each API call:

* classify input difficulty
* estimate visual complexity
* choose model/tokens/image-size accordingly
* retry/escalate only if validation fails

That gives lower average latency/cost without hurting hard-problem reliability.

## Recommended policy

### 1) Detect input mode

* If clipboard has text only → text pipeline
* If image present → OCR/vision pipeline (your current vision call)

### 2) Score difficulty (cheap heuristics)

Compute a `difficulty_score` from:

* text length
* number of operators/symbols (`^`, `/`, radicals, abs, piecewise markers)
* number of equals/inequalities
* trigger words: `compose`, `inverse`, `domain`, `range`, `rational`, `difference quotient`, `system`, `log`, `trig`
* multipart markers (`a) b) c)`)

Example bands:

* **Easy**: single-step/one-expression
* **Medium**: 2–4 algebraic transformations
* **Hard**: multipart/function/rational/system/proof-like formatting constraints

### 3) Score image complexity

From PIL image stats:

* resolution
* grayscale entropy / contrast
* edge density
* count of connected components proxy (busy worksheet vs single problem)

Bands:

* **Low**: clean crop, one problem
* **Medium**: one graph + text
* **High**: full worksheet / noisy screenshot / tiny text

### 4) Dynamic parameter selection

Use a matrix like:

* **Easy + Low image**
  `model=mini`, `max_tokens=220`, `max_image_size=1200`
* **Medium or Medium image**
  `model=mini`, `max_tokens=400`, `max_image_size=1600`
* **Hard or High image**
  `model=4o`, `max_tokens=700`, `max_image_size=2000`
* **Very hard multipart/graph-heavy**
  `model=4o`, `max_tokens=1000`, `max_image_size=2200` (cap)

### 5) Two-pass escalation (important)

Pass 1 = cheap profile.
Run your validators (`enforce_structure`, interval canonicalization, abc checks).

Escalate only if:

* structure error
* missing final answer
* invalid abc block
* malformed interval/union after normalization
* low-confidence extraction

Then Pass 2:

* upgrade model tier
* increase max_tokens
* increase image cap modestly

### 6) Prompt shaping by difficulty

* Easy: compact prompt, strict “minimal steps”
* Hard: add one line allowing slightly fuller work to avoid format failures
* Keep output contract strict regardless

### 7) Cache + dedupe

Hash normalized input:

* if same problem repeats within N minutes, return cached result
* avoids paying latency repeatedly when hotkey is pressed twice

### 8) Timeout/retry policy by tier

* Mini pass: shorter timeout (e.g., 20s), 1 retry
* 4o escalation: longer timeout (30–40s), 1–2 retries
* jittered backoff (you already do this well)

---

## Minimal integration points in your code

Add:

* `assess_text_difficulty(text) -> "easy|medium|hard"`
* `assess_image_complexity(img) -> "low|medium|high"`
* `choose_budget(mode, diff, img_complex, multipart) -> Budget(model, tokens, image_size)`
* `solve_with_budget(...)` and `escalate_budget(...)`

You already have most of the hard parts (validation + normalization).
So this is mostly a **routing layer**, not a rewrite.

---

## Concrete starter defaults for your app

Given your Math 95-heavy usage:

* default first pass:

  * text: `mini, 300 tokens`
  * image: `mini, 1400 px, 400 tokens`
* escalation:

  * `4o, 2000 px, 800 tokens`
* final escalation for multipart only:

  * `4o, 2200 px, 1000 tokens`

This will feel faster on average while still catching di

## Priority roadmap from here

## 1) Reliability hardening first

Before calc/precalc mode, make current mode deterministic and failure-transparent.

### A. Add explicit status signals

Right now “nothing happened” is still possible.

* trigger beep
* success beep
* failure beep
* optional tray notification with short reason

### B. Add clipboard retry

`ImageGrab.grabclipboard()` and `pyperclip.paste()` should be retried (2–3 attempts, ~80–120ms delay).

### C. Add API timeout + retry/backoff

Wrap calls with:

* connect/read timeout
* retry on 429/5xx/network timeouts
* exponential backoff with jitter

### D. Add structured error buckets

Return and surface:

* NO_INPUT
* API_AUTH_ERROR
* API_RATE_LIMIT
* API_TIMEOUT
* PARSE_ERROR
* STRUCTURE_ERROR

This makes debugging fast and UX clearer.

---

## 2) Performance optimization for weak connections

This is where you’ll feel real gains.

### A. Dynamic image quality ladder

Use staged upload size based on network quality or first-attempt failure:

* Tier 1: grayscale + autocontrast, max side 1280, PNG/JPEG quality tuned
* Tier 2: 1600
* Tier 3: 2000 only when OCR confidence seems low

Defaulting to smaller first can cut latency a lot.

### B. Route text vs image aggressively

If clipboard text exists and looks like a solvable typed prompt, skip image path entirely.

* text requests are faster/cheaper than vision
* maintain image only when needed

### C. Reduce output token budget

`MAX_TOKENS=1000` is high for your constrained format.

* try 300–450 for Math 95 mode
* faster decode and lower cost

### D. Prompt compaction

Your prompt is strong but verbose. Keep constraints, remove redundancy.
Shorter system prompt = slightly lower latency + fewer format drift points.

### E. Local pre-solve for known templates

For the fastest cases, skip API:

* single linear inequality
* two-part compound inequality
* interval merge/canonicalization
* simple linear equations

If parser succeeds locally, answer instantly; fallback to model only if unsupported.

---

## 3) UX upgrades that matter

Not a full GUI yet—just high-impact wins.

### A. Tray menu toggles

* Mode: Answer-only / Work
* Math profile: Algebra95 / CalcPrep
* Speed profile: Fast / Balanced / Accurate
* Clipboard source: Auto / Text-first / Image-only

### B. Hot-reload config

Reload config from tray without restarting process.

### C. Last-result preview

Tray item: “Copy last output again” and “Open last raw response”.
Great for recovery when clipboard is overwritten.

### D. Health check command

Hotkey for a quick self-test:

* API key present
* model reachable
* clipboard read works
  Outputs a one-line status.

---

## 4) Engine architecture improvements

You can refactor without changing behavior.

### A. Split into modules

* `config.py`
* `hotkeys.py`
* `solver_pipeline.py`
* `interval_engine.py`
* `model_client.py`
* `ui_tray.py`
* `telemetry.py`

### B. Pipeline stages

Make explicit stages:

1. acquire input
2. classify input
3. local solve attempt
4. model solve
5. post-process normalize
6. verify/canonicalize
7. render output

### C. Add lightweight telemetry log (local file)

Track:

* timestamp
* source type (text/image)
* latency ms
* token usage (if available)
* success/failure code
* retry count

This tells you exactly where speed/reliability is failing.

---

## 5) Accuracy guardrails (important)

Your interval engine is already solid. Add final consistency checks.

### A. Semantic validator for compound inequality outputs

If model returns:

* `x > -2 or x > 9`
  local engine should canonicalize to `(-2, ∞)` automatically (you already partly do this).
  Add stronger parse acceptance for variants with spaces/Unicode operators.

### B. Contradiction detection

If WORK implies one thing and FINAL ANSWER another, trust parsed final expression + canonicalization or flag “CONSISTENCY WARNING.”

### C. Strict final block replacement

Replace only the **last** FINAL ANSWER block, not every block.
Current regex can rewrite both occurrences in some layouts.

---

## 6) Hotkey subsystem: polling vs event-driven

You asked speed/optimization, so this matters.

* **Polling** is okay and flexible for complex combos, but wastes cycles and can miss edge timing.
* **RegisterHotKey (event-driven)** is leaner and usually more stable for your use case.

Recommendation:

* Move back to `RegisterHotKey` unless you need WIN-key combos or advanced chord behavior.
* Keep polling only if you truly need custom key semantics.

---

## 7) What to do before calc/precalc mode

Do this in order:

1. Add retry/backoff + status beeps + error buckets
2. Add dynamic image-size ladder + lower max tokens
3. Add local solver fast-path for inequality/equation templates
4. Add telemetry log + latency dashboard (even a CSV)
5. Then branch into calc/precalc mode profiles

If you do these 5, your app will feel much faster and “product-ready,” especially on weak internet.

---

## Suggested config additions right now

Add these keys:

```json
{
  "mode": "work",
  "profile": "algebra95",
  "speed_profile": "balanced",
  "max_tokens_text": 350,
  "max_tokens_image": 450,
  "image_max_side_fast": 1280,
  "image_max_side_balanced": 1600,
  "image_max_side_accurate": 2000,
  "api_timeout_s": 25,
  "api_retries": 2,
  "api_backoff_base_ms": 350,
  "clipboard_retries": 3,
  "clipboard_retry_delay_ms": 90,
  "beep_enabled": true,
  "log_enabled": true
}
```

---

If you want, next I can give you a **drop-in v2 patch** for your current script that adds:

* clipboard retry
* API retry/backoff
* timeout
* speed profiles
* last-FINAL-only replacement
* optional beeps/logging

with minimal code churn so you can test immediately.





















### TODO (low priority, high leverage)

1. **Last-query recall**

   * Store last input (text or image path)
   * Store last mode (answer / work)
   * Store last output (normalized + raw)
   * Allow re-copy / re-run of last query
   * In-memory only (ring buffer size 1–3)

2. **Minimal built-in screenshot capture (ShareX replacement, future/public)**

   * Freeze screen (fullscreen overlay with captured framebuffer)
   * Rectangle selection tool (mouse drag → bounds)
   * Crop screenshot to selection
   * Save PNG to flat, app-controlled folder (timestamp filename)
   * Cache saved image path into internal clipboard/index (Ditto-lite)
   * Use this cache as vision history / last-query source

Constraints:

* No UI chrome
* No annotation or editing
* No persistence beyond what’s necessary
* Silent operation only
* Keep scope minimal

Status: **Not urgent**, but strategically important for autonomy and public readiness.
