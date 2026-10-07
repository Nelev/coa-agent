# Dataset

All of it is invented. See the root README for the scenario table.

- `make_data.py` writes everything below.
- `coa/coa_0{1..8}_*.pdf` are the synthetic CoAs, committed.
- `spec.csv`, `materials.csv`, `suppliers.csv`, `lot_history.csv`, `aliases.csv`
  are the reference data the code tools read.
- `expected.csv` is the ground truth: `file, expected_status, expected_findings`
  (as `test:severity;...`), plus `answer` and `final_status` for the scenario
  that asks a question.
