"""The release wheel builds every advertised transport.

Development wheels cannot prove which services a custom release wheel compiled.
"""

from __future__ import annotations

import re

from tests.paths import BACKEND_DIR


class TestStorageImage:
    def test_builds_the_required_s3_service(self) -> None:
        dockerfile = (BACKEND_DIR / "Dockerfile").read_text()

        feature_line = re.search(r"--features\s+([^\s]+)", dockerfile)

        assert feature_line is not None
        assert "services-s3" in feature_line.group(1).split(",")
