import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
SERVER = os.path.join(ROOT, "server.py")


class CacheServerTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="cache-test-", dir=ROOT)
        self.db_path = os.path.join(self.tmpdir, "state.json")
        self.proc = subprocess.Popen(
            [sys.executable, SERVER, "--port", "0", "--db", self.db_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.port = self._read_port()

    def tearDown(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=3)
        for name in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, name))
        os.rmdir(self.tmpdir)

    def _send(self, command: str) -> str:
        if self.proc.poll() is not None:
            raise AssertionError(self.proc.stdout.read())
        with socket.create_connection(("127.0.0.1", self.port), timeout=2) as sock:
            sock.sendall(command.encode("utf-8"))
            sock.shutdown(socket.SHUT_WR)
            return sock.recv(4096).decode("utf-8")

    def _read_port(self) -> int:
        if self.proc.poll() is not None:
            raise AssertionError(self.proc.stdout.read())
        line = self.proc.stdout.readline().strip()
        if not line:
            raise AssertionError("server did not report a port")
        return int(line)

    def test_set_get_and_ttl(self):
        self.assertEqual(self._send("SET a 1 2\n"), "OK")
        self.assertEqual(self._send("GET a\n"), "1")
        time.sleep(2.2)
        self.assertEqual(self._send("GET a\n"), "NULL")

    def test_lru_eviction(self):
        self.assertEqual(self._send("SET a 1 100\n"), "OK")
        self.assertEqual(self._send("SET b 2 100\n"), "OK")
        self.assertEqual(self._send("GET a\n"), "1")
        self.assertEqual(self._send("SET c 3 100\n"), "OK")
        self.assertEqual(self._send("GET b\n"), "NULL")

    def test_lfu_eviction(self):
        self.assertEqual(self._send("SET a 1 100\n"), "OK")
        self.assertEqual(self._send("SET b 2 100\n"), "OK")
        self.assertEqual(self._send("GET a\n"), "1")
        self.assertEqual(self._send("GET a\n"), "1")
        self.assertEqual(self._send("SET c 3 100\n"), "OK")
        self.assertEqual(self._send("GET b\n"), "NULL")

    def test_get_distinguishes_missing_key_from_empty_string(self):
        self.assertEqual(self._send('SET a "" 100\n'), "OK")
        self.assertEqual(self._send("GET a\n"), "")
        self.assertEqual(self._send("GET missing\n"), "NULL")

    def test_malformed_set_returns_error(self):
        self.assertEqual(self._send("SET a hello world 10\n"), "ERR")

    def test_get_does_not_rewrite_persistence_file(self):
        self.assertEqual(self._send("SET a 1 100\n"), "OK")
        deadline = time.time() + 1.0
        while not os.path.exists(self.db_path) and time.time() < deadline:
            time.sleep(0.01)
        before = os.stat(self.db_path).st_mtime_ns
        time.sleep(0.05)
        self.assertEqual(self._send("GET a\n"), "1")
        after = os.stat(self.db_path).st_mtime_ns
        self.assertEqual(before, after)

    def test_persists_state_to_disk(self):
        self.assertEqual(self._send("SET a 1 100\n"), "OK")
        self._send("QUIT\n")
        self.proc.wait(timeout=3)
        self.assertTrue(os.path.exists(self.db_path))
        with open(self.db_path, "r", encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn("a", content)


if __name__ == "__main__":
    unittest.main()
