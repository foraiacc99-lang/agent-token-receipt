"""Optional, zero-dependency local stdio MCP server for Agent Token Receipt.

Exposes read-only session discovery, structured token/cost usage breakdowns,
and 80mm thermal PDF receipt generation over JSON-RPC 2.0 stdio transport
without adding external runtime dependencies. MCP remains completely optional;
standard CLI commands and agent skills work independently.
"""

from pathlib import Path
import json
import sys
from typing import Any, Callable, Dict, IO, List, Optional

from collector.registry import CollectorRegistry
from core.aggregator import UsageAggregator
from generator.pdf import ReceiptPDFGenerator
from pricing.calculator import CostCalculator

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {
    "name": "agent-token-receipt",
    "version": "0.2.0",
}


def _tool_definitions() -> List[Dict[str, Any]]:
    """Return MCP tool definitions advertised on tools/list."""
    return [
        {
            "name": "list_agent_sessions",
            "description": (
                "Discover local coding-agent sessions (Antigravity, Claude Code, Codex, "
                "Gemini CLI, Cursor metadata) read-only without extracting prompt text."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_path": {
                        "type": "string",
                        "description": "Optional project directory filter.",
                    },
                    "agents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of agent keys (e.g. claude_code, codex, antigravity).",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 20,
                    },
                },
            },
        },
        {
            "name": "get_agent_usage",
            "description": (
                "Collect and aggregate verifiable local token counts and estimated API costs "
                "for a workspace or specific session across selected agents."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_path": {"type": "string"},
                    "session_id": {"type": "string"},
                    "agents": {"type": "array", "items": {"type": "string"}},
                    "latest_per_agent": {"type": "boolean", "default": False},
                },
            },
        },
        {
            "name": "generate_agent_receipt",
            "description": (
                "Generate an 80mm thermal PDF usage & cost receipt using the Python accounting engine."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_path": {"type": "string"},
                    "session_id": {"type": "string"},
                    "agents": {"type": "array", "items": {"type": "string"}},
                    "output_dir": {"type": "string", "default": "receipts"},
                    "latest_per_agent": {"type": "boolean", "default": False},
                },
            },
        },
    ]


class LocalMCPServer:
    """In-process + stdio JSON-RPC 2.0 handler backed by CollectorRegistry and CostCalculator."""

    def __init__(
        self,
        collector_registry: Optional[CollectorRegistry] = None,
        calculator: Optional[CostCalculator] = None,
    ):
        self.collector_registry = collector_registry or CollectorRegistry()
        self.calculator = calculator or CostCalculator()
        self.aggregator = UsageAggregator(self.calculator)

    def _serialize_receipt_summary(self, receipt) -> Dict[str, Any]:
        return {
            "receipt_id": receipt.metadata.receipt_id,
            "session_id": receipt.metadata.session_id,
            "session_title": receipt.metadata.session_title,
            "total_turns": receipt.total_turns,
            "total_input_tokens": receipt.total_input_tokens,
            "total_output_tokens": receipt.total_output_tokens,
            "total_cache_read_tokens": receipt.total_cache_read_tokens,
            "input_plus_output_tokens": receipt.total_tokens,
            "estimated_api_cost_usd": (
                str(receipt.estimated_api_cost_usd)
                if receipt.estimated_api_cost_usd is not None
                else None
            ),
            "actual_billed_amount_usd": (
                str(receipt.actual_billed_amount_usd)
                if receipt.actual_billed_amount_usd is not None
                else None
            ),
            "pricing_status": receipt.pricing_status,
            "pricing_notes": receipt.pricing_notes,
            "models": [
                {
                    "agent": s.agent,
                    "provider": s.provider,
                    "model_display_name": s.model_display_name,
                    "model_id": s.model_id,
                    "turn_count": s.turn_count,
                    "input_tokens": s.input_tokens,
                    "output_tokens": s.output_tokens,
                    "cache_read_tokens": s.cache_read_tokens,
                    "cache_write_tokens": s.cache_write_tokens,
                    "reasoning_tokens": s.reasoning_tokens,
                    "estimated_api_cost_usd": (
                        str(s.estimated_api_cost_usd)
                        if s.estimated_api_cost_usd is not None
                        else None
                    ),
                    "pricing_status": s.pricing_status,
                    "pricing_notes": s.pricing_notes,
                }
                for s in receipt.model_summaries
            ],
            "unavailable_agents": list(receipt.unavailable_agents),
        }

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args = arguments or {}

        if name == "list_agent_sessions":
            limit = max(1, min(100, int(args.get("limit") or 20)))
            sessions = self.collector_registry.discover_all_sessions(
                workspace_path=args.get("workspace_path"),
                agents=args.get("agents"),
            )[:limit]
            return {
                "count": len(sessions),
                "sessions": [
                    {
                        "agent_key": key,
                        "agent": s.agent,
                        "provider": s.provider,
                        "session_id": s.session_id,
                        "title": s.title,
                        "workspace_path": s.workspace_path,
                        "turn_count": s.turn_count,
                        "last_active_time": (
                            s.last_active_time.isoformat() if s.last_active_time else None
                        ),
                    }
                    for key, s in sessions
                ],
            }

        if name in ("get_agent_usage", "generate_agent_receipt"):
            ws_path = args.get("workspace_path")
            session_id = args.get("session_id")
            agents = args.get("agents")
            latest_per_agent = bool(args.get("latest_per_agent", False))

            coll_res = self.collector_registry.collect_workspace_usage(
                workspace_path=ws_path,
                agents=agents,
                session_id=session_id,
                latest_per_agent=latest_per_agent,
            )

            receipt_sid = session_id or (
                f"workspace-{Path(ws_path).name}" if ws_path else "multi-agent-billing"
            )
            receipt_title = (
                f"Workspace Billing ({Path(ws_path).name})"
                if ws_path
                else "Multi-Agent Billing Receipt"
            )
            receipt = self.aggregator.build_receipt(
                records=coll_res.records,
                session_id=receipt_sid,
                session_title=receipt_title,
                unavailable_agents=coll_res.unavailable_agents,
            )
            payload = self._serialize_receipt_summary(receipt)

            if name == "generate_agent_receipt":
                if not coll_res.records and not coll_res.unavailable_agents:
                    payload["pdf_path"] = None
                    payload["generated"] = False
                    payload["message"] = "No verifiable usage records or active unavailable platforms matched."
                else:
                    out_dir = Path(args.get("output_dir") or "receipts")
                    generator = ReceiptPDFGenerator(output_dir=out_dir)
                    pdf_path = generator.generate(receipt)
                    payload["pdf_path"] = str(pdf_path.resolve())
                    payload["generated"] = True

            return payload

        raise KeyError(f"Unknown MCP tool '{name}'")

    def handle_request(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process one decoded JSON-RPC 2.0 message and return a response dict (or None for notifications)."""
        msg_id = message.get("id")
        method = message.get("method")
        params = message.get("params") or {}

        if msg_id is None and isinstance(method, str) and method.startswith("notifications/"):
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                },
            }

        if method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": _tool_definitions()},
            }

        if method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments") or {}
            try:
                result_data = self.call_tool(tool_name, tool_args)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result_data, indent=2),
                            }
                        ]
                    },
                }
            except (KeyError, ValueError) as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32602, "message": str(exc)},
                }
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "isError": True,
                        "content": [{"type": "text", "text": str(exc)}],
                    },
                }

        if msg_id is None:
            return None

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method '{method}' not found"},
        }

    def serve_streams(
        self,
        stdin: Optional[IO[str]] = None,
        stdout: Optional[IO[str]] = None,
    ) -> None:
        """Serve newline-delimited JSON-RPC 2.0 MCP requests from stdin to stdout."""
        in_stream = stdin or sys.stdin
        out_stream = stdout or sys.stdout

        for raw_line in in_stream:
            line = raw_line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as exc:
                resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {exc}"},
                }
                out_stream.write(json.dumps(resp) + "\n")
                out_stream.flush()
                continue

            if not isinstance(msg, dict):
                continue
            resp = self.handle_request(msg)
            if resp is not None:
                out_stream.write(json.dumps(resp) + "\n")
                out_stream.flush()

