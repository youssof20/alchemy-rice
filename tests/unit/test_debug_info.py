from __future__ import annotations

import getpass
import socket
import unittest
from pathlib import Path

from alchemy.services.debug_info import redact


class DebugInfoTests(unittest.TestCase):
    def test_redacts_local_identity_and_network_values(self) -> None:
        original = (
            f"user={getpass.getuser()} host={socket.gethostname()} home={Path.home()} "
            "ip=192.168.1.42 mac=aa:bb:cc:dd:ee:ff api_key=supersecret"
        )

        redacted = redact(original)

        self.assertNotIn(getpass.getuser(), redacted)
        self.assertNotIn(socket.gethostname(), redacted)
        self.assertNotIn(str(Path.home()), redacted)
        self.assertNotIn("192.168.1.42", redacted)
        self.assertNotIn("aa:bb:cc:dd:ee:ff", redacted.lower())
        self.assertNotIn("supersecret", redacted)


if __name__ == "__main__":
    unittest.main()
