import socket

from config import available_port


def test_available_port_skips_occupied_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        port = occupied.getsockname()[1]
        selected = available_port(port)
        assert selected > port
        assert selected < port + 20
