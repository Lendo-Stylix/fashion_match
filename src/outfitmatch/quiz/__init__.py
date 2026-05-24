"""Onboarding quiz and preference-based re-ranking (v3.1-lite Tầng 4).

MVP replaces GNN personalisation (deferred to Kien_truc_v3.1.md Phụ lục A)
with a simple onboarding quiz → PreferenceProfile → additive re-rank.

Workflow:
    answers = QuizAnswers(style=[...], occasions=[...], ...)
    profile = quiz_to_profile(answers)
    top_outfits = rerank_by_preference(qdrant_candidates, profile, top_k=5)
"""

from outfitmatch.quiz.rerank import rerank_by_preference, score_outfit_for_preference
from outfitmatch.quiz.schema import PreferenceProfile, QuizAnswers, quiz_to_profile

__all__ = [
    "QuizAnswers",
    "PreferenceProfile",
    "quiz_to_profile",
    "score_outfit_for_preference",
    "rerank_by_preference",
]
