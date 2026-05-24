"""Gradio demo UI (Sprint 8).

Skeleton placeholder so `make demo` succeeds before the real UI is wired up.
Sprint 8 will replace this with the full quiz onboarding + chat + outfit display flow.
"""

from __future__ import annotations

import gradio as gr


def _placeholder(message: str) -> str:
    return f"OutfitMatch demo chưa được triển khai — sẽ có ở Sprint 8.\n\nBạn vừa gõ: {message}"


def build_app() -> gr.Blocks:
    with gr.Blocks(title="OutfitMatch — v3.1-lite (Sprint 8 trở đi)") as app:
        gr.Markdown("# OutfitMatch — AI Stylist v3.1-lite")
        gr.Markdown(
            "Demo placeholder. Xem `Kien_truc_v3.1.md` cho pipeline đầy đủ. "
            "Sprint 8 sẽ build Quiz onboarding + Chat + Outfit display."
        )
        msg = gr.Textbox(label="Thử gõ một yêu cầu…")
        out = gr.Textbox(label="Phản hồi", interactive=False)
        msg.submit(fn=_placeholder, inputs=msg, outputs=out)
    return app


if __name__ == "__main__":
    build_app().launch()
