import socket

from hostfront_manager.diagnostics import _check_tcp_listener


def test_runtime_tcp_listener_detects_down_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.listen(1)
    try:
        assert _check_tcp_listener(port).ok is True
    finally:
        sock.close()
    assert _check_tcp_listener(port).ok is False
