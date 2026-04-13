import asyncio
import pytest
from agentlabx.core.turn_context import TurnContext, current_turn, push_turn


def test_push_turn_sets_and_clears():
    assert current_turn() is None
    ctx = TurnContext(turn_id="t1", agent="a", stage="s", is_mock=False)
    with push_turn(ctx):
        assert current_turn() is ctx
    assert current_turn() is None


async def test_turn_context_isolated_per_task():
    async def worker(label):
        ctx = TurnContext(turn_id=f"t-{label}", agent="a", stage="s", is_mock=False)
        with push_turn(ctx):
            await asyncio.sleep(0)
            return current_turn().turn_id

    r = await asyncio.gather(worker("a"), worker("b"))
    assert set(r) == {"t-a", "t-b"}
