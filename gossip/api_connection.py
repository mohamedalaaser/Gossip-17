import struct
import hexdump


from gossip.messages_type import (
    GOSSIP_ANNOUNCE,
    GOSSIP_NOTIFY,
    GOSSIP_VALIDATION,
    PEER_ANOUNCE,
    GOSSIP_NOTIFICATION,
)


class APIConnection:

    def __init__(self, gossip, reader, writer):
        self.gossip = gossip
        self.reader = reader
        self.writer = writer

        peername = writer.get_extra_info("peername")
        self.address = peername[0]
        self.port = peername[1]

    async def close_connection(self):
        print(f"[-][API] Closing connection with {self.address}:{self.port}")
        self.writer.close()
        async with self.gossip.api_connections_lock:
            if self in self.gossip.api_connections:
                self.gossip.api_connections.remove(self)

        async with self.gossip.subscriptions_lock:
            for data_type in self.gossip.subscriptions:
                if self in self.gossip.subscriptions[data_type]:
                    self.gossip.subscriptions[data_type].remove(self)
                    print(
                        f"[+] Removed {self.address}:{self.port} from list of subscribers of data type: ${data_type}"
                    )

    async def run(self):
        """listen for incoming messages"""

        print(f"[+][API] Connection established with {self.address}:{self.port}")
        while True:
            try:
                msg_size_bytes = await self.reader.read(2)
                msg_size = struct.unpack(">H", msg_size_bytes)[0]
                if msg_size < 8 or msg_size > 65535:
                    raise Exception(f"[-][API] Invalid message size {msg_size}")
                msg = msg_size_bytes + await self.reader.read(msg_size - 2)
                if len(msg) != (msg_size):
                    raise Exception(
                        f"[-][API] Incomplete message received from {self.address}:{self.port}=> expected {msg_size} bytes, got {len(msg)} bytes"
                    )
                print("++++++++++++++++++++")
                await self.handle_message(msg)
            except Exception as e:
                print(
                    f"[-][API] Error in Connection with {self.address}:{self.port} \n Exception: {e}"
                )
                await self.close_connection()
                break
            print("++++++++++++++++++++")

    async def handle_message(self, msg):
        """handle incoming message"""
        print(f"[+][API] Packet arrived from {self.address}:{self.port}")

        msg_type = struct.unpack(">H", msg[2:4])[0]

        if msg_type == GOSSIP_ANNOUNCE:
            await self.handle_gossip_announce(msg)
        elif msg_type == GOSSIP_NOTIFY:
            await self.handle_gossip_notify(msg)
        elif msg_type == GOSSIP_VALIDATION:
            await self.handle_gossip_validation(msg)
        else:
            raise Exception(
                f"[-][API] Unknown message type {msg_type} received from {self.address}:{self.port}"
            )

    async def handle_gossip_announce(self, msg):

        try:
            print(f"[+][API] GOSSIP_ANNOUNCE from {self.address}:{self.port} =>\n")
            ttl = struct.unpack(">B", msg[4:5])[0]
            data_type = struct.unpack(">H", msg[6:8])[0]
            data = msg[8:]

            print(f"    [+] Data type: {data_type}")
            print(f"    [+] TTL: {ttl}")
            print(f"    [+] Data: {hexdump.dump(data)}")

            async with self.gossip.subscriptions_lock:
                if data_type in self.gossip.subscriptions:
                    gossip_notification_message = (
                        struct.pack(
                            ">HHHH",
                            8 + len(data),
                            GOSSIP_NOTIFICATION,
                            0,
                            data_type,
                        )
                        + data
                    )
                    for connection in self.gossip.subscriptions[data_type]:
                        if connection != self:
                            try:
                                print(
                                    f"[+][API] Sending GOSSIP_NOTIFICATION to {connection.address}:{connection.port}"
                                )
                                connection.writer.write(gossip_notification_message)
                                await connection.writer.drain()
                            except Exception as e:
                                print(
                                    f"[-][API] Error in sending GOSSIP_NOTIFICATION to {connection.address}:{connection.port}: {e}"
                                )

            peer_announce_msg = (
                struct.pack(
                    ">HHBBH",
                    8 + len(data),
                    PEER_ANOUNCE,
                    ttl,
                    0,
                    data_type,
                )
                + data
            )

            async with self.gossip.p2p_connections_lock:
                for connection in self.gossip.p2p_connections:
                    try:
                        print(
                            f"[+][P2P] Sending PEER_ANNOUNCE to {connection.address}:{connection.listening_port}"
                        )
                        connection.writer.write(peer_announce_msg)
                        await connection.writer.drain()
                    except Exception as e:
                        print(
                            f"[-][P2P] Error in sending PEER_ANNOUNCE to {connection.address}:{connection.listening_port}: {e}"
                        )

        except Exception as e:
            print(
                f"[-][API] Error in handling GOSSIP_ANNOUNCE from {self.address}:{self.port}"
            )
            raise e

    async def handle_gossip_notify(self, msg):
        try:
            print(f"[+][API] GOSSIP_NOTIFY from {self.address}:{self.port} =>\n")

            data_type = struct.unpack(">H", msg[6:8])[0]

            print(f"    [+] Data type: {data_type}")

            async with self.gossip.subscriptions_lock:
                if data_type not in self.gossip.subscriptions:
                    self.gossip.subscriptions[data_type] = (
                        set()
                    )  # Using set to avoid duplicates
                    print(f"[+] new valid data type is registered: {data_type}")
                self.gossip.subscriptions[data_type].add(self)
                print(
                    f"[+] Added {self.address}:{self.port} to list of subscribers of data type: {data_type}"
                )

        except Exception as e:
            print(
                f"[-][API] Error in handling GOSSIP_NOTIFY from {self.address}:{self.port}"
            )

            raise e

    async def handle_gossip_validation(self, msg):
        print(f"[+][API] GOSSIP_VALIDATION received from {self.address}:{self.port}")

        try:
            message_id = struct.unpack(">H", msg[4:6])[0]
            is_valid = (struct.unpack(">H", msg[6:8])[0]) & 1 != 0

            print(f"    [+] Message ID: {message_id}")
            print(f"    [+] Is Valid: {is_valid}")

            async with self.gossip.unvalidated_announces_lock:
                if message_id not in self.gossip.unvalidated_announces:
                    print(
                        f"[-][API] GOSSIP_VALIDATION received for message_id {message_id} that does not exist in unvalidated_announces"
                    )
                    return

                if self not in self.gossip.unvalidated_announces[message_id][4]:
                    raise Exception(
                        f"[-][API] GOSSIP_VALIDATION received for message_id {message_id} from a non validator: {self.address}:{self.port}"
                    )

                if not is_valid:
                    print(
                        f"[+][API] Message {message_id} is not valid. Deleting data and not propagating it further and dropping sender peer connection."
                    )
                    _, _, _, sender, _ = self.gossip.unvalidated_announces.pop(
                        message_id
                    )
                    await sender.close_connection()
                    async with self.gossip.p2p_connections_lock:
                        if sender in self.gossip.p2p_connections:
                            self.gossip.p2p_connections.remove(sender)

                    return

                print("[+][API] removing connection from list of awaited validators")
                self.gossip.unvalidated_announces[message_id][4].remove(self)

                if len(self.gossip.unvalidated_announces[message_id][4]) == 0:
                    print(
                        "[+][API] All validators have validated the message. Message will now be announced to peers."
                    )
                    ttl, data_type, data, sender, _ = (
                        self.gossip.unvalidated_announces.pop(message_id)
                    )

                    peer_announce_msg = (
                        struct.pack(
                            ">HHBBH",
                            8 + len(data),
                            PEER_ANOUNCE,
                            ttl,
                            0,
                            data_type,
                        )
                        + data
                    )

                    async with self.gossip.p2p_connections_lock:
                        for connection in self.gossip.p2p_connections:
                            if connection != sender:
                                try:
                                    print(
                                        f"[+][P2P] Sending PEER_ANNOUNCE to {connection.address}:{connection.listening_port}"
                                    )
                                    connection.writer.write(peer_announce_msg)
                                    await connection.writer.drain()
                                except Exception as e:
                                    print(
                                        f"[-][P2P] Error in sending PEER_ANNOUNCE to {connection.address}:{connection.port}: {e}"
                                    )

        except Exception as e:
            print(
                f"[-][API] Error in handling GOSSIP_VALIDATION from {self.address}:{self.port}"
            )
            raise e
