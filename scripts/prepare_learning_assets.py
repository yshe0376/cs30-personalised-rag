"""Create the auditable local Topic-map sidecar required by the API Demo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cs30.learning.assets import prepare_topic_map_binding  # noqa: E402
from cs30.learning.config import LearningConfig  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    config = LearningConfig.load(args.config)
    path = prepare_topic_map_binding(
        config.source_topic_map_path,
        config.corpus_dir,
        config.topic_registry_path,
        config.topic_map_path,
    )
    print(f"Validated rebound Topic map written to: {path}")
    print(f"Source preserved at: {config.source_topic_map_path}")


if __name__ == "__main__":
    main()
