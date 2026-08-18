"""Live diagnostic tool for the ve7cc.net CC Cluster telnet connection.

Run this before relying on cluster.py's ClusterConnection - it prints the raw
handshake and server responses so login/filter behavior can be eyeballed
against a real connection.

Usage:
    py cluster_debug.py                  # handshake only, print for 10s
    py cluster_debug.py --probe          # handshake + filter setup, print for 15s
    py cluster_debug.py --interactive    # type raw commands, see raw responses
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time

HOST = "ve7cc.net"
PORT = 23
CALLSIGN = "N6YU"
LOGIN_WAIT_S = 2.0
SKIMMER_WAIT_S = 0.5
FILTER_CMD_WAIT_S = 0.3


def _reader_thread(sock: socket.socket, stop: threading.Event) -> None:
    fh = sock.makefile("r", errors="replace")
    try:
        for line in fh:
            if stop.is_set():
                break
            print(f"<< {line.rstrip()}")
    except OSError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true", help="also send filter setup commands")
    parser.add_argument("--interactive", action="store_true", help="type raw commands after login")
    args = parser.parse_args()

    print(f">> connecting to {HOST}:{PORT} ...")
    sock = socket.create_connection((HOST, PORT), timeout=30.0)
    sock.settimeout(None)
    stop = threading.Event()
    reader = threading.Thread(target=_reader_thread, args=(sock, stop), daemon=True)
    reader.start()

    print(f">> {CALLSIGN}")
    sock.sendall((CALLSIGN + "\r\n").encode())
    time.sleep(LOGIN_WAIT_S)

    print(">> SET/SKIMMER")
    sock.sendall(b"SET/SKIMMER\r\n")
    time.sleep(SKIMMER_WAIT_S)

    if args.probe:
        for cmd in [
            "UNSET/FILTER",
            "SET/NOFT8",
            "SET/NOFT4",
            "SET/NORTTY",
            "SET/FILTER DXBM/REJECT 160,80,60,40,30,17,15,12,10,6",
            "SH/FILTER",
        ]:
            print(f">> {cmd}")
            sock.sendall((cmd + "\r\n").encode())
            time.sleep(FILTER_CMD_WAIT_S)
        time.sleep(15.0)
    elif args.interactive:
        print(">> interactive mode - type commands, Ctrl-C to quit")
        try:
            while True:
                cmd = input()
                sock.sendall((cmd + "\r\n").encode())
        except (KeyboardInterrupt, EOFError):
            pass
    else:
        time.sleep(10.0)

    stop.set()
    try:
        sock.close()
    except OSError:
        pass
    print(">> closed")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
