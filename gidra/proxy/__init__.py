from __future__ import annotations

import base64
from enum import Enum
from threading import Thread
from typing import Callable

from betterproto import Message
from loguru import logger

from gidra.proxy.cmdids import CmdID
from gidra.proxy.kcp_socket import KcpSocket, _Address
from gidra.proxy.packet import Packet

Handler = Callable[['StarRailProxy', Message], None]


class PacketDirection(Enum):
    Client = 0
    Server = 1


class HandlerRouter:
    _handlers: dict[tuple[CmdID, PacketDirection], Handler]

    def __init__(self):
        self._handlers = {}

    def add(self, router: HandlerRouter):
        self._handlers |= router._handlers

    def get(self, cmdid: CmdID, source: PacketDirection) -> Handler | None:
        return self._handlers.get((cmdid, source))

    def __call__(self, cmdid: CmdID, source: PacketDirection):
        def wrapper(handler: Handler):
            self._handlers[(cmdid, source)] = handler
            return handler
        return wrapper


class ServerProxy(Thread):
    client_proxy: ClientProxy

    def __init__(self, proxy: StarRailProxy, addr: _Address):
        self.proxy = proxy
        self.proxy_server_addr = addr
        self.sock = KcpSocket()
        super().__init__(daemon=True)

    def run(self):
        if not self.sock.bind(self.proxy_server_addr):
            logger.error('[C] can\'t bind')
            return

        logger.info('[C] binded')
        while True:
            data = self.sock.recv()
            # logger.debug(f'[C] {data.hex()}')
            self.proxy.handle(data, PacketDirection.Server)

class ClientProxy(Thread):
    server_proxy: ServerProxy

    def __init__(self, proxy: StarRailProxy, addr: _Address):
        self.proxy = proxy
        self.server_addr = addr
        self.sock = KcpSocket()
        super().__init__(daemon=True)

    def run(self):
        if not self.sock.connect(self.server_addr):
            logger.error('[S] can\'t connect')
            return

        logger.info('[S] connected')
        while True:
            data = self.sock.recv()
            # logger.debug(f'[S] {data.hex()}')
            self.proxy.handle(data, PacketDirection.Client)


class StarRailProxy:
    def __init__(self, src_addr: _Address, dst_addr: _Address):
        self.router = HandlerRouter()
        self.src_addr = src_addr
        self.dst_addr = dst_addr

    def add(self, router: HandlerRouter):
        self.router.add(router)

    def handle(self, data: bytes, direction: PacketDirection):
        try:
            packet = Packet().parse(data)
        except Exception:
            logger.debug(f'{PacketDirection(direction.value ^ 1).name} -> {direction.name}: {data.hex()}')
            self.send_raw(data, direction)
            return

        logger.debug(f'{PacketDirection(direction.value ^ 1).name} -> {direction.name} {packet.cmdid}: {packet.body.__class__.__name__}')

        if handler := self.router.get(packet.cmdid, PacketDirection(direction.value ^ 1)):
            handler(self, packet.body)
        else:
            self.send_raw(data, direction)

    def send(self, msg: Message, direction: PacketDirection):
        packet = Packet(body=msg)
        self.send_raw(bytes(packet), direction)

    def send_raw(self, data: bytes, direction: PacketDirection):
        match direction:
            case PacketDirection.Server: self.client_proxy.sock.send(data)
            case PacketDirection.Client: self.server_proxy.sock.send(data)

    def start(self):
        self.server_proxy = ServerProxy(self, self.src_addr)
        self.client_proxy = ClientProxy(self, self.dst_addr)

        self.server_proxy.client_proxy = self.client_proxy
        self.client_proxy.server_proxy = self.server_proxy

        self.server_proxy.start()
        self.client_proxy.start()
