"""Evaluation suite for the Retail Analytics GraphRAG agent.

Runs 10 questions through the same Semantic Kernel agent used by the CLI / web
UI and applies lightweight pass checks (no exception, non-empty answer, and —
where given — at least one expected keyword present). It is a smoke / regression
suite, not a strict accuracy benchmark, since LLM phrasing varies.

The questions run sequentially against one shared chat history so the
follow-up questions (e.g. "...for each segment") have the needed context.

Run it:
    cd graphrag && python eval_agent.py

or via Docker:
    docker compose run --rm agent python eval_agent.py
"""

import asyncio
import os
import sys

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

load_dotenv("../.env")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
SERVICE_ID = "retail_search"

# Each case: the question, the capability/tool it should exercise, and an
# optional list of keywords — the answer passes if at least one appears.
EVAL_SUITE = [
    {
        "id": 1,
        "capability": "Semantic vector search (search_products)",
        "question": "What are some good lightweight sweaters for spring? Nothing too warm please.",
        "expect_any": ["sweater", "knit", "jumper", "light"],
    },
    {
        "id": 2,
        "capability": "Supplier returns ranking (get_top_suppliers_by_returns)",
        "question": "Which suppliers have the highest number of returns (i.e., credit notes)?",
        "expect_any": ["supplier", "return", "credit"],
    },
    {
        "id": 3,
        "capability": "Product -> supplier swap analysis (get_supplier_order_product_info)",
        "question": "What are the top 3 most returned products for supplier 1616? Get those product codes and find other suppliers who have fewer returns for each product I can use instead.",
        "expect_any": ["1616", "supplier", "product"],
    },
    {
        "id": 4,
        "capability": "GDS community detection (create_customer_segments)",
        "question": "Can you run a customer segmentation analysis?",
        "expect_any": ["segment", "group", "community"],
    },
    {
        "id": 5,
        "capability": "Follow-up reasoning over segments",
        "question": "What are the most common product types purchased for each segment?",
        "expect_any": ["segment", "product type", "type"],
    },
    {
        "id": 6,
        "capability": "Open-ended text-to-Cypher (answer_general_question)",
        "question": "How many customers are in the database?",
        "expect_any": ["customer"],
    },
    {
        "id": 7,
        "capability": "Open-ended text-to-Cypher (answer_general_question)",
        "question": "How many orders and articles are in the database?",
        "expect_any": ["order", "article"],
    },
    {
        "id": 8,
        "capability": "Supplier order/return stats (get_supplier_order_product_info)",
        "question": "Show me the total orders and returns for supplier 1616.",
        "expect_any": ["1616", "order", "return"],
    },
    {
        "id": 9,
        "capability": "Recommendations (recommend_products)",
        "question": "Recommend some products for customers who tend to buy sweaters.",
        "expect_any": ["product", "recommend"],
    },
    {
        "id": 10,
        "capability": "Recommendations + creative generation",
        "question": "For the largest customer segment, draft a short creative spring promotional email highlighting recommended products.",
        "expect_any": ["spring", "email", "subject", "dear", "hello"],
    },
]


def build_agent():
    kernel = Kernel()
    retail_service = RetailService(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    kernel.add_plugin(RetailPlugin(retail_service=retail_service), plugin_name="retail_analysis")
    kernel.add_service(
        OpenAIChatCompletion(ai_model_id="gpt-4o-mini", api_key=OPENAI_KEY, service_id=SERVICE_ID)
    )
    settings: OpenAIChatPromptExecutionSettings = kernel.get_prompt_execution_settings_from_service_id(
        service_id=SERVICE_ID
    )
    settings.function_choice_behavior = FunctionChoiceBehavior.Auto(
        filters={"included_plugins": ["retail_analysis"]}
    )
    return kernel, settings


# Phrases that signal the agent could not actually answer (tool error, empty
# graph, or a refusal). These must FAIL even though the text is non-empty —
# otherwise a "sorry, I couldn't retrieve that" reply would pass on keywords.
FAILURE_MARKERS = [
    "unable to",
    "i'm unable",
    "wasn't able",
    "was not able",
    "couldn't",
    "could not",
    "can't retrieve",
    "cannot currently",
    "no data",
    "no information",
    "there are 0",
    "0 customers",
    "0 orders",
    "0 articles",
    "error while",
    "an error occurred",
    "failed after",
    "traceback",
]


def grade(answer: str, expect_any) -> tuple[bool, str]:
    text = (answer or "").strip()
    if not text:
        return False, "empty answer"
    low = text.lower()
    if low.startswith("error"):
        return False, "agent error"
    for marker in FAILURE_MARKERS:
        if marker in low:
            return False, f"failure phrase: '{marker}'"
    if expect_any and not any(k.lower() in low for k in expect_any):
        return False, f"missing any of {expect_any}"
    return True, "ok"


async def run_eval() -> int:
    kernel, settings = build_agent()
    history = ChatHistory()
    chat_completion: OpenAIChatCompletion = kernel.get_service(type=ChatCompletionClientBase)

    results = []
    for case in EVAL_SUITE:
        print(f"\n[{case['id']:>2}] {case['capability']}")
        print(f"     Q: {case['question']}")
        history.add_user_message(case["question"])
        try:
            result = (
                await chat_completion.get_chat_message_contents(
                    chat_history=history, settings=settings, kernel=kernel
                )
            )[0]
            answer = str(result)
            history.add_message(result)
        except Exception as e:  # noqa: BLE001 - capture so the suite keeps going
            answer = f"Error: {e}"

        passed, reason = grade(answer, case.get("expect_any"))
        snippet = answer.replace("\n", " ")[:160]
        print(f"     A: {snippet}{'...' if len(answer) > 160 else ''}")
        print(f"     -> {'PASS' if passed else 'FAIL'} ({reason})")
        results.append((case["id"], case["capability"], passed, reason))

    passed_count = sum(1 for _, _, p, _ in results if p)
    print("\n" + "=" * 70)
    print(f"RESULT: {passed_count}/{len(results)} passed")
    print("=" * 70)
    for cid, cap, p, reason in results:
        print(f"  [{cid:>2}] {'PASS' if p else 'FAIL'}  {cap}" + ("" if p else f"  ({reason})"))

    return 0 if passed_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run_eval()))
