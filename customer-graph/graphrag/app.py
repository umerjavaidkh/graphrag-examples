"""Browser chat UI for the Retail Analytics GraphRAG agent.

A clean Streamlit front-end over the same Semantic Kernel agent used by
`cli_agent.py`. Run it locally with:

    streamlit run app.py

or via Docker:

    docker compose up -d web      # then open http://localhost:8501
"""

import asyncio
import logging
import os

import streamlit as st
from dotenv import load_dotenv
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.open_ai_prompt_execution_settings import (
    OpenAIChatPromptExecutionSettings,
)
from semantic_kernel.contents.chat_history import ChatHistory

from retail_plugin import RetailPlugin
from retail_service import RetailService

logging.basicConfig(level=logging.INFO)

# Compose injects these as real env vars; the local .env is a fallback so the
# app also works when run manually from the graphrag/ folder.
load_dotenv("../.env")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
SERVICE_ID = "retail_search"

SAMPLE_QUESTIONS = [
    "What are some good sweaters for spring? Nothing too warm please!",
    "Which suppliers have the highest number of returns (i.e., credit notes)?",
    "Can you run a customer segmentation analysis?",
    "What are the most common product types purchased for each segment?",
    "How many customers, orders, and articles are in the database?",
    "For the largest customer group, make a creative spring promotional campaign highlighting recommended products. Draft it as an email.",
]

st.set_page_config(page_title="Retail Analytics Agent", page_icon="🛍️", layout="wide")


def get_event_loop() -> asyncio.AbstractEventLoop:
    """One persistent loop reused across reruns.

    The agent's async OpenAI/Neo4j clients bind to the loop they are first used
    on; calling asyncio.run() per message would close that loop and break the
    clients on the next turn (the bug in the original app).
    """
    if "event_loop" not in st.session_state:
        st.session_state.event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(st.session_state.event_loop)
    return st.session_state.event_loop


def build_kernel():
    """Build the kernel + settings (once per session, see get_kernel)."""
    kernel = Kernel()
    retail_service = RetailService(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    kernel.add_plugin(RetailPlugin(retail_service=retail_service), plugin_name="retail_analytics")
    kernel.add_service(
        OpenAIChatCompletion(ai_model_id="gpt-4o", api_key=OPENAI_KEY, service_id=SERVICE_ID)
    )

    settings: OpenAIChatPromptExecutionSettings = kernel.get_prompt_execution_settings_from_service_id(
        service_id=SERVICE_ID
    )
    settings.function_choice_behavior = FunctionChoiceBehavior.Auto(
        filters={"included_plugins": ["retail_analytics"]}
    )
    return kernel, settings


def get_kernel():
    """Cache the kernel in session state so it pairs with this session's loop.

    The kernel's async clients bind to the loop they first run on, so the
    kernel and the event loop must live together for the whole session.
    """
    if "kernel" not in st.session_state:
        with st.spinner("Connecting to the graph and agent ..."):
            st.session_state.kernel, st.session_state.settings = build_kernel()
    return st.session_state.kernel, st.session_state.settings


async def get_agent_response(kernel, settings, history: ChatHistory, user_input: str) -> str:
    history.add_user_message(user_input)
    chat_completion: OpenAIChatCompletion = kernel.get_service(type=ChatCompletionClientBase)
    result = (
        await chat_completion.get_chat_message_contents(
            chat_history=history,
            settings=settings,
            kernel=kernel,
        )
    )[0]
    history.add_message(result)
    return str(result)


# --- Session state ---------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []  # list of {"role", "content"} for display
if "chat_history" not in st.session_state:
    st.session_state.chat_history = ChatHistory()  # full kernel history

# --- Sidebar ---------------------------------------------------------------
with st.sidebar:
    st.header("🛍️ Retail Analytics Agent")
    st.caption("GraphRAG over a fashion retail knowledge graph.")

    if not OPENAI_KEY:
        st.error("OPENAI_API_KEY is not set.")
    st.markdown(f"**Neo4j:** `{NEO4J_URI or 'not set'}`")

    st.divider()
    st.subheader("Try a question")
    pending_question = None
    for i, q in enumerate(SAMPLE_QUESTIONS):
        if st.button(q, key=f"sample_{i}", use_container_width=True):
            pending_question = q

    st.divider()
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.chat_history = ChatHistory()
        st.rerun()

# --- Main chat area --------------------------------------------------------
st.title("Chat with your Retail Analytics Agent")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

typed_question = st.chat_input("Ask about products, suppliers, returns, customer segments ...")
user_question = typed_question or pending_question

if user_question:
    st.session_state.messages.append({"role": "user", "content": user_question})
    with st.chat_message("user"):
        st.markdown(user_question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking ..."):
            try:
                kernel, settings = get_kernel()
                loop = get_event_loop()
                answer = loop.run_until_complete(
                    get_agent_response(
                        kernel, settings, st.session_state.chat_history, user_question
                    )
                )
            except Exception as e:  # surface errors in the UI instead of hanging
                logging.exception("Agent error")
                answer = f"⚠️ Error: {e}"
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
