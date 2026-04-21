"""Command-line utility for downloading bags without GUI."""
from __future__ import annotations

import argparse
from pathlib import Path

from dateutil import parser as date_parser

from bagfetcher.core.bag_service import BagService
from bagfetcher.core.sshclient import SSHClientWrapper


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download robot bag files")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--user", default="gaussian")
    parser.add_argument("--password", default=None)
    parser.add_argument("--bag-dir", default="/root/GAUSSIAN_RUNTIME_DIR/bag")
    parser.add_argument("--stage-dir", default="/root/public/tmp")
    parser.add_argument("--local-dir", type=Path, required=True)
    parser.add_argument("--from", dest="from_dt", help="Start datetime, e.g. '2025-11-06 09:10'")
    parser.add_argument("--to", dest="to_dt", help="End datetime, e.g. '2025-11-06 09:15'")
    parser.add_argument("--cleanup", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ssh = SSHClientWrapper(args.host, args.port, args.user, args.password)
    ssh.connect()
    service = BagService(ssh, args.bag_dir, args.stage_dir)
    bags = service.fetch_index()
    if not bags:
        print("No bags to download")
        return 0

    from_dt = date_parser.parse(args.from_dt) if args.from_dt else min(bag.dt for bag in bags)
    to_dt = date_parser.parse(args.to_dt) if args.to_dt else max(bag.dt for bag in bags)
    selected = service.filter_by_time(bags, from_dt, to_dt)
    if not selected:
        print("No bags found in requested time range")
        return 0

    print(f"Downloading {len(selected)} bag(s) between {from_dt} and {to_dt}...")

    def progress(name: str, transferred: int, total: int) -> None:
        percent = (transferred / total) * 100 if total else 0
        print(f"\r{name}: {percent:5.1f}%", end="", flush=True)

    service.stage_and_download(selected, args.local_dir, args.cleanup, progress_cb=progress)
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
