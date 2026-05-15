from __future__ import annotations

import asyncio

from nlp_parser.pubsub import MessagePubSub


def _run(coro):
    return asyncio.run(coro)


def test_pubsub_delivers_to_subscriber():
    async def scenario():
        ps = MessagePubSub()
        q = await ps.subscribe()
        await ps.publish({"id": "1"})
        event = await asyncio.wait_for(q.get(), timeout=1.0)
        await ps.unsubscribe(q)
        return event

    assert _run(scenario())["id"] == "1"


def test_pubsub_multiple_subscribers():
    async def scenario():
        ps = MessagePubSub()
        q1 = await ps.subscribe()
        q2 = await ps.subscribe()
        await ps.publish({"id": "x"})
        a = await asyncio.wait_for(q1.get(), timeout=1.0)
        b = await asyncio.wait_for(q2.get(), timeout=1.0)
        return a, b

    a, b = _run(scenario())
    assert a == b == {"id": "x"}


def test_pubsub_drops_old_when_full():
    async def scenario():
        ps = MessagePubSub()
        q = await ps.subscribe()
        for i in range(150):
            await ps.publish({"i": i})
        assert q.qsize() <= 100

    _run(scenario())
