"""C8: the fixed pipeline: read_coa, identify, normalize, check_spec,
check_supplier, in that order, with the same tools as the agent. No lot history,
no drafts, no questions: any difference in results comes from the agent's
choices, not from better tools. An error is caught and reported as status
ERROR, never a stack trace."""
