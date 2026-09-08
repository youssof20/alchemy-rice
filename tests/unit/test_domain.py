from __future__ import annotations

import unittest

from alchemy.domain.capabilities import CapabilityMatrix, ComponentCapability


class CapabilityMatrixTests(unittest.TestCase):
    def test_serialization_does_not_mutate_immutable_domain_state(self) -> None:
        matrix = CapabilityMatrix(
            host_os="linux",
            plasma_version="6.7.4",
            session="wayland",
            desktop="KDE",
            login_manager=None,
            distro="arch",
            distro_version="rolling",
            package_manager="pacman",
            aur_helper=None,
            portals=("screenshot",),
            plasma_apply=("colorscheme",),
            union=ComponentCapability(None, None),
            nix=ComponentCapability(False, False),
            plasma_manager=ComponentCapability(False, False),
            monitors=("eDP-1",),
            mixed_scale=False,
            immutable_host=False,
            apply_supported=False,
        )

        payload = matrix.to_dict()
        payload["session"] = "x11"

        self.assertEqual(matrix.session, "wayland")


if __name__ == "__main__":
    unittest.main()
