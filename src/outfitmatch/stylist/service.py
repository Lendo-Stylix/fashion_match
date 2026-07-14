"""Stylist conversational service (Tầng 2) — agent loop.

``StylistService`` wraps the loaded Qwen3-VL-8B model + graph KB into a
conversational agent that can emit SSE events for the Next.js frontend.

The agent loop (sprint v3.1):
  1. Build messages from system prompt + chat history + user input.
  2. Generate response; detect ``<tool_call>search_outfits(...)</tool_call>``.
  3. If a tool call is present and valid, execute it against the graph KB.
  4. Inject the tool result back into context and generate a final VN
     explanation with real outfit IDs.
  5. Run hallucination guards (``validate_response`` + ``validate_sizes``).
  6. Emit SSE events: ``token``, ``thinking``, ``outfit_cards``, ``done``,
     ``error``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from outfitmatch.pipeline import RecommendRequest, RecommendResult

logger = logging.getLogger(__name__)


@dataclass
class StylistService:
    """Conversational stylist backed by Qwen3-VL and the graph KB.

    Args:
        model: Loaded Qwen3-VL model (from ``stylist.model.load_stylist_model``).
        processor: Loaded AutoProcessor.
        graph: Loaded OutfitGraph instance.
        qdrant_url: Optional Qdrant URL for seed filtering.
        max_iterations: Max tool-call/agent iterations per user turn.
        generate_fn: Optional override of the generation function (for tests).
    """

    model: Any
    processor: Any
    graph: Any
    qdrant_url: str | None = None
    max_iterations: int = 3
    generate_fn: Callable[..., str] | None = None

    _system_prompt: str = field(init=False)

    def __post_init__(self) -> None:
        from outfitmatch.stylist.model import DEFAULT_SYSTEM_PROMPT

        self._system_prompt = DEFAULT_SYSTEM_PROMPT

    @staticmethod
    def _extract_tool_call(text: str) -> dict[str, Any] | None:
        from outfitmatch.stylist.tools import parse_tool_call_text

        return parse_tool_call_text(text)

    @staticmethod
    def _validate_tool_call(payload: dict[str, Any]) -> tuple[bool, list[str]]:
        from outfitmatch.stylist.tools import validate_tool_call_payload

        return validate_tool_call_payload(payload)

    def _generate(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        if self.generate_fn is not None:
            return self.generate_fn(self.model, self.processor, messages, **kwargs)
        from outfitmatch.stylist.model import generate_stylist_response

        return generate_stylist_response(
            self.model,
            self.processor,
            user_prompt=messages[-1]["content"],
            system_prompt=messages[0]["content"],
            **kwargs,
        )

    def _tool_call_to_request(self, payload: dict[str, Any]) -> RecommendRequest:
        from outfitmatch.pipeline import RecommendRequest

        args = payload.get("arguments", {})
        return RecommendRequest(
            occasion=args.get("occasion", "cafe_hangout"),
            style=args.get("style"),
            body_shape=args.get("body_shape"),
            skin_tone=args.get("skin_tone"),
            price_max=args.get("price_max"),
            exclude_colors=list(args.get("exclude_colors") or []),
        )

    def _execute_tool_call(self, payload: dict[str, Any]) -> list[Any]:
        from outfitmatch.retrieval import search_outfits

        request = self._tool_call_to_request(payload)
        return search_outfits(
            request,
            graph=self.graph,
            qdrant_url=self.qdrant_url,
            top_n=5,
        )

    @staticmethod
    def _format_tool_result(records: list[Any]) -> str:
        lines = [
            "Kết quả tìm kiếm từ Knowledge Base:",
        ]
        for rec in records:
            lines.append(f"- {rec.outfit_id}: {rec.stylist_explanation_vi[:160]}")
            lines.append(f"  Giá: {rec.price_total_vnd:,} VND | Style: {', '.join(rec.style)}")
        return "\n".join(lines)

    @staticmethod
    def _format_outfit_cards(records: list[Any]) -> list[dict[str, Any]]:
        cards = []
        for rec in records:
            items = [
                {
                    "item_id": it.item_id,
                    "category": it.category,
                    "title_vi": it.store.get("title_vi", ""),
                    "price_vnd": int(it.store.get("price_vnd") or 0),
                    "store_name": it.store.get("store_name", ""),
                    "product_url": it.store.get("product_url", ""),
                    "image_path": it.image_path,
                }
                for it in rec.items
            ]
            cards.append(
                {
                    "outfit_id": rec.outfit_id,
                    "explanation_vi": rec.stylist_explanation_vi,
                    "price_total_vnd": rec.price_total_vnd,
                    "price_tier": rec.price_tier,
                    "style": rec.style,
                    "occasion": rec.occasion,
                    "color_palette": rec.color_palette,
                    "items": items,
                    "compatibility_score": rec.compatibility_score,
                }
            )
        return cards

    def _run_validation(
        self,
        response: str,
        records: list[Any],
        height_cm: int | None,
        weight_kg: int | None,
    ) -> tuple[bool, list[str]]:
        from outfitmatch.stylist.validation import validate_response, validate_sizes

        valid_ids = {rec.outfit_id for rec in records}
        ok, bad_ids = validate_response(response, valid_ids)
        errors: list[str] = []
        if not ok:
            errors.append(f"outfit_id không tồn tại: {', '.join(bad_ids)}")

        if height_cm is not None and weight_kg is not None:
            sizes: set[str] = set()
            for rec in records:
                for it in rec.items:
                    available = it.store.get("sizes")
                    if available:
                        sizes.update(str(s).upper() for s in available)
            if sizes:
                ok2, bad2 = validate_sizes(response, sizes)
                if not ok2:
                    errors.append(f"size không tồn tại: {', '.join(bad2)}")

        return len(errors) == 0, errors

    def chat_stream(
        self,
        user_message: str,
        *,
        history: list[dict[str, str]] | None = None,
        quiz_answers: Any | None = None,
        height_cm: int | None = None,
        weight_kg: int | None = None,
        max_new_tokens: int = 512,
    ):
        """Yield SSE event dicts for one conversational turn.

        Event types: ``thinking``, ``token``, ``outfit_cards``, ``done``, ``error``.
        """
        from outfitmatch.stylist.validation import validate_response

        messages: list[dict[str, str]] = [{"role": "system", "content": self._system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        thinking_text = "Phân tích yêu cầu..."
        yield {"type": "thinking", "data": thinking_text}

        # Pass 1: parse intent / tool call
        response = self._generate(messages, max_new_tokens=max_new_tokens)
        yield {"type": "token", "data": response}

        payload = self._extract_tool_call(response)
        if payload is not None:
            ok, errors = self._validate_tool_call(payload)
            if not ok:
                yield {
                    "type": "error",
                    "data": f"tool_call không hợp lệ: {errors[0]}"
                    if errors
                    else "tool_call không hợp lệ",
                }
                return

            try:
                records = self._execute_tool_call(payload)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Tool execution failed")
                yield {"type": "error", "data": f"Lỗi truy vấn KB: {exc}"}
                return

            tool_result = self._format_tool_result(records)
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "tool", "content": tool_result})

            final_response = self._generate(messages, max_new_tokens=max_new_tokens)
            yield {"type": "token", "data": final_response}

            # Validation
            valid, v_errors = self._run_validation(final_response, records, height_cm, weight_kg)
            if not valid:
                yield {"type": "error", "data": "; ".join(v_errors)}
                return

            cards = self._format_outfit_cards(records)
            yield {"type": "outfit_cards", "data": cards}
        else:
            # No tool call: validate that we did not hallucinate IDs
            valid, _ = validate_response(response, set())
            if not valid:
                yield {"type": "error", "data": "Phát hiện outfit_id không tồn tại trong phản hồi."}
                return

        yield {"type": "done"}

    def recommend_from_structured(self, request: RecommendRequest) -> RecommendResult:
        """Run the deterministic recommendation pipeline (non-chat endpoint)."""
        from outfitmatch.pipeline import recommend_outfit

        return recommend_outfit(request, graph=self.graph, qdrant_url=self.qdrant_url)
