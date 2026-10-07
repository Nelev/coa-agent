from sqlalchemy import select

from database import dispose_engine, get_session, init_engine
from model import Run, Step


async def test_steps_round_trip_in_order(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    await init_engine()
    try:
        async for session in get_session():
            session.add(Run(id="r1", kind="agent", pdf_id="p1"))
            session.add_all(
                Step(run_id="r1", seq=n, tool=t)
                for n, t in [(2, "check_spec"), (1, "read_coa")]
            )
            await session.commit()
            rows = (await session.scalars(select(Step).order_by(Step.seq))).all()
            assert [s.tool for s in rows] == ["read_coa", "check_spec"]
    finally:
        await dispose_engine()
