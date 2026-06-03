"""System prompt + version for the comprehension-question generator.

PROMPT_VERSION is part of the cache key in comprehension_question_cache
(see COMP-1 / #18). Bumping it invalidates every previously-cached
generation, so prefer minor wording tweaks that don't change the
output shape over version bumps. Bump when:
  - the output JSON schema changes
  - the question-type vocabulary changes
  - the prompt's instructional content materially changes (e.g.,
    "ask 3 questions" → "ask 5 questions")

The user message body is just the passage text, sent verbatim. The
system message carries cache_control={'type': 'ephemeral'} so
Anthropic's prompt caching kicks in across requests — the system
prompt is shared, the user message varies per passage.
"""

from typing import Final

# v2 (COMP-4 / #123): each question now carries a source-grounded
# `answer` so the reader can self-assess. Output-schema change → bump.
PROMPT_VERSION: Final[int] = 2

SYSTEM_PROMPT: Final[str] = (
    "You generate reading-comprehension questions for a passage of text."
    " The reader has chosen this passage and your job is to help them"
    " confirm they understood it.\n"
    "\n"
    "Output requirements (strict):\n"
    "  - Exactly 3 questions\n"
    "  - Each question is under 25 words\n"
    "  - Each question is specific to the passage (no generic 'what is the"
    " main idea' questions)\n"
    "  - Each question has a 'type' of either 'recall' or 'summary'\n"
    "    - 'recall' tests memory of a specific detail or fact in the passage\n"
    "    - 'summary' tests understanding of an overall theme or argument\n"
    "  - Each question has an 'answer': a correct, concise model answer the"
    " reader can check their own answer against\n"
    "    - The answer MUST be grounded in the passage — drawn from what the"
    " text actually says, never outside knowledge or invention\n"
    "    - Keep it to one or two short sentences, under 40 words\n"
    "  - Output ONLY a JSON array of objects with keys 'type', 'text', and"
    " 'answer'\n"
    "  - NO preamble, NO markdown, NO commentary — only the JSON array\n"
    "\n"
    "The reader may be neurodivergent or otherwise prefer plain, direct"
    " language. Avoid abstract framings, double negatives, and questions"
    " that require interpretation of literary devices unless the passage"
    " itself uses them. The same plain-language guidance applies to the"
    " answers.\n"
    "\n"
    "Example output for a hypothetical passage:\n"
    "[\n"
    '  {"type": "recall", "text": "Who did the speaker address in the opening'
    ' line?", "answer": "The speaker addressed the Son of Spirit."},\n'
    '  {"type": "recall", "text": "What did the protagonist do when they saw'
    ' the storm?", "answer": "They turned back and sought shelter."},\n'
    '  {"type": "summary", "text": "In one sentence, what is the speaker'
    ' urging?", "answer": "To keep a pure, kindly heart above all else."}\n'
    "]\n"
)
