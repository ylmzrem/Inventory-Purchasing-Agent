from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.tools.purchasing_tools import Toolset
from .prompts import build_system_prompt
from .state import AgentState

load_dotenv(override=True)

MAX_AGENT_STEPS = 8
MAX_API_RETRIES = 5

DEFAULT_GROQ_MODELS = [
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
]

TOOL_DECLARATIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search catalog products by SKU or product name keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "SKU code or product name keyword."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_inventory_and_demand",
            "description": "Retrieve physical, allocated, and available stock, snapshot timestamp, open orders, and demand rows for a SKU.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "Exact product SKU."}
                },
                "required": ["sku"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_net_requirements",
            "description": "Run day-by-day inventory projection up to horizon_end (YYYY-MM-DD) to find need_date and net_requirement.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "Exact product SKU."},
                    "horizon_end": {"type": "string", "description": "End date of planning horizon in YYYY-MM-DD format."},
                },
                "required": ["sku", "horizon_end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_suppliers",
            "description": "Evaluate suppliers on total TRY cost, delivery deadline, and budget, and create a requisition draft.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "net_requirement": {"type": "integer"},
                    "need_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "available_stock": {"type": "integer"},
                    "budget_try": {
                        "anyOf": [{"type": "number"}, {"type": "null"}],
                        "description": "Max budget in TRY if user stated one; omit or null otherwise.",
                    },
                    "supplier_override": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "Specific supplier_id if user requested one; omit or null otherwise.",
                    },
                },
                "required": ["sku", "net_requirement", "need_date", "available_stock"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_requisition",
            "description": "Approve or reject the current requisition draft. Only call with 'approve' after explicit user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["approve", "reject"]}
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_clarification",
            "description": "Call ONLY when the user omitted the date, gave an ambiguous unit (pieces vs boxes), gave a completely generic product name without a model number, or gave an unknown product code (use status='not_found').",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["clarification", "not_found"],
                        "description": "Use 'not_found' if the requested SKU/product does not exist in the catalog; otherwise 'clarification'.",
                    },
                    "topics": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["product", "quantity", "unit", "date", "budget"]},
                    },
                },
                "required": ["status", "topics"],
            },
        },
    },
]


class PurchasingAgent:
    def __init__(self, data: dict[str, Any], as_of: str) -> None:
        self.state = AgentState(as_of=as_of)
        self.tools = Toolset(data=data, as_of=as_of, state=self.state)
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": build_system_prompt(as_of)}
        ]
        self._init_llm_client()

    def _init_llm_client(self) -> None:
        groq_key = os.getenv("GROQ_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        if groq_key:
            self.provider = "groq"
            self.client = OpenAI(
                api_key=groq_key,
                base_url="https://api.groq.com/openai/v1",
            )
            env_model = os.getenv("GROQ_MODEL")
            if env_model and env_model not in DEFAULT_GROQ_MODELS:
                self.models = [env_model] + DEFAULT_GROQ_MODELS
            else:
                self.models = list(DEFAULT_GROQ_MODELS)
            self.model_idx = 0
        elif openai_key:
            self.provider = "openai"
            self.client = OpenAI(api_key=openai_key)
            self.models = [os.getenv("OPENAI_MODEL", "gpt-4o-mini")]
            self.model_idx = 0
        else:
            raise RuntimeError("Missing API key: set GROQ_API_KEY or OPENAI_API_KEY in .env")

    def _update_usage(self, usage: Any) -> None:
        if not usage:
            return
        in_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
        out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
        self.state.input_tokens += in_tok
        self.state.output_tokens += out_tok
        self.state.cost_usd += (in_tok * 0.10 + out_tok * 0.30) / 1_000_000.0

    def _dispatch_tool(self, name: str, args: dict[str, Any]) -> str:
        try:
            if name == "search_products":
                res = self.tools.search_products(query=args["query"])
            elif name == "get_inventory_and_demand":
                res = self.tools.get_inventory_and_demand(sku=args["sku"])
            elif name == "calculate_net_requirements":
                res = self.tools.calculate_net_requirements(
                    sku=args["sku"],
                    horizon_end=args["horizon_end"],
                )
            elif name == "compare_suppliers":
                res = self.tools.compare_suppliers(
                    sku=args["sku"],
                    net_requirement=int(args["net_requirement"]),
                    need_date=args["need_date"],
                    available_stock=int(args["available_stock"]),
                    budget_try=args.get("budget_try"),
                    supplier_override=args.get("supplier_override"),
                )
            elif name == "manage_requisition":
                res = self.tools.manage_requisition(action=args["action"])
            elif name == "record_clarification":
                status = args.get("status", "clarification")
                topics = [t for t in args.get("topics", []) if t in {"product", "quantity", "unit", "date", "budget"}]
                self.state.outcome = "not_found" if status == "not_found" else "clarification"
                for t in topics:
                    if t not in self.state.clarify_topics:
                        self.state.clarify_topics.append(t)
                res = {"status": self.state.outcome, "topics": self.state.clarify_topics}
            else:
                res = {"status": "error", "message": f"Unknown tool: {name}"}
        except Exception as exc:  # noqa: BLE001
            res = {"status": "tool_exception", "error": f"{type(exc).__name__}: {exc}"}
        return json.dumps(res, ensure_ascii=False, default=str)

    def _call_llm_with_retry(self) -> Any:
        last_err: Exception | None = None
        for attempt in range(MAX_API_RETRIES + 1):
            current_model = self.models[self.model_idx % len(self.models)]
            try:
                return self.client.chat.completions.create(
                    model=current_model,
                    messages=self.messages,
                    tools=TOOL_DECLARATIONS,
                    tool_choice="auto",
                    temperature=0.0,
                )
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                err_str = str(exc)
                if "429" in err_str or "rate_limit" in err_str.lower():
                    if "tokens per day" in err_str.lower() or "tpd" in err_str.lower():
                        self.model_idx += 1
                        continue
                    match = re.search(r"try again in ([0-9.]+)s", err_str, re.IGNORECASE)
                    wait_s = float(match.group(1)) + 0.5 if match else min(12.0, 2.0 * (attempt + 1))
                    if wait_s > 15.0 and len(self.models) > 1:
                        self.model_idx += 1
                    else:
                        time.sleep(wait_s)
                else:
                    time.sleep(1.0)
        raise RuntimeError(f"LLM API failed after retries: {last_err}")

    def send(self, message: str) -> str:
        self.state.clarify_topics = []
        self.messages.append({"role": "user", "content": message})

        for _step in range(MAX_AGENT_STEPS):
            response = self._call_llm_with_retry()
            self._update_usage(getattr(response, "usage", None))
            choice = response.choices[0].message

            msg_dict: dict[str, Any] = {"role": "assistant", "content": choice.content or ""}
            if choice.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in choice.tool_calls
                ]
            self.messages.append(msg_dict)

            if not choice.tool_calls:
                if self.state.outcome is None and "?" in (choice.content or ""):
                    self.state.outcome = "clarification"
                return choice.content or ""

            for tc in choice.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    fn_args = {}
                tool_output = self._dispatch_tool(fn_name, fn_args)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_output,
                })

        return "Maximum reasoning steps reached. Please refine or confirm your request."

    def get_state(self) -> dict[str, Any]:
        return self.state.to_dict()


def create_agent(data: dict[str, Any], as_of: str) -> PurchasingAgent:
    return PurchasingAgent(data=data, as_of=as_of)