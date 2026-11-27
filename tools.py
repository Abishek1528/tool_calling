"""
tools.py - the agent's toolbox for the "Shop Stock Helper".

Every tool is plain Python and works completely offline.
They only read the shop's own data file: data/stock.csv
No internet, no API key, no paid service.

Three tools, one for each step of the job:
    low_stock(threshold)            -> READ      (look things up in our data)
    days_of_stock(item, daily_sales)-> COMPUTE   (work something out)
    draft_reorder_note(item, quantity)-> DRAFT   (write it up for a person)

Design rules followed here:
  * Tools never change anything. They only read and produce text.
  * Every tool returns a JSON-friendly dict:
        {"ok": True,  "result": ...}
        {"ok": False, "error":  "..."}   <- honest failure, never a guess
"""

from __future__ import annotations

import csv
import os

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "stock.csv")


# --------------------------------------------------------------------------- #
# data loading
# --------------------------------------------------------------------------- #
def _load() -> list[dict]:
    """Read data/stock.csv into a list of dicts. Raises if the file is missing."""
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Data file not found: {DATA_PATH}")

    rows: list[dict] = []
    with open(DATA_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = (r.get("item") or "").strip()
            if not name:
                continue
            try:
                qty = int(str(r.get("quantity", "")).strip())
            except ValueError:
                continue
            rows.append(
                {
                    "item": name,
                    "quantity": qty,
                    "supplier": (r.get("supplier") or "").strip(),
                }
            )
    return rows


def _find(rows: list[dict], item: str) -> dict | None:
    """Find one row by name. Exact match (case-insensitive) first, then substring."""
    if item is None:
        return None
    needle = str(item).strip().lower()
    if not needle:
        return None

    for r in rows:
        if r["item"].lower() == needle:
            return r
    for r in rows:
        if needle in r["item"].lower() or r["item"].lower() in needle:
            return r
    return None


# --------------------------------------------------------------------------- #
# tool 1 - READ
# --------------------------------------------------------------------------- #
def low_stock(threshold=10) -> dict:
    """List items at or below `threshold` units. This is the 'look it up' step."""
    try:
        threshold = int(float(threshold))
    except (TypeError, ValueError):
        return {"ok": False, "error": f"threshold must be a whole number, got {threshold!r}"}

    rows = _load()
    low = sorted((r for r in rows if r["quantity"] <= threshold), key=lambda r: r["quantity"])

    return {
        "ok": True,
        "result": {
            "threshold": threshold,
            "count": len(low),
            "items": [
                {"item": r["item"], "quantity": r["quantity"], "supplier": r["supplier"]}
                for r in low
            ],
            "message": (
                f"No items are at or below {threshold} units."
                if not low
                else f"{len(low)} item(s) are at or below {threshold} units."
            ),
        },
    }


# --------------------------------------------------------------------------- #
# tool 2 - COMPUTE
# --------------------------------------------------------------------------- #
def days_of_stock(item, daily_sales) -> dict:
    """Estimate how many days current stock lasts at `daily_sales` units/day."""
    try:
        rows = _load()
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    match = _find(rows, item)
    if match is None:
        return {
            "ok": False,
            "error": f"No item matching {item!r} was found in the stock file.",
            "known_items": [r["item"] for r in rows],
        }

    try:
        ds = float(daily_sales)
    except (TypeError, ValueError):
        return {"ok": False, "error": f"daily_sales must be a number, got {daily_sales!r}"}

    if ds <= 0:
        return {"ok": False, "error": "daily_sales must be greater than 0."}

    days = match["quantity"] / ds
    return {
        "ok": True,
        "result": {
            "item": match["item"],
            "quantity": match["quantity"],
            "daily_sales": ds,
            "days_of_stock": round(days, 1),
            "supplier": match["supplier"],
        },
    }


# --------------------------------------------------------------------------- #
# tool 3 - DRAFT
# --------------------------------------------------------------------------- #
def draft_reorder_note(item, quantity) -> dict:
    """
    Draft a short reorder note for one item.

    This ONLY writes text for the shopkeeper to read. It never sends, orders,
    emails or saves anything - so it is an action that is always reversible.
    """
    try:
        rows = _load()
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    match = _find(rows, item)
    if match is None:
        return {
            "ok": False,
            "error": f"No item matching {item!r} was found in the stock file.",
            "known_items": [r["item"] for r in rows],
        }

    try:
        qty = int(float(quantity))
    except (TypeError, ValueError):
        return {"ok": False, "error": f"quantity must be a whole number, got {quantity!r}"}
    if qty <= 0:
        return {"ok": False, "error": "quantity must be greater than 0."}

    note = (
        "REORDER NOTE (DRAFT - not sent to anyone)\n"
        "----------------------------------------\n"
        f"Item            : {match['item']}\n"
        f"Current stock   : {match['quantity']} units\n"
        f"Reorder quantity: {qty} units\n"
        f"Supplier        : {match['supplier']}\n\n"
        f"Hi {match['supplier']},\n"
        f"Please send {qty} x {match['item']} with the next delivery.\n"
        f"Our current stock is down to {match['quantity']} units.\n\n"
        "Thanks,\n"
        "The shop"
    )

    return {
        "ok": True,
        "result": {
            "item": match["item"],
            "supplier": match["supplier"],
            "current_stock": match["quantity"],
            "quantity": qty,
            "note": note,
            "sent": False,
            "delivered": False,
        },
    }


# --------------------------------------------------------------------------- #
# registry used by the agent
# --------------------------------------------------------------------------- #
TOOL_FUNCTIONS = {
    "low_stock": low_stock,
    "days_of_stock": days_of_stock,
    "draft_reorder_note": draft_reorder_note,
}

# JSON-schema style descriptions handed to Gemini so it knows how to call them.
TOOL_SPECS = [
    {
        "name": "low_stock",
        "description": (
            "READ step. List every item in the shop's stock file whose current "
            "quantity is less than or equal to the given threshold. Call this "
            "first when the user asks what is running low / what to reorder."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "threshold": {
                    "type": "integer",
                    "description": "Quantity threshold. Items at or below it are returned. Default 10.",
                }
            },
            "required": ["threshold"],
        },
    },
    {
        "name": "days_of_stock",
        "description": (
            "COMPUTE step. Estimate how many days the current stock of ONE item "
            "will last, given an average number of units sold per day. Call this "
            "to judge how urgent a reorder is."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "item": {
                    "type": "string",
                    "description": "Item name. Must match a name in the stock file.",
                },
                "daily_sales": {
                    "type": "number",
                    "description": "Average units sold per day. Must be greater than 0.",
                },
            },
            "required": ["item", "daily_sales"],
        },
    },
    {
        "name": "draft_reorder_note",
        "description": (
            "DRAFT step. Write a short reorder note for ONE item so the shopkeeper "
            "can review it. This only produces text - it never sends, orders or "
            "emails anything, and it changes no data."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "item": {"type": "string", "description": "Item to reorder."},
                "quantity": {"type": "integer", "description": "How many units to reorder."},
            },
            "required": ["item", "quantity"],
        },
    },
]
