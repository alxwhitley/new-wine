"""
Shared real-answer generation helper for SP1 test scripts. Runs a question
through the actual retrieval + Claude answer-writing path (same system
prompt, same model, same retrieval fusion as production) via direct
function calls — NOT the live /chat HTTP endpoint, so no weekly-query-limit
/ guest-limit metering and no conversations/messages rows are touched (per
Alex's confirmed harness choice). Used by the answer-quality baseline/
regression scripts (Tasks 9, 12) and the Track-A pinned reference test
(Task 13) — the retrieval+Claude-call logic lives in exactly one place.

Note: ANSWER_SYSTEM_BLOCKS is read from system_prompt.txt once, at import
time, inside app.services.answer_toolbox (moved out of app.routers.chat
2026-08-07, mirror-unification batch 1 -- chat.py now imports it from the
same place). Each script that imports this helper does so in its own fresh
`python3` process, so a script run before Task 10's system_prompt.txt edit
picks up the OLD prompt, and one run after picks up the NEW prompt — no
special handling needed, just run things in the order the tasks specify.
"""
import sys
from pathlib import Path
from typing import Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.answer_toolbox import hybrid_search_rrf, _is_citable, ANSWER_SYSTEM_BLOCKS
# Pre-existing, unrelated bug fix (2026-08-07): this previously imported
# `_get_anthropic` from chat.py, which stopped existing there on 2026-07-18
# (commit b4a8c8c, "Extract shared Anthropic client + guardrails loader from
# chat.py") -- that commit moved the client-singleton getter out of chat.py
# and renamed it get_anthropic_client() on app.services.llm_client, updating
# chat.py's own call site accordingly. This script was never updated to
# match and has imported a name chat.py no longer exposes ever since (already
# noted as stale for this reason in
# docs/audits/phase0_measurement_2026-08-01.md:34-35). Fixed here to import
# the real, current function from its real home.
from app.services.llm_client import get_anthropic_client


def generate_real_answer(question: str, db) -> Tuple[str, str]:
    """Returns (answer_text, raw_output). answer_text is what a user would
    see (the <answer> block's contents); raw_output is the model's complete
    raw response, including anything written after </answer>.
    """
    scores, _ = hybrid_search_rrf(question, db, include_copyrighted=True)
    ranked = sorted(scores.items(), key=lambda x: x[1][0], reverse=True)
    chunks = [chunk for _, (_, chunk) in ranked[:8]]

    context_parts = []
    source_num = 0
    for c in chunks:
        if _is_citable(c):
            source_num += 1
            label = f"[Source {source_num}]"
        else:
            label = "[Background]"
        context_parts.append(
            f"{label} (source_kind={c.get('source_kind') or c.get('source_type', 'unknown')}, "
            f"citation_mode={c.get('citation_mode', 'citable')}) "
            f"\"{c.get('title', 'Unknown')}\" by {c.get('author', 'Unknown')}\n{c['content']}"
        )
    context = "\n\n---\n\n".join(context_parts)

    history = [{
        "role": "user",
        "content": f"Sources:\n{context}\n\nQuestion: {question}",
    }]

    client = get_anthropic_client()
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=3000,
        system=ANSWER_SYSTEM_BLOCKS,
        messages=history,
        stream=False,
    )
    raw_output = response.content[0].text

    answer_start = raw_output.find("<answer>")
    answer_end = raw_output.find("</answer>")
    if answer_start != -1 and answer_end != -1:
        answer = raw_output[answer_start + len("<answer>"):answer_end].strip()
    else:
        answer = raw_output.strip()

    return answer, raw_output
