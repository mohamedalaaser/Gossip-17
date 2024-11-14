import asyncio
import struct

from gossip.p2p_connection import P2PConnection, initiate_connection_to_peer
from gossip.messages_type import PEER_DISCOVER


class P2PServer:

    def __init__(self, gossip):
        self.gossip = gossip
        self.host, self.port = gossip.config.p2p_address.split(":")
        self.bootstrapper_host, self.bootstrapper_port = (
            gossip.config.bootstrapper.split(":")
        )

    async def run(self):
        asyncio.create_task(self.start_server())

        async with self.gossip.unverified_p2p_connections_lock:
            await initiate_connection_to_peer(
                self.bootstrapper_host, self.bootstrapper_port, self.gossip
            )

        asyncio.create_task(self.peer_discovery())

    async def on_connection(self, reader, writer):
        connection = P2PConnection(self.gossip, reader, writer, None)

        async with self.gossip.unverified_p2p_connections_lock:
            self.gossip.unverified_p2p_connections.append(connection)

        asyncio.create_task(connection.run())

    async def start_server(self):
        try:
            server = await asyncio.start_server(
                self.on_connection, self.host, self.port
            )
            print(f">>>> P2P Server started, listening on {self.host}:{self.port} <<<<")

            async with server:
                await server.serve_forever()
        except Exception as e:
            print(
                f"[-][P2P] Error in starting P2P server on {self.host}:{self.port}: {e}"
            )

    async def peer_discovery(self):

        peer_discover_msg = struct.pack(">HH", 4, PEER_DISCOVER)

        async def send_peer_discover(connection):
            try:
                print(
                    f"[+][P2P] Sending PEER_DISCOVER to {connection.address}:{connection.listening_port}"
                )
                connection.writer.write(peer_discover_msg)
                await connection.writer.drain()
            except Exception as e:
                print(
                    f"[-][P2P] Error in sending PEER_DISCOVER to {connection.address}:{connection.listening_port}: {e}"
                )

        while True:

            async with self.gossip.p2p_connections_lock:
                if (
                    len(self.gossip.p2p_connections)
                    < self.gossip.p2p_connections.maxlen
                ):
                    print("====================================")
                    print(f"[+][P2P] Discovering peers")
                    tasks = []
                    for connection in self.gossip.p2p_connections:
                        tasks.append(
                            asyncio.create_task(send_peer_discover(connection))
                        )
                    await asyncio.gather(*tasks)

            async with self.gossip.unverified_p2p_connections_lock:
                async with self.gossip.p2p_connections_lock:
                    print(
                        f"current connections {[f'{c.address}:{c.listening_port}' for c in self.gossip.p2p_connections]}"
                    )
                    print(
                        f"current unverified connections: {[f'{c.address}:{c.port}' for c in self.gossip.unverified_p2p_connections]}"
                    )
            print("====================================")
            await asyncio.sleep(self.gossip.config.discovery_cooldown)
