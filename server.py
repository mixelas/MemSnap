import argparse
import json
import os
import socket
import threading
import time
from collections import OrderedDict


class CacheEntry:
    def __init__(self, value: str, ttl_seconds: int):
        self.value = value
        self.expires_at = None if ttl_seconds <= 0 else time.time() + ttl_seconds
        self.freq = 1


class CacheServer:
    def __init__(self, host: str, port: int, db_path: str, max_entries: int = 128, policy: str = "lru"):
        self.host = host
        self.port = port
        self.db_path = db_path
        self.max_entries = max_entries
        self.policy = policy
        self.store = {}
        self.lru_order = OrderedDict()
        self.lfu_buckets = {}
        self.min_freq = 1
        self.lock = threading.RLock()
        self.shutdown_event = threading.Event()
        self.server_socket = None
        self._dirty = False
        self._persist_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._persist_thread.start()
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.db_path):
            return
        with open(self.db_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        now = time.time()
        for key, item in payload.items():
            ttl = item.get("ttl_seconds", -1)
            expires_at = None if ttl <= 0 else now + ttl
            if expires_at is not None and expires_at <= now:
                continue
            entry = CacheEntry(item["value"], ttl)
            self.store[key] = entry
            if self.policy == "lru":
                self.lru_order[key] = None
            else:
                self._add_lfu_bucket(key, 1)

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _flush_loop(self) -> None:
        while not self.shutdown_event.is_set():
            time.sleep(0.2)
            if self._dirty:
                with self.lock:
                    if self._dirty:
                        self._persist()
                        self._dirty = False

    def _persist(self) -> None:
        payload = {}
        now = time.time()
        for key, entry in self.store.items():
            if entry.expires_at is not None and entry.expires_at <= now:
                continue
            ttl = -1
            if entry.expires_at is not None:
                ttl = max(0, int(entry.expires_at - now))
            payload[key] = {"value": entry.value, "ttl_seconds": ttl}
        directory = os.path.dirname(self.db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.db_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)

    def _prune_expired(self) -> None:
        now = time.time()
        expired = [key for key, entry in self.store.items() if entry.expires_at is not None and entry.expires_at <= now]
        for key in expired:
            self._remove_entry(key)

    def _add_lfu_bucket(self, key: str, freq: int) -> None:
        bucket = self.lfu_buckets.setdefault(freq, OrderedDict())
        bucket[key] = None
        if freq < self.min_freq:
            self.min_freq = freq

    def _remove_from_lfu_bucket(self, key: str, freq: int) -> None:
        bucket = self.lfu_buckets.get(freq)
        if not bucket:
            return
        bucket.pop(key, None)
        if not bucket:
            self.lfu_buckets.pop(freq, None)
            if freq == self.min_freq:
                self.min_freq = min(self.lfu_buckets.keys(), default=1)

    def _remove_entry(self, key: str) -> None:
        entry = self.store.pop(key, None)
        if entry is None:
            return
        if self.policy == "lru":
            self.lru_order.pop(key, None)
        else:
            self._remove_from_lfu_bucket(key, entry.freq)
        self._mark_dirty()

    def _touch(self, key: str) -> None:
        if self.policy == "lru":
            if key in self.lru_order:
                self.lru_order.move_to_end(key)
        else:
            entry = self.store.get(key)
            if entry is None:
                return
            old_freq = entry.freq
            self._remove_from_lfu_bucket(key, old_freq)
            entry.freq = old_freq + 1
            self._add_lfu_bucket(key, entry.freq)

    def _evict_one(self) -> None:
        if self.policy == "lru":
            if not self.lru_order:
                return
            key, _ = self.lru_order.popitem(last=False)
            self.store.pop(key, None)
            self._mark_dirty()
            return
        if not self.lfu_buckets:
            return
        bucket = self.lfu_buckets.get(self.min_freq)
        if bucket is None:
            self.min_freq = min(self.lfu_buckets.keys(), default=1)
            bucket = self.lfu_buckets.get(self.min_freq)
        if bucket is None:
            return
        victim, _ = bucket.popitem(last=False)
        if not bucket:
            self.lfu_buckets.pop(self.min_freq, None)
            self.min_freq = min(self.lfu_buckets.keys(), default=1)
        self.store.pop(victim, None)
        self._mark_dirty()

    def set(self, key: str, value: str, ttl_seconds: int) -> str:
        with self.lock:
            if not key:
                return "ERR"
            if ttl_seconds < 0:
                return "ERR"
            if key in self.store:
                self._remove_entry(key)
            if len(self.store) >= self.max_entries:
                self._prune_expired()
            if len(self.store) >= self.max_entries:
                self._evict_one()
            entry = CacheEntry(value, ttl_seconds)
            self.store[key] = entry
            if self.policy == "lru":
                self.lru_order[key] = None
                self.lru_order.move_to_end(key)
            else:
                self._add_lfu_bucket(key, 1)
            self._mark_dirty()
            return "OK"

    def get(self, key: str) -> str:
        with self.lock:
            entry = self.store.get(key)
            if entry is None:
                return "NULL"
            if entry.expires_at is not None and entry.expires_at <= time.time():
                self._remove_entry(key)
                return "NULL"
            self._touch(key)
            return entry.value

    def serve(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((self.host, self.port))
            server.listen(5)
            self.server_socket = server
            port = server.getsockname()[1]
            print(port, flush=True)
            server.settimeout(0.5)
            while not self.shutdown_event.is_set():
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()

    def _handle_client(self, conn: socket.socket) -> None:
        with conn:
            data = conn.recv(4096).decode("utf-8", errors="ignore")
            if not data:
                return
            raw = data.strip()
            if not raw:
                return
            parts = raw.split(None, 3)
            if not parts:
                return
            command = parts[0].upper()
            if command == "SET":
                if len(parts) != 4:
                    response = "ERR"
                else:
                    try:
                        ttl = int(parts[3])
                    except ValueError:
                        response = "ERR"
                    else:
                        value = parts[2]
                        if value in {'""', "''"}:
                            value = ""
                        response = self.set(parts[1], value, ttl)
            elif command == "GET" and len(parts) >= 2:
                response = self.get(parts[1])
            elif command == "QUIT":
                response = "OK"
                self.shutdown_event.set()
                self._mark_dirty()
                self._persist()
                if self.server_socket is not None:
                    try:
                        self.server_socket.close()
                    except OSError:
                        pass
            else:
                response = "ERR"
            conn.sendall(response.encode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=6380, type=int)
    parser.add_argument("--db", default="cache_state.json")
    parser.add_argument("--max-entries", default=2, type=int)
    parser.add_argument("--policy", default="lru", choices=["lru", "lfu"])
    args = parser.parse_args()
    server = CacheServer(args.host, args.port, args.db, max_entries=args.max_entries, policy=args.policy)
    server.serve()


if __name__ == "__main__":
    main()
