"""C1: writes the CSV files and the 8 CoA PDFs, all invented.

Run from coa-api:  uv run python -m dataset.make_data

Deterministic: reportlab is called with invariant=1 so regenerating does not
change PDF bytes. Layout A (table on page 1) for scenarios 1-4, layout B (two
pages, different column order) for 5-8. Writes spec, materials, suppliers,
lot_history, aliases and expected .csv beside this file.
"""
