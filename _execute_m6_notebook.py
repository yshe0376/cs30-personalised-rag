import argparse
from pathlib import Path

import nbformat
from nbclient import NotebookClient

root = Path(__file__).resolve().parent
path = root / "M6_W5_retrieval_dev_test.ipynb"
parser = argparse.ArgumentParser(description="Execute the M6 W5 handoff notebook.")
parser.add_argument(
    "--output",
    type=Path,
    default=path,
    help="Executed notebook destination; use an ignored artifacts path for a clean Git run.",
)
args = parser.parse_args()
notebook = nbformat.read(path, as_version=4)
client = NotebookClient(
    notebook,
    timeout=900,
    kernel_name="python3",
    resources={"metadata": {"path": str(root)}},
)
client.execute()
destination = args.output.resolve()
destination.parent.mkdir(parents=True, exist_ok=True)
nbformat.write(notebook, destination)
print(destination)
