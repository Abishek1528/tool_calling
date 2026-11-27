"""
test_tools.py - offline checks for the Shop Stock Helper.

These tests need NO internet and NO Gemini key. They prove the tools behave
correctly and fail honestly. Run with:

    python test_tools.py

The end-to-end agent checks (which do use a key) are described in tests.md.
"""

import agent_core
import tools

PASSED = 0
FAILED = 0


def check(name, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED += 1
        print(f"  FAIL  {name}  {detail}")


print("== Data file ==")
rows = tools._load()
check("data has at least 15 rows", len(rows) >= 15, f"(found {len(rows)})")
check(
    "every row has item/quantity/supplier",
    all(r["item"] and isinstance(r["quantity"], int) and r["supplier"] for r in rows),
)

print("\n== Tool 1: low_stock (READ) ==")
res = tools.low_stock(5)
check("low_stock(5) works", res["ok"] is True, res.get("error", ""))
items = res["result"]["items"]
check("low_stock(5) returns only <= 5", all(i["quantity"] <= 5 for i in items))
check("low_stock(5) is sorted ascending", items == sorted(items, key=lambda x: x["quantity"]))
check("low_stock(999) returns everything", tools.low_stock(999)["result"]["count"] == len(rows))
check("low_stock(-1) returns nothing honestly", tools.low_stock(-1)["result"]["count"] == 0)
check("low_stock('abc') fails honestly", tools.low_stock("abc")["ok"] is False)

print("\n== Tool 2: days_of_stock (COMPUTE) ==")
res = tools.days_of_stock("Toor Dal (1kg)", 1.5)
check("days_of_stock works", res["ok"] is True, res.get("error", ""))
check("days_of_stock math is right", res["result"]["days_of_stock"] == round(3 / 1.5, 1),
      str(res.get("result")))
res = tools.days_of_stock("toor dal", 1)  # case-insensitive
check("days_of_stock is case-insensitive", res["ok"] is True)
res = tools.days_of_stock("Unicorn Tears", 1)
check("unknown item fails honestly", res["ok"] is False and "was found" in res["error"].lower(),
      res.get("error", ""))
res = tools.days_of_stock("Sugar (1kg)", 0)
check("daily_sales=0 fails honestly", res["ok"] is False)

print("\n== Tool 3: draft_reorder_note (DRAFT) ==")
res = tools.draft_reorder_note("Coffee (200g)", 20)
check("draft works", res["ok"] is True, res.get("error", ""))
check("draft is marked as not sent", res["result"]["sent"] is False and res["result"]["delivered"] is False)
check("draft includes supplier", res["result"]["supplier"] in res["result"]["note"])
check("draft says DRAFT", "DRAFT" in res["result"]["note"])
check("draft for unknown item fails honestly", tools.draft_reorder_note("Nope", 5)["ok"] is False)
check("draft with bad quantity fails honestly", tools.draft_reorder_note("Sugar (1kg)", 0)["ok"] is False)

print("\n== Agent wiring (no network) ==")
check("exactly 3 tools are registered", len(tools.TOOL_SPECS) == 3)
check(
    "tool spec names match functions",
    set(tools.TOOL_FUNCTIONS) == {s["name"] for s in tools.TOOL_SPECS},
)
check("build_tool() constructs a declaration", agent_core._build_tool() is not None)
si = agent_core.SYSTEM_INSTRUCTION.lower()
check("prompt says stay in one job", "one job" in si)
check("prompt forbids inventing data", "never invent" in si)
check("prompt requires honesty out of scope", "outside your job" in si)
check("prompt says nothing is sent", "never sent" in si or "nothing is ever sent" in si)
check("safe step limit is set", agent_core.MAX_STEPS >= 3)

print("\n== Agent loop plumbing (mocked, no network) ==")


class _FC:  # fake function_call
    def __init__(self, name, args):
        self.name = name
        self.args = args


class _Part:
    def __init__(self, fc=None):
        self.function_call = fc


class _Resp:
    def __init__(self, parts, text=""):
        self.candidates = [type("C", (), {"content": type("X", (), {"parts": parts})()})()]
        self.text = text


resp = _Resp([_Part(_FC("low_stock", {"threshold": 5})), _Part(_FC("draft_reorder_note", {"item": "Coffee (200g)", "quantity": 20}))])
calls = agent_core._iter_function_calls(resp)
check("loop extracts function calls from a response", len(calls) == 2, str(len(calls)))
check("loop reads tool name", calls[0].name == "low_stock")
check("loop reads tool args", agent_core._plain_args(calls[0].args) == {"threshold": 5})
check("no calls -> agent stops", agent_core._iter_function_calls(_Resp([_Part()])) == [])

# simulate executing the extracted calls the way run_agent does
recorded = []
for c in calls:
    recorded.append({"name": c.name, "result": tools.TOOL_FUNCTIONS[c.name](**agent_core._plain_args(c.args))})
check("extracted calls execute and yield ok results", all(r["result"]["ok"] for r in recorded))

print(f"\n{PASSED} passed, {FAILED} failed")
raise SystemExit(1 if FAILED else 0)
