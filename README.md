# 📦 Shop Stock Helper

A small **tool-calling agent** for one clear job:

> **Decide what a small shop should reorder and how urgent it is — then draft the note.**

It looks things up in the shop's own data, works out the urgency, and writes a note
for a human to review. It shows **every step** it takes, stops as soon as it has
enough information, and **never takes an action that cannot be undone**.

- **Deployed app:** `https://your-app-name.streamlit.app`  ← replace after deploying
- **Repository:** `https://github.com/your-username/your-repo-name` ← replace after pushing

---

## The special rule (followed here)

Every visitor pastes **their own free Gemini key** in the sidebar.

- No key is stored, committed, or shared.
- Nobody uses the owner's quota.
- There is **no key anywhere in this code**.

Get a free key: <https://aistudio.google.com/app/apikey>

---

## The one job, and the three tools

The job needs three steps: **read → compute → draft**. Each step is a tool.

| Step | Tool | What it does | Needs internet? |
|------|------|--------------|-----------------|
| 1. READ | `low_stock(threshold)` | Lists items at or below `threshold` units from `data/stock.csv`, sorted by least stock first. | No |
| 2. COMPUTE | `days_of_stock(item, daily_sales)` | Estimates how many days one item's stock lasts at `daily_sales` units/day. | No |
| 3. DRAFT | `draft_reorder_note(item, quantity)` | Writes a reorder note for one item. **Draft text only — never sent.** | No |

All tools are plain Python, use only `data/stock.csv`, and need **no key and no internet**.

### A typical run

```
"What is running low in the shop?"
  → low_stock(threshold=10)      … finds the low items
  → (stop) answer written
```

```
"Which low-stock items run out within a week at about 2 a day?"
  → low_stock(threshold=10)                 … candidates
  → days_of_stock(item, daily_sales=2)      … once per candidate
  → draft_reorder_note(item, quantity)      … for the urgent ones
  → (stop) answer written
```

---

## How the agent works

```
app.py            Streamlit UI — sidebar key, chat, and the step viewer
   │
   ▼
agent_core.py     Gemini function-calling loop (the "brain")
   │  1. send the user question + 3 tool declarations + system instruction
   │  2. Gemini replies with tool call(s)
   │  3. run the plain-Python tool
   │  4. send the result back to Gemini
   │  5. repeat until Gemini stops calling tools  →  final answer
   │     (hard cap: MAX_STEPS = 6, so it can never loop forever)
   │
   ▼
tools.py          the 3 offline tools (read / compute / draft)
   │
   ▼
data/stock.csv    18 rows of made-up shop stock data
```

`run_agent()` returns `(final_answer, steps)`, and `app.py` renders `steps` in
expanders so the visitor can see **the exact tool, the exact input, and the exact
result** at every step.

---

## Being honest (built into the system prompt)

The agent is instructed to:

1. **Stay in its job.** Anything that is not about this shop's stock and reordering
   (prices, weather, tax, news, …) is answered with "that is outside my job" — with
   no guess.
2. **Never invent numbers.** It must call a tool for real quantities and suppliers.
3. **Report empty results.** If a tool finds nothing, or an item is not in the file,
   it says exactly that. `days_of_stock` / `draft_reorder_note` return `ok=false`
   with the message `No item matching '…' was found in the stock file.`
4. **Never take real actions.** The only "writing" tool produces draft text. Nothing
   is sent, ordered, emailed or saved. If asked to *actually order or email*, it says
   it can only draft a note — and drafts one.

---

## Files

```
app.py            Streamlit UI (sidebar key, chat, step viewer)
agent_core.py     Gemini function-calling agent loop + system prompt
tools.py          the 3 offline tools
data/stock.csv    18 made-up rows: item, quantity, supplier
test_tools.py     32 offline checks (no key needed)
tests.md          8 end-to-end test scenarios
requirements.txt  streamlit, google-generativeai
README.md         this file
```

---

## Run it locally

```bash
pip install -r requirements.txt
python test_tools.py            # 32 offline checks, no key needed
streamlit run app.py            # then paste your own Gemini key in the sidebar
```

---

## Deploy it (Streamlit Community Cloud)

1. Push this repo to GitHub (public).
2. Go to <https://share.streamlit.io> → **New app** → pick the repo.
3. Main file path: **`app.py`**. Deploy.
4. **Do not add any secrets** — the visitor supplies their own key.
5. Open the deployed URL in a **private/incognito window** to confirm it loads
   without login and runs after pasting a key.

---

## Data note

`data/stock.csv` is **invented by the author** for this assignment. It contains no
real shop, supplier, or person's private information.
