"""C4: the deterministic tools. Each is a plain function over dataset/*.csv.

identify_material(material_name, supplier_name) -> material_code + supplier_id,
    or candidates when ambiguous
normalize(results) -> results with internal test names and units, plus a note
    per mapping (aliases.csv is keyed per test: supplier_unit -> internal_unit)
check_spec(material_code, results) -> findings[test, value, limit, severity,
    spec_ref] and missing tests
check_supplier(supplier_id, material_code) -> approved, expiry, reason
get_lot_history(supplier_id, material_code, test) -> last 10 values, mean,
    slope, and a trend / outlier classification computed here, not by the model
ask_user(question, options) -> the answer (interrupt(); no side effects first)
"""
