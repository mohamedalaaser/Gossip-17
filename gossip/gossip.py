"""Start gossip module."""

import asyncio
from collections import deque
from gossip.api_server import APIServer
from gossip.config import Config
from gossip.p2p_server import P2PServer


class Gossip:
    """Gossip class to start the gossip module."""

    def __init__(self, config_file_path):
        self.config = Config(config_file_path)
        print("Gossip module started")

        self.api_connections = []
        self.api_connections_lock = asyncio.Lock()

        # key: data_type, value: list of subscribed connections
        self.subscriptions = {}
        self.subscriptions_lock = asyncio.Lock()

        self.p2p_connections = deque(maxlen=self.config.degree)
        self.p2p_connections_lock = asyncio.Lock()

        self.unverified_p2p_connections = deque(maxlen=self.config.degree)
        self.unverified_p2p_connections_lock = asyncio.Lock()

        # key: message_id, value: [ttl, data_type, data, sender p2p_connection, [subscribers] ]
        self.unvalidated_announces = {}
        self.unvalidated_announces_lock = asyncio.Lock()

        self.cache = deque(maxlen=self.config.cache_size)
        self.cache_lock = asyncio.Lock()

    async def run(self):
        asyncio.create_task(APIServer(self).run())
        asyncio.create_task(P2PServer(self).run())

        while True:
            await asyncio.sleep(1)
