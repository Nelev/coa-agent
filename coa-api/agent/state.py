"""What a run carries besides its messages.

Set by the server or written by tools, never typed by the model: the tools
read it from the injected state, so the model cannot pick which PDF is read
and `submit` can see which checks really ran.
"""

from typing import Annotated, NotRequired, TypedDict

from langgraph.graph.message import add_messages


class RunState(TypedDict):
    messages: Annotated[list, add_messages]
    # Server-set. read_coa takes no pdf argument; it reads this.
    pdf_id: str
    # Written by tools as they run. None means "invalidated by a later call";
    # the injected state is validated against these types, so it must be allowed.
    extraction: NotRequired[dict]
    material_code: NotRequired[str]
    supplier_id: NotRequired[str]
    normalized: NotRequired[list[dict] | None]
    spec_check: NotRequired[dict | None]
    supplier_check: NotRequired[dict | None]
    # test -> get_lot_history output; backs a likely_coa_error claim.
    lot_history: NotRequired[dict[str, dict]]
    # draft_id -> Draft dump, and the one the final result will point at.
    drafts: NotRequired[dict[str, dict]]
    draft_id: NotRequired[str]
    # Every tool call counts, including ask_user and refused submits.
    calls_used: NotRequired[int]
    # Per-tool consecutive failures: two of the same tool end the run as REVIEW.
    failures: NotRequired[dict[str, int]]
    result: NotRequired[dict]
