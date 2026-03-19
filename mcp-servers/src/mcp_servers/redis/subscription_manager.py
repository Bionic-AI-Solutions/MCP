"""
Redis Subscription Manager

Manages persistent pub/sub subscriptions across stateless MCP HTTP requests.
Each subscription holds a dedicated Redis PubSub connection and a background
asyncio task that reads messages into a bounded deque. Clients poll for
buffered messages via subscription ID.

Supports both standalone Redis and Redis Cluster. For cluster mode, a
dedicated standalone connection is created to a random cluster node for
pub/sub (Redis Cluster broadcasts pub/sub across all nodes natively).
"""

import asyncio
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import redis.asyncio as aioredis


@dataclass
class Subscription:
    """Tracks a single Redis pub/sub subscription."""

    sub_id: str
    tenant_id: str
    channel: str  # prefixed channel name in Redis
    display_channel: str  # unprefixed channel name for callers
    is_pattern: bool
    messages: deque  # bounded deque of received messages
    task: asyncio.Task  # background listener task
    pubsub: object  # redis PubSub instance
    created_at: float
    last_polled: float
    notify: asyncio.Event = field(default_factory=asyncio.Event)  # signaled on new message
    standalone_conn: object = None  # standalone Redis conn for cluster pub/sub


class SubscriptionManager:
    """Manages persistent Redis pub/sub subscriptions across stateless HTTP calls.

    Architecture:
    - subscribe() creates a Redis PubSub object and starts a background asyncio
      task that reads messages into a bounded deque.
    - poll() drains and returns all buffered messages for a subscription.
    - unsubscribe() cancels the background task and closes the PubSub connection.
    - A background cleanup task removes subscriptions not polled within idle_timeout.
    """

    def __init__(self, max_messages: int = 1000, idle_timeout: int = 300):
        self.subscriptions: Dict[str, Subscription] = {}
        self.max_messages = max_messages
        self.idle_timeout = idle_timeout  # seconds before auto-cleanup
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the periodic cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        """Stop all subscriptions and the cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        for sub_id in list(self.subscriptions):
            await self.unsubscribe(sub_id)

    async def _get_pubsub(self, client, config=None):
        """Get a PubSub object, handling both standalone and cluster clients.

        For Redis Cluster, pub/sub is broadcast across all nodes. We create
        a dedicated standalone Redis connection to a random cluster node.
        """
        from redis.asyncio.cluster import RedisCluster
        if isinstance(client, RedisCluster):
            # Get a random node from the cluster for pub/sub
            node = client.get_random_node()
            standalone = aioredis.Redis(
                host=node.host,
                port=node.port,
                password=config.get("password") if config else None,
                decode_responses=True,
            )
            return standalone.pubsub(), standalone
        else:
            return client.pubsub(), None

    async def subscribe(
        self,
        tenant_id: str,
        client,
        channel: str,
        display_channel: str,
        is_pattern: bool = False,
        config: dict = None,
    ) -> str:
        """Create a new subscription. Returns subscription ID."""
        sub_id = uuid.uuid4().hex[:8]
        pubsub, standalone_conn = await self._get_pubsub(client, config)

        if is_pattern:
            await pubsub.psubscribe(channel)
        else:
            await pubsub.subscribe(channel)

        messages = deque(maxlen=self.max_messages)
        now = time.time()
        notify = asyncio.Event()

        task = asyncio.create_task(
            self._listen(sub_id, pubsub, messages, display_channel, is_pattern, notify)
        )

        self.subscriptions[sub_id] = Subscription(
            sub_id=sub_id,
            tenant_id=tenant_id,
            channel=channel,
            display_channel=display_channel,
            is_pattern=is_pattern,
            messages=messages,
            task=task,
            pubsub=pubsub,
            created_at=now,
            last_polled=now,
            notify=notify,
            standalone_conn=standalone_conn,
        )
        return sub_id

    async def _listen(
        self,
        sub_id: str,
        pubsub,
        messages: deque,
        display_channel: str,
        is_pattern: bool,
        notify: asyncio.Event = None,
    ) -> None:
        """Background task that reads messages from Redis into the deque."""
        try:
            async for message in pubsub.listen():
                msg_type = message.get("type", "")
                if msg_type in ("message", "pmessage"):
                    data = message.get("data", "")
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    entry = {
                        "channel": display_channel,
                        "data": data,
                        "timestamp": time.time(),
                    }
                    if is_pattern:
                        pattern = message.get("pattern", "")
                        if isinstance(pattern, bytes):
                            pattern = pattern.decode("utf-8")
                        entry["pattern"] = pattern
                    messages.append(entry)
                    if notify:
                        notify.set()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            messages.append({"error": str(e), "timestamp": time.time()})
            if notify:
                notify.set()

    async def poll(self, sub_id: str, timeout: float = 0) -> List[dict]:
        """Drain and return all buffered messages for a subscription.

        Args:
            sub_id: Subscription identifier.
            timeout: Maximum seconds to wait for messages if the buffer is
                empty. 0 (default) returns immediately. Capped at 30s.
        """
        sub = self.subscriptions.get(sub_id)
        if not sub:
            raise ValueError(f"Subscription '{sub_id}' not found")

        timeout = min(max(timeout, 0), 30)

        # If buffer is empty and caller wants to wait, long-poll
        if not sub.messages and timeout > 0:
            sub.notify.clear()
            try:
                await asyncio.wait_for(sub.notify.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass

        sub.last_polled = time.time()
        msgs = list(sub.messages)
        sub.messages.clear()
        sub.notify.clear()
        return msgs

    def list_subscriptions(self, tenant_id: Optional[str] = None) -> List[dict]:
        """List active subscriptions, optionally filtered by tenant."""
        result = []
        for sub in self.subscriptions.values():
            if tenant_id and sub.tenant_id != tenant_id:
                continue
            result.append({
                "subscription_id": sub.sub_id,
                "tenant_id": sub.tenant_id,
                "channel": sub.display_channel,
                "is_pattern": sub.is_pattern,
                "buffered_messages": len(sub.messages),
                "created_at": sub.created_at,
                "last_polled": sub.last_polled,
            })
        return result

    async def unsubscribe(self, sub_id: str) -> bool:
        """Cancel a subscription and clean up resources."""
        sub = self.subscriptions.pop(sub_id, None)
        if not sub:
            return False
        sub.task.cancel()
        try:
            await sub.task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            if sub.is_pattern:
                await sub.pubsub.punsubscribe()
            else:
                await sub.pubsub.unsubscribe()
            await sub.pubsub.aclose()
        except Exception:
            pass
        # Close standalone connection if this was a cluster pub/sub
        if sub.standalone_conn:
            try:
                await sub.standalone_conn.aclose()
            except Exception:
                pass
        return True

    async def _cleanup_loop(self) -> None:
        """Periodically remove subscriptions that haven't been polled."""
        while True:
            try:
                await asyncio.sleep(60)
                now = time.time()
                stale = [
                    sid
                    for sid, s in self.subscriptions.items()
                    if now - s.last_polled > self.idle_timeout
                ]
                for sid in stale:
                    print(f"Warning: Cleaning up idle subscription '{sid}'")
                    await self.unsubscribe(sid)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Warning: Subscription cleanup error: {e}")
