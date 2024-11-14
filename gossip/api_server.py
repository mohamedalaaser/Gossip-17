import asyncio

from gossip.api_connection import APIConnection


class APIServer:

    def __init__(self, gossip):
        self.gossip = gossip
        self.host, self.port = gossip.config.api_address.split(":")

    async def on_connection(self, reader, writer):
        connection = APIConnection(self.gossip, reader, writer)

        async with self.gossip.api_connections_lock:
            self.gossip.api_connections.append(connection)

        asyncio.create_task(connection.run())

    async def run(self):
        try:
            server = await asyncio.start_server(
                self.on_connection, self.host, self.port
            )

            print(f">>>> API Server started, listening on {self.host}:{self.port} <<<<")

            async with server:
                await server.serve_forever()
        except Exception as e:
            print(
                f"[-][API] Error in starting API server on {self.host}:{self.port}: {e}"
            )
