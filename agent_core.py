"""
agent_core.py - the brain of the "Shop Stock Helper".

It runs a small function-calling loop against Google Gemini:

    user question
        -> Gemini decides which tool to call
        -> we run the plain-Python tool (tools.py)
        -> we feed the result back to Gemini
        -> repeat until Gemini stops calling tools
        -> final written answer

We record EVERY step so the app can show them to the visitor.

Honesty + safety are baked into the system instruction:
  * stay inside the one job,
  * never invent stock numbers,
  * say so when something is out of scope or a tool finds nothing,
  * only ever DRAFT text - no irreversible action.
"""

from __future__ import annotations

import google.generativeai as genai

from tools import TOOL_FUNCTIONS, TOOL_SPECS

# --------------------------------------------------------------------------- #
# configuration
# --------------------------------------------------------------------------- #
# The visitor pastes their OWN key in the app sidebar; we only pass it through.
MODEL_OPTIONS = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"]
DEFAULT_MODEL = MODEL_OPTIONS[0]
MAX_STEPS = 6  # safety cap: the agent can never loop forever

SYSTEM_INSTRUCTION = """\
You are "Shop Stock Helper", an assistant for one small neighbourhood shop.

YOUR ONE JOB: help the shopkeeper decide WHAT to reorder and HOW URGENT it is,
using ONLY the shop's own stock file.

You have exactly three tools:
  1. low_stock(threshold)               - READ. Find items at or below a quantity.
  2. days_of_stock(item, daily_sales)   - COMPUTE. How many days the stock lasts.
  3. draft_reorder_note(item, quantity) - DRAFT. Write a reorder note for review.

HOW TO WORK
- Plan the smallest useful sequence of tool calls, then stop. A typical job is
  low_stock -> days_of_stock -> draft_reorder_note.
- Use the tools to get real numbers. NEVER invent quantities, suppliers or item
  names. If you are not sure, call a tool.
- When you already have enough information to answer, STOP calling tools and
  write the answer.

BE HONEST
- If the question is outside your job (prices, weather, news, tax, anything that
  is not about this shop's stock and reordering), say plainly that it is outside
  your job and stop. Do not guess.
- If a tool returns ok=false, or returns no matching items, tell the user exactly
  that. Never fill the gap with a made-up answer.
- If the user names an item that is not in the file, say it was not found and, if
  helpful, mention that you can list what IS in stock.

YOU CANNOT TAKE REAL ACTIONS
- The only "writing" tool is draft_reorder_note, and it ONLY produces draft text
  for a human to review. Nothing is ever sent, ordered, emailed or saved.
- Never say that you placed an order, contacted a supplier, or changed any data.
- If asked to actually order / email / send something, explain that you can only
  draft a note, and do that instead.

STYLE
- Be short and clear. Use plain language, small bullet lists, and the real numbers
  from the tools. Group your answer around: what is low, how urgent, and the
  suggested note.
"""


# --------------------------------------------------------------------------- #
# build the Gemini tool declarations from tools.py specs
# --------------------------------------------------------------------------- #
_TYPE_MAP = {
    "string": genai.protos.Type.STRING,
    "integer": genai.protos.Type.INTEGER,
    "number": genai.protos.Type.NUMBER,
    "boolean": genai.protos.Type.BOOLEAN,
    "object": genai.protos.Type.OBJECT,
}


def _schema(param: dict) -> "genai.protos.Schema":
    ptype = _TYPE_MAP[param["type"]]
    kwargs = {"type": ptype, "description": param.get("description", "")}
    if ptype == genai.protos.Type.NUMBER:
        kwargs["format"] = "float"
    return genai.protos.Schema(**kwargs)


def _build_tool() -> "genai.protos.Tool":
    declarations = []
    for spec in TOOL_SPECS:
        props = {name: _schema(p) for name, p in spec["parameters"]["properties"].items()}
        declarations.append(
            genai.protos.FunctionDeclaration(
                name=spec["name"],
                description=spec["description"],
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties=props,
                    required=spec["parameters"].get("required", []),
                ),
            )
        )
    return genai.protos.Tool(function_declarations=declarations)


# --------------------------------------------------------------------------- #
# the loop
# --------------------------------------------------------------------------- #
def _iter_function_calls(response) -> list:
    calls = []
    try:
        parts = response.candidates[0].content.parts
    except (AttributeError, IndexError):
        return calls
    for part in parts:
        fc = getattr(part, "function_call", None)
        if fc is not None and getattr(fc, "name", ""):
            calls.append(fc)
    return calls


def _plain_args(args) -> dict:
    """Convert the proto args map into plain Python values."""
    try:
        return {k: v for k, v in dict(args).items()}
    except (TypeError, ValueError):
        return {}


def run_agent(user_message: str, api_key: str, model_name: str = DEFAULT_MODEL, max_steps: int = MAX_STEPS):
    """
    Run one agent turn.

    Returns (final_text, steps) where steps is a list of dicts:
        {"type": "tool",   "name": ..., "args": {...}, "result": {...}}
        {"type": "notice", "text": ...}
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=model_name,
        tools=[_build_tool()],
        system_instruction=SYSTEM_INSTRUCTION,
    )
    chat = model.start_chat(history=[])
    steps: list[dict] = []

    response = chat.send_message(user_message)

    for _ in range(max_steps):
        calls = _iter_function_calls(response)
        if not calls:
            break  # the agent has enough information -> stop

        response_parts = []
        for call in calls:
            name = call.name
            args = _plain_args(call.args)

            fn = TOOL_FUNCTIONS.get(name)
            if fn is None:
                result = {"ok": False, "error": f"Unknown tool {name!r}."}
            else:
                try:
                    result = fn(**args)
                except TypeError as e:
                    result = {"ok": False, "error": f"Bad arguments for {name}: {e}"}
                except Exception as e:  # noqa: BLE001 - tool must never crash the app
                    result = {"ok": False, "error": f"{type(e).__name__}: {e}"}

            steps.append({"type": "tool", "name": name, "args": args, "result": result})
            response_parts.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=name, response={"result": result}
                    )
                )
            )

        response = chat.send_message(response_parts)
    else:
        steps.append(
            {"type": "notice", "text": f"Stopped after the safe limit of {max_steps} steps."}
        )

    try:
        final_text = (response.text or "").strip()
    except Exception:  # noqa: BLE001 - some responses carry no text
        final_text = ""

    if not final_text:
        final_text = (
            "I could not produce an answer from the data I have. "
            "Please rephrase, or ask what is running low in the shop."
        )

    return final_text, steps
