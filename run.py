"""
run.py — Entry point for the QuizBlitz Flask application.

    python run.py                      # serve on the local network (phones can join)
    QUIZBLITZ_DEBUG=1 python run.py    # debug + auto-reload, this machine only

Environment:
    QUIZBLITZ_HOST   interface to bind (default 0.0.0.0 = all, so phones on the Wi-Fi can connect)
    QUIZBLITZ_PORT   port (default 5000)
    QUIZBLITZ_DEBUG  1/true to enable debug mode (forces host 127.0.0.1, see below)

This is for a trusted local network. For the public site see DEPLOY.md.
"""

import os
import socket

from app import create_app, socketio
from app.cli import upgrade_database

app = create_app()


def _lan_ip() -> str | None:
    """This machine's address on the local network (no packets are sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.255.255.255", 1))
            return probe.getsockname()[0]
    except OSError:
        return None


def main() -> None:
    host = os.environ.get("QUIZBLITZ_HOST", "0.0.0.0")
    port = int(os.environ.get("QUIZBLITZ_PORT", "5000"))
    debug = os.environ.get("QUIZBLITZ_DEBUG", "").lower() in {"1", "true", "yes"}

    # Debug mode serves Werkzeug's interactive debugger, which lets anyone who can reach
    # the server run code on this machine. Never expose it beyond localhost.
    if debug and host not in {"127.0.0.1", "localhost"}:
        print(f"[!] QUIZBLITZ_DEBUG is on: binding to 127.0.0.1 instead of {host} (phones can't join in debug mode).")
        host = "127.0.0.1"

    lan_ip = _lan_ip() if host == "0.0.0.0" else None
    print(f"[*] QuizBlitz running on port {port}")
    if lan_ip:
        # The lobby QR code encodes whatever address the master's browser used,
        # so the master must use the network address, not localhost.
        print(f"    Quiz master: open http://{lan_ip}:{port} on this computer (not localhost), so")
        print("    the lobby QR code points somewhere phones on the same Wi-Fi can reach.")
    else:
        print(f"    Open http://{host}:{port}")

    upgrade_database(app)

    # socketio.run (not app.run) also serves the Socket.IO transport, so live game updates work.
    # allow_unsafe_werkzeug: this entry point is for a trusted local network. The public
    # site runs wsgi.py under Gunicorn (see DEPLOY.md).
    socketio.run(app, host=host, port=port, debug=debug, use_reloader=debug, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
