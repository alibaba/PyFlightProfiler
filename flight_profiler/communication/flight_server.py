import asyncio
import json
import socket
import struct
from abc import abstractmethod
from typing import Any, Dict, Optional

from flight_profiler.common.system_logger import logger
from flight_profiler.communication.base import ServerProtocol


class FlightServer(ServerProtocol):

    def __init__(self, interactive_commands: Dict[str, Any]):
        self.server_socket = None
        self.loop = None
        self.interactive_commands = interactive_commands

    async def start_server(self, host: str, port: int):
        if self.loop is None:
            self.loop = asyncio.get_event_loop()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((host, port))
        self.server_socket.listen(100)  # Larger backlog
        self.server_socket.setblocking(False)  # Key: non-blocking mode

        await self.accept_connections()

    async def accept_connections(self):
        # Create a thread pool for handling client connections
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(thread_name_prefix="flight-profiler-recv-", max_workers=200)  # Match socket listen backlog

        try:
            while True:
                try:
                    client_socket, addr = await self.loop.sock_accept(
                        self.server_socket
                    )
                    # Submit the client handling to thread pool while maintaining async behavior
                    self.loop.run_in_executor(executor, self._sync_handle_client, client_socket, addr)
                except Exception as e:
                    logger.exception(f"Error accepting connection: {e}")

        except asyncio.CancelledError:
            logger.exception(f"FlightServer ShutDown exceptionally!")
        finally:
            executor.shutdown(wait=True)

    def _sync_handle_client(self, client_socket, addr):
        """Synchronous wrapper for handling client connections"""
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Run the async handle_client in this thread's event loop
            loop.run_until_complete(self.handle_client(client_socket, addr))
        finally:
            loop.close()

    async def handle_client(self, client_socket, addr):
        writer: Optional[asyncio.StreamWriter] = None
        try:
            reader, writer = await asyncio.open_connection(sock=client_socket)

            request_bytes = await self.handle_read(reader)
            request_json: Dict[str, Any] = json.loads(request_bytes)

            target = request_json["target"]
            is_plugin_calling = request_json.get("is_plugin_calling", True)
            param = request_json.get("param", "")

            logger.debug(
                f"Cmd: {target} Param: {param} is_plugin_calling: {is_plugin_calling}"
            )
            if is_plugin_calling:
                if target in self.interactive_commands:
                    await self.execute_plugin_interactively(
                        target, param, reader, writer
                    )
                else:
                    await self.execute_plugin(target, param, writer)
            else:
                await self.special_calling(target, param, writer)
        except:
            logger.exception("error in execute plugin")
        finally:
            if writer is not None and not writer.is_closing():
                writer.close()
                await writer.wait_closed()

    @abstractmethod
    async def execute_plugin(
        self, cmd: str, param: str, writer: asyncio.StreamWriter
    ) -> None:
        pass

    @abstractmethod
    async def special_calling(
        self, target: str, param: str, writer: asyncio.StreamWriter
    ) -> None:
        pass

    @abstractmethod
    async def execute_plugin_interactively(
        self,
        cmd: str,
        param: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        pass

    async def handle_read(self, reader: asyncio.StreamReader) -> bytes:
        header_data = await self._handle_read_bytes(reader, 4)
        if len(header_data) == 4:
            msg_len = struct.unpack("<L", header_data)[0]
            data = await self._handle_read_bytes(reader, msg_len)
            if len(data) == msg_len:
                return data
        return b""

    async def _handle_read_bytes(
        self, reader: asyncio.StreamReader, msg_len: int
    ) -> bytes:
        data = "".encode("utf-8")
        while len(data) < msg_len:
            chunk = await reader.read(msg_len - len(data))
            if not chunk:
                break
            data += chunk
        return data

    async def send(self, data: bytes, writer: asyncio.StreamWriter) -> None:
        header = struct.pack("<L", len(data))
        writer.write(header + data)
        await writer.drain()
