"""
app.py - the Streamlit app for the "Shop Stock Helper" agent.

Special rule (the starter follows it too): every visitor pastes their OWN free
Gemini key in the sidebar. Nobody uses the owner's quota and no key is shared or
stored anywhere in the code.

Run locally:   streamlit run app.py
"""

import streamlit as st

from agent_core import DEFAULT_MODEL, MODEL_OPTIONS, run_agent

st.set_page_config(page_title="Shop Stock Helper", page_icon="📦", layout="centered")

# --------------------------------------------------------------------------- #
# sidebar: the visitor's own key
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("🔑 Your Gemini API key")
    api_key = st.text_input(
        "Paste your own Google Gemini key",
        type="password",
        placeholder="AIza...",
        help="Get a free key at https://aistudio.google.com/app/apikey",
    )
    model_name = st.selectbox("Model", MODEL_OPTIONS, index=MODEL_OPTIONS.index(DEFAULT_MODEL))
    st.caption(
        "Your key is used only for this session to call Google on your behalf. "
        "It is never stored on the server and never shared."
    )
    st.divider()
    st.markdown("**What this agent does**")
    st.markdown(
        "- `low_stock(threshold)` — reads `data/stock.csv`, finds items at or below a quantity\n"
        "- `days_of_stock(item, daily_sales)` — works out how many days the stock lasts\n"
        "- `draft_reorder_note(item, quantity)` — drafts a note for you to review (never sent)"
    )
    st.caption("All tools run offline on the shop's own data file. No other service is used.")

# --------------------------------------------------------------------------- #
# header
# --------------------------------------------------------------------------- #
st.title("📦 Shop Stock Helper")
st.caption(
    "An agent for one clear job: **decide what to reorder and how urgent it is**, "
    "then draft the note. It shows every step it takes."
)

EXAMPLES = [
    "What is running low in the shop?",
    "Which low-stock items will run out within a week if we sell about 2 a day?",
    "Draft a reorder note for the item with the least stock.",
    "How many days of Toor Dal do we have at 1.5 per day?",
    "What is the price of Basmati Rice?",  # deliberately out of scope
    "Order 50 packets of Instant Noodles and email the supplier now.",  # irreversible
]

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending" not in st.session_state:
    st.session_state.pending = None

st.markdown("###### Try one of these")
cols = st.columns(2)
for i, example in enumerate(EXAMPLES):
    if cols[i % 2].button(example, use_container_width=True, key=f"ex{i}"):
        st.session_state.pending = example


# --------------------------------------------------------------------------- #
# rendering helpers
# --------------------------------------------------------------------------- #
def render_assistant(steps, answer):
    if not steps:
        st.caption("No tools were needed for this reply.")
    for i, step in enumerate(steps, 1):
        if step["type"] == "tool":
            ok = step["result"].get("ok", True) if isinstance(step["result"], dict) else True
            icon = "🔧" if ok else "⚠️"
            with st.expander(f"{icon} Step {i} — `{step['name']}(...)`", expanded=True):
                st.markdown("**Input given to the tool**")
                st.json(step["args"])
                st.markdown("**What the tool returned**")
                st.json(step["result"])
        elif step["type"] == "notice":
            st.warning(step["text"])
    st.markdown(answer)


def render_turn(msg):
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            render_assistant(msg.get("steps", []), msg["content"])


for message in st.session_state.messages:
    render_turn(message)


# --------------------------------------------------------------------------- #
# input + agent call
# --------------------------------------------------------------------------- #
typed = st.chat_input("Ask about shop stock or reordering...")
prompt = st.session_state.pending or typed
st.session_state.pending = None

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        if not api_key:
            answer = "Please paste your own Gemini API key in the sidebar to run the agent."
            st.info(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer, "steps": []})
        else:
            try:
                with st.spinner("Agent is working through its steps..."):
                    answer, steps = run_agent(prompt, api_key, model_name=model_name)
            except Exception as e:  # noqa: BLE001 - show a friendly error, never crash
                text = str(e)
                if "API_KEY" in text.upper() or "API key" in text or "permission" in text.lower():
                    answer = (
                        "The Gemini API rejected the key. Please check that you pasted a valid "
                        "free key from https://aistudio.google.com/app/apikey"
                    )
                elif "quota" in text.lower() or "429" in text:
                    answer = "Your Gemini key has hit a rate/quota limit. Please wait a moment and try again."
                else:
                    answer = f"Something went wrong while running the agent: {text}"
                steps = []
                st.error(answer)
            else:
                render_assistant(steps, answer)

            st.session_state.messages.append(
                {"role": "assistant", "content": answer, "steps": steps}
            )
