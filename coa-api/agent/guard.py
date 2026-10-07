"""The submit guard: reads the run's state, calls tools.rules.decide_status,
and refuses (with the reason, as a tool message) when check_spec or
check_supplier has not run or the proposed status disagrees."""
