"""C7: write_step(run_id, ...) and tail(run_id, after_seq) over the steps table.
The SSE route tails by seq and honours Last-Event-ID, so a dropped connection
resumes and a finished run replays."""
