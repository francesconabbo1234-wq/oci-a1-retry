"""Minecraft Server List Ping (what the multiplayer screen does): prints version, players and MOTD.
Usage: python mc_ping.py HOST [PORT]. Exit code 0 only if the server answered."""
import json, socket, struct, sys


def varint(n):
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        out += struct.pack("B", b | (0x80 if n else 0))
        if not n:
            return out


def read_varint(s):
    n = shift = 0
    while True:
        b = s.recv(1)[0]
        n |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            return n


host = sys.argv[1]
port = int(sys.argv[2]) if len(sys.argv) > 2 else 25565
with socket.create_connection((host, port), timeout=10) as s:
    h = host.encode()
    # packet 0, protocol (any number works for a status request), address, port, next state 1 = status
    handshake = varint(0) + varint(772) + varint(len(h)) + h + struct.pack(">H", port) + varint(1)
    s.sendall(varint(len(handshake)) + handshake)
    s.sendall(varint(1) + varint(0))
    read_varint(s)  # packet length
    read_varint(s)  # packet id
    size = read_varint(s)
    data = b""
    while len(data) < size:
        chunk = s.recv(size - len(data))
        if not chunk:
            break
        data += chunk
status = json.loads(data)
desc = status.get("description")
motd = desc.get("text", "") if isinstance(desc, dict) else desc
print("version:", status["version"]["name"], "| players:", status["players"]["online"], "/", status["players"]["max"], "| motd:", motd)
