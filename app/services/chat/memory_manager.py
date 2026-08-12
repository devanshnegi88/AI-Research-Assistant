"""
Memory manager — decides what conversation context goes into the prompt.

Strategy: keep recent messages verbatim up to a token budget, and fold
anything older into a single rolling summary on the `Conversation` row.
Re-summarizing costs one extra LLM call, so it only happens once enough
new messages have aged past the verbatim window since the last summary —
not on every single turn.

Token counts are a `len(text) // 4` heuristic — see config.py for why
there's no exact tokenizer here. It's consistently applied (same
approximation for budgeting and for triggering re-summarization), so it
degrades gracefully rather than being precise.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.models.conversation import Conversation, Message
from app.models.enums import MessageRole
from app.services.rag.llm_client import LLMClient

_CHARS_PER_TOKEN = 4  # heuristic — see module docstring

_SUMMARIZATION_SYSTEM_PROMPT = (
    "You are condensing a conversation history into a concise running "
    "summary for an AI assistant's memory. Preserve concrete facts, "
    "decisions, and any specific entities (names, numbers, documents) "
    "mentioned. Omit small talk. Write it as plain prose, not a list. "
    "Keep it under {max_tokens} tokens."
)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


@dataclass
class ConversationContext:
    """What memory_manager assembled for this turn's prompt."""

    summary: str | None
    recent_messages: list[Message]


class MemoryManager:
    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    def select_recent_within_budget(self, messages: list[Message]) -> list[Message]:
        """Walk backward from the most recent message, keeping whole turns
        until the token budget is spent — always keeping at least
        `MEMORY_MIN_RECENT_TURNS` turns (a "turn" = one user + one
        assistant message) regardless of budget, so a single long message
        can't zero out all context."""
        min_messages = settings.MEMORY_MIN_RECENT_TURNS * 2
        budget = settings.MEMORY_MAX_HISTORY_TOKENS

        selected: list[Message] = []
        used_tokens = 0

        for message in reversed(messages):
            cost = message.token_estimate or estimate_tokens(message.content)
            if used_tokens + cost > budget and len(selected) >= min_messages:
                break
            selected.append(message)
            used_tokens += cost

        selected.reverse()
        return selected

    def needs_resummarization(
        self, conversation: Conversation, all_messages: list[Message]
    ) -> bool:
        unsummarized_count = len(
            [m for m in all_messages if m.turn_index > conversation.summarized_up_to_index]
        )
        # Only re-summarize once there's enough new material AND some of
        # it is about to fall outside the verbatim recent window —
        # otherwise everything's already covered verbatim, no need.
        recent = self.select_recent_within_budget(all_messages)
        oldest_recent_index = recent[0].turn_index if recent else 0
        aged_out = unsummarized_count > 0 and (
            conversation.summarized_up_to_index < oldest_recent_index - 1
        )
        return aged_out and unsummarized_count >= settings.MEMORY_SUMMARIZE_AFTER_MESSAGES

    async def resummarize(
        self, conversation: Conversation, all_messages: list[Message]
    ) -> tuple[str, int]:
        """Returns (new_summary, summarized_up_to_index). Folds everything
        up to (but not including) the current verbatim window into the
        summary, combining it with the prior summary rather than
        replaying the full history through the LLM each time."""
        recent = self.select_recent_within_budget(all_messages)
        cutoff_index = recent[0].turn_index if recent else len(all_messages)

        to_fold = [m for m in all_messages if m.turn_index < cutoff_index]
        if not to_fold:
            return conversation.summary or "", conversation.summarized_up_to_index

        transcript = "\n".join(
            f"{'User' if m.role == MessageRole.USER else 'Assistant'}: {m.content}"
            for m in to_fold
        )
        prior_summary = (
            f"Prior summary:\n{conversation.summary}\n\n" if conversation.summary else ""
        )

        prompt = (
            f"{prior_summary}New messages to fold in:\n{transcript}\n\n"
            "Write the updated running summary."
        )
        system_prompt = _SUMMARIZATION_SYSTEM_PROMPT.format(
            max_tokens=settings.MEMORY_SUMMARY_MAX_TOKENS
        )

        new_summary = await self.llm_client.generate(system_prompt, prompt)
        new_cutoff = to_fold[-1].turn_index

        return new_summary, new_cutoff

    async def build_context(
        self, conversation: Conversation, all_messages: list[Message]
    ) -> ConversationContext:
        recent = self.select_recent_within_budget(all_messages)
        return ConversationContext(summary=conversation.summary, recent_messages=recent)