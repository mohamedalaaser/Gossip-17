import hashlib
import random
import struct
import time
import hexdump
import asyncio

from gossip.messages_type import (
    GOSSIP_NOTIFICATION,
    PEER_ANOUNCE,
    PEER_BROADCAST,
    PEER_DISCOVER,
    PEER_INIT,
    PEER_VERIFY,
    PEER_OK,
)


class P2PConnection:

    def __init__(self, gossip, reader, writer, listening_port):
        self.gossip = gossip
        self.reader = reader
        self.writer = writer

        peername = writer.get_extra_info("peername")
        self.address = peername[0]
        self.port = peername[1]
        self.listening_port = listening_port
        self.challenge_sent = None
        self.challenge_timeout = None
        self.validated = False

    async def close_connection(self):
        print(f"[-][P2P] Closing connection with {self.address}:{self.port}")
        self.writer.close()
        async with self.gossip.p2p_connections_lock:
            if self in self.gossip.p2p_connections:
                self.gossip.p2p_connections.remove(self)
        async with self.gossip.unverified_p2p_connections_lock:
            if self in self.gossip.p2p_connections:
                self.gossip.unverified_p2p_connections.remove(self)

    async def send_peer_init(self):
        self.challenge_sent = random.getrandbits(64)
        self.challenge_timeout = time.time() + self.gossip.config.challenge_timeout

        message = struct.pack(">HHQ", 12, PEER_INIT, self.challenge_sent)
        print(f"[+][PEER] Sending PEER_CHALLENGE to: {self.address}:{self.port}")
        self.writer.write(message)
        await self.writer.drain()

    async def run(self):
        """listen for incoming messages"""

        print(f"[+][P2P] Connection established with {self.address}:{self.port}")

        if self.listening_port is None:
            await self.send_peer_init()

        while True:
            try:
                msg_size_bytes = await self.reader.read(2)
                msg_size = struct.unpack(">H", msg_size_bytes)[0]
                if msg_size < 4 or msg_size > 65535:
                    raise Exception(f"[-][P2P] Invalid message size {msg_size}")
                msg = msg_size_bytes + await self.reader.read(msg_size - 2)
                if len(msg) != (msg_size):
                    raise Exception(
                        f"[-][P2P] Incomplete message received from {self.address}:{self.port}=> expected {msg_size} bytes, got {len(msg)} bytes"
                    )
                print("++++++++++++++++++++")
                await self.handle_message(msg)
            except Exception as e:
                print(
                    f"[-][P2P] Error in Connection with {self.address}:{self.port} \n Exception: {e}"
                )
                await self.close_connection()
                break
            print("++++++++++++++++++++")

    async def handle_message(self, msg):
        """handle incoming message"""
        print(f"[+][P2P] Packet arrived from {self.address}:{self.port}")

        msg_type = struct.unpack(">H", msg[2:4])[0]

        def check_validated(msg_type):
            if not self.validated:
                raise Exception(
                    f"[-][P2P] Cannot receive {msg_type} from unvalidated connection"
                )

        if msg_type == PEER_INIT:  # nonce
            asyncio.create_task(self.handle_peer_init(msg))
        elif msg_type == PEER_VERIFY:
            await self.handle_peer_verify(msg)
        elif msg_type == PEER_OK:
            await self.handle_peer_ok()
        elif msg_type == PEER_ANOUNCE:
            check_validated("PEER_ANOUNCE")
            await self.handle_peer_announce(msg)
        elif msg_type == PEER_DISCOVER:
            check_validated("PEER_DISCOVER")
            await self.handle_peer_discover()
        elif msg_type == PEER_BROADCAST:
            check_validated("PEER_BROADCAST")
            await self.handle_peer_broadcast(msg)

        else:
            raise Exception(
                f"[-][P2P] Unknown message type {msg_type} received from {self.address}:{self.port}"
            )

    async def handle_peer_init(self, msg):

        print(f"[+][P2P] PEER_CHALLENGE from {self.address}:{self.port}")

        try:

            challenge = int(struct.unpack(">Q", msg[4:])[0]).to_bytes(8, "big")
            print(f"    [+] Challenge: {challenge}")

            difficulty = self.gossip.config.challenge_difficulty
            our_listening_port = int(self.gossip.config.p2p_address.split(":")[1])
            our_listening_port_bytes = our_listening_port.to_bytes(2, "big")

            print(f"[+][P2P] Finding nonce")
            nonce = None
            for trial in range(2**64):

                hash = hashlib.sha256(
                    (challenge + trial.to_bytes(8, "big") + our_listening_port_bytes)
                ).hexdigest()

                if hash[:difficulty] == "0" * difficulty:
                    nonce = trial
                    print(f"[+] Found nonce {nonce}")
                    print(f"[+] hash(challenge + nonce + our_listening_port) => {hash}")
                    break

            if nonce is None:
                raise Exception("[-] Could not find a nonce")

            message = struct.pack(
                ">HHHHQ", 16, PEER_VERIFY, 0, our_listening_port, nonce
            )
            print(f"[+][P2P] Sending PEER_VERIFY to {self.address}:{self.port}")
            self.writer.write(message)
            await self.writer.drain()

        except Exception as e:
            print(
                f"[-][P2P] Error in handling PEER_CHALLENGE from {self.address}:{self.port}"
            )
            raise e

    async def handle_peer_verify(self, msg):
        print(f"[+][P2P] PEER_VERIFY from {self.address}:{self.port} =>\n")

        try:
            if self.challenge_sent is None or self.listening_port is not None:
                raise Exception("[-][P2P] not expecting this message at this time")

            if time.time() > self.challenge_timeout:
                raise Exception("[-][P2P] Received nonce after timeout")

            listening_port, nonce = struct.unpack(">HQ", msg[6:])
            print(f"    [+] listening_port: {listening_port}")
            print(f"    [+] nonce: {nonce}")

            hash = hashlib.sha256(
                self.challenge_sent.to_bytes(8, "big")
                + nonce.to_bytes(8, "big")
                + listening_port.to_bytes(2, "big")
            ).hexdigest()

            print(f"hash : {hash}")

            difficulty = self.gossip.config.challenge_difficulty
            if not hash[:difficulty] == "0" * difficulty:
                raise Exception("[-][P2P] Received invalid nonce")

            self.listening_port = listening_port
            print(f"[+][P2P] Sending PEER_OK to {self.address}:{self.listening_port}")

            async with self.gossip.unverified_p2p_connections_lock:
                async with self.gossip.p2p_connections_lock:
                    self.gossip.unverified_p2p_connections.remove(self)

                    if (
                        len(self.gossip.p2p_connections)
                        >= self.gossip.p2p_connections.maxlen
                    ):
                        popped_connection = self.gossip.p2p_connections.popleft()
                        popped_connection.writer.close()
                        print(
                            f"[-][P2P] Popped connection with {popped_connection.address}:{popped_connection.listening_port}"
                        )

                    self.gossip.p2p_connections.append(self)
            self.validated = True

            message = struct.pack(">HH", 4, PEER_OK)
            self.writer.write(message)
            await self.writer.drain()

        except Exception as e:
            print(
                f"[-][P2P] Error in handling PEER_VERIFY from {self.address}:{self.port}"
            )
            raise e

    async def handle_peer_ok(self):
        print(f"[+][P2P] PEER_OK from {self.address}:{self.port}")

        try:
            if self.challenge_sent is not None:
                raise Exception("[-][P2P] not expecting this message at this time")

            async with self.gossip.unverified_p2p_connections_lock:
                async with self.gossip.p2p_connections_lock:
                    self.gossip.unverified_p2p_connections.remove(self)

                    if (
                        len(self.gossip.p2p_connections)
                        >= self.gossip.p2p_connections.maxlen
                    ):
                        popped_connection = self.gossip.p2p_connections.popleft()
                        popped_connection.writer.close()
                        print(
                            f"[-][P2P] Popped connection with {popped_connection.address}:{popped_connection.listening_port}"
                        )

                    self.gossip.p2p_connections.append(self)
            self.validated = True

        except Exception as e:
            print(f"[-][P2P] Error in handling PEER_OK from {self.address}:{self.port}")
            raise e

    async def handle_peer_announce(self, msg):
        print(f"[+][P2P] PEER_ANNOUNCE from {self.address}:{self.listening_port}")

        try:

            ttl = struct.unpack(">B", msg[4:5])[0]
            data_type = struct.unpack(">H", msg[6:8])[0]
            data = msg[8:]

            print(f"    [+] Data type: {data_type}")
            print(f"    [+] TTL: {ttl}")
            print(f"    [+] Data: {hexdump.dump(data)}")

            subscribers = []
            async with self.gossip.subscriptions_lock:
                if not (
                    data_type in self.gossip.subscriptions
                    and self.gossip.subscriptions[data_type]
                ):
                    print(
                        f"[-][P2P] No subscribers for data type {data_type}. Discarding message from {self.address}:{self.listening_port}"
                    )
                    return
                subscribers = self.gossip.subscriptions[data_type].copy()

            message_hash = hashlib.sha1(msg[6:]).digest()
            async with self.gossip.cache_lock:
                if message_hash in self.gossip.cache:
                    print(
                        f"[+] Message already in cache. Discarding message from {self.address}:{self.listening_port}"
                    )
                    return
                self.gossip.cache.append(message_hash)

            message_id = random.randint(1, 2**16 - 1)

            if ttl != 1:
                if ttl > 1:
                    ttl = ttl - 1
                async with self.gossip.unvalidated_announces_lock:
                    while message_id in self.gossip.unvalidated_announces:
                        message_id = random.randint(0, 2**16 - 1)

                    self.gossip.unvalidated_announces[message_id] = [
                        ttl,
                        data_type,
                        data,
                        self,
                        subscribers,
                    ]

            gossip_notification_message = (
                struct.pack(
                    ">HHHH",
                    8 + len(data),
                    GOSSIP_NOTIFICATION,
                    message_id,
                    data_type,
                )
                + data
            )

            for connection in subscribers:
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

        except Exception as e:
            print(
                f"[-][P2P] Error in handling PEER_ANNOUNCE from {self.address}:{self.listening_port}"
            )
            raise e

    async def handle_peer_discover(self):
        print(f"[+][P2P] PEER_DISCOVER from {self.address}:{self.listening_port}")

        try:
            async with self.gossip.p2p_connections_lock:
                addresses = []
                for connection in self.gossip.p2p_connections:
                    if not (
                        connection.address == self.address
                        and int(connection.listening_port) == int(self.listening_port)
                    ):
                        addresses.append(
                            f"{connection.address}:{connection.listening_port}"
                        )

                if len(addresses) == 0:
                    print(
                        f"[+][P2P] No addresses known to send to {self.address}:{self.listening_port}"
                    )
                    return

                addresses_bytes = (",".join(addresses)).encode("utf-8")

                peer_broadcast_msg = (
                    struct.pack(">HH", 4 + len(addresses_bytes), PEER_BROADCAST)
                    + addresses_bytes
                )

                print(
                    f"[+][P2P] Sending PEER_BROADCAST to {self.address}:{self.listening_port}"
                )
                print(f"    [+] Addresses: {addresses}")
                self.writer.write(peer_broadcast_msg)
                await self.writer.drain()

        except Exception as e:
            print(
                f"[-][P2P] Error in handling PEER_DISCOVER from {self.address}:{self.listening_port}"
            )
            raise e

    async def handle_peer_broadcast(self, msg):
        print(f"[+][P2P] PEER_BROADCAST from {self.address}:{self.listening_port}")
        try:

            addresses = msg[4:].decode("utf-8").split(",")
            print(f"    [+] Addresses: {addresses}")
            got_new_addresses = False
            async with self.gossip.p2p_connections_lock:
                async with self.gossip.unverified_p2p_connections_lock:
                    for address in addresses:
                        peer_address, peer_port = address.split(":")

                        our_address, our_port = self.gossip.config.p2p_address.split(
                            ":"
                        )

                        if peer_address == our_address and int(peer_port) == int(
                            our_port
                        ):
                            continue

                        connection_exists = False
                        for connection in self.gossip.p2p_connections:
                            if connection.address == peer_address and (
                                int(connection.listening_port) == int(peer_port)
                                or int(connection.port) == int(peer_port)
                            ):
                                connection_exists = True
                                break
                        if not connection_exists:
                            for connection in self.gossip.unverified_p2p_connections:
                                if connection.address == peer_address and (
                                    int(connection.listening_port) == int(peer_port)
                                    or int(connection.port) == int(peer_port)
                                ):
                                    connection_exists = True
                                    break

                        if not connection_exists:
                            got_new_addresses = True
                            print(
                                f"[+][P2P] Initiating connection with {peer_address}:{peer_port}"
                            )

                            await initiate_connection_to_peer(
                                peer_address, peer_port, self.gossip
                            )

                    if not got_new_addresses:
                        print(
                            f"[+][P2P] No new addresses to connect to from {self.address}:{self.listening_port}"
                        )

        except Exception as e:
            print(
                f"[-][P2P] Error in handling PEER_BROADCAST from {self.address}:{self.listening_port}"
            )
            raise e


async def initiate_connection_to_peer(peer_address, peer_port, gossip):
    try:

        print(f"[+][P2P] Initiating p2p connection with {peer_address}:{peer_port}")
        reader, writer = await asyncio.open_connection(peer_address, peer_port)

        connection = P2PConnection(gossip, reader, writer, peer_port)

        gossip.unverified_p2p_connections.append(connection)

        asyncio.create_task(connection.run())

    except Exception as e:
        print(
            f"[-][P2P] Error in initiating connection with {peer_address}:{peer_port}: {e}"
        )
