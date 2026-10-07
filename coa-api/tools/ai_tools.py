"""C3: the two tools that call a model, through OpenRouter.

read_coa -- PyMuPDF text layer plus page images to the vision model, structured
    output into schema.Extraction. Takes no argument: the pdf comes from state.
    Checks each source_text appears on its page and caps confidence if not.
draft_supplier_request(supplier, issue, evidence) -> subject, body. Text only;
    drafts are stored and shown, never sent.
"""
