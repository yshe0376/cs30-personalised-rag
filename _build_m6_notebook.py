from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

ROOT = Path(__file__).resolve().parent
NOTEBOOK = ROOT / "M6_W5_retrieval_dev_test.ipynb"


cells = [
    new_markdown_cell(
        """# M6 W5 Retrieval Evaluation and Handoff

## TL;DR

This notebook is the reproducible M6 handoff for BM25, Dense, and Hybrid retrieval.
It uses the repository interfaces, the official M4/M5 artifact layout, MiniLM as the
primary model, `top_k=5`, and Hit/Recall at 1, 3, and 5 plus MRR.

The notebook automatically runs real retrieval and Dev evaluation when the official
artifacts are present. If an artifact is missing, it reports the exact missing path
instead of presenting fixture output as a real result. The proposed Test split remains
locked until `CS30_RUN_FROZEN_TEST=1` is explicitly set after one Dev configuration is
frozen."""
    ),
    new_markdown_cell(
        """## Context and methods

### Key assumptions

- M4 artifacts follow `artifacts/w5/m4-v3/`.
- M5's primary MiniLM index follows
  `artifacts/w5/m5_latest/all-minilm-l6-v2/`.
- All three retrieval modes must report the same `corpus_hash`,
  `chunk_config_hash`, and `index_version`.
- The current 20-question Gold set is answerable-only. Refusal checks below are
  controlled engineering gates, not evidence of a calibrated production threshold.
- Dev selects the configuration. Test is run once only after the configuration is frozen."""
    ),
    new_code_cell(
        """from __future__ import annotations

import hashlib
import inspect
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import cs30


def find_project_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / 'pyproject.toml').is_file():
            return candidate
    raise RuntimeError('Run this notebook from inside the cs30-personalised-rag checkout.')


PROJECT_ROOT = find_project_root(Path.cwd().resolve())
LOCAL_VENV = (PROJECT_ROOT / '.venv').resolve()
PYTHON = Path(sys.executable).resolve()
PACKAGE_SOURCE = Path(inspect.getfile(cs30)).resolve()

git_candidates = (
    Path(os.environ['GIT_EXECUTABLE']) if os.environ.get('GIT_EXECUTABLE') else None,
    Path(shutil.which('git')) if shutil.which('git') else None,
    Path('C:/Program Files/Git/cmd/git.exe'),
    Path.home() / '.cache' / 'codex-runtimes' / 'codex-primary-runtime'
    / 'dependencies' / 'native' / 'git' / 'cmd' / 'git.exe',
)
GIT_EXECUTABLE = next(
    (candidate.resolve() for candidate in git_candidates if candidate and candidate.is_file()),
    None,
)
if GIT_EXECUTABLE is not None:
    os.environ['PATH'] = str(GIT_EXECUTABLE.parent) + os.pathsep + os.environ['PATH']

assert LOCAL_VENV in PYTHON.parents, (
    f'Wrong Python environment: {PYTHON}. Select {LOCAL_VENV / "Scripts" / "python.exe"}.'
)
assert PROJECT_ROOT in PACKAGE_SOURCE.parents, (
    f'cs30 was imported from another checkout: {PACKAGE_SOURCE}'
)

print('Project root:', PROJECT_ROOT)
print('Python:', PYTHON)
print('cs30 source:', PACKAGE_SOURCE)"""
    ),
    new_markdown_cell("## Inputs and experiment policy"),
    new_code_cell(
        """from cs30.contracts import RetrievalMode
from cs30.retrieval.model_policy import (
    CANDIDATE_EMBEDDING_MODELS,
    PRIMARY_EMBEDDING_MODEL,
)

TOP_K = 5
K_VALUES = (1, 3, 5)
SMOKE_QUESTION = 'What is acceleration?'

M4_ROOT = PROJECT_ROOT / 'artifacts' / 'w5' / 'm4-v3'
PREPARED_CORPUS_DIR = M4_ROOT / 'prepared_corpus'
PREPARED_DOCUMENT = PREPARED_CORPUS_DIR / 'openstax_document.json'
PREPARED_CORPUS_MANIFEST = PREPARED_CORPUS_DIR / 'corpus_manifest.json'
EVIDENCE_SOURCE_BLOCKS = PREPARED_CORPUS_DIR / 'evidence_source_blocks.jsonl'
NORMALIZED_GOLD = M4_ROOT / 'gold_normalized' / 'gold_v0_2_from_m3_v0_1_1.jsonl'
GOLD_MAPPING = M4_ROOT / 'gold_mapping' / 'evaluation_mapping_v0_1.json'

M5_ROOT = PROJECT_ROOT / 'artifacts' / 'w5' / 'm5_latest'
PRIMARY_INDEX_DIR = M5_ROOT / 'all-minilm-l6-v2'
M6_OUTPUT_ROOT = PROJECT_ROOT / 'artifacts' / 'w5' / 'm6'


def model_slug(model_name: str) -> str:
    return model_name.rsplit('/', 1)[-1].lower()


MODEL_EXPERIMENTS = [
    {
        'experiment_id': 'w5-minilm-primary-v1',
        'model': PRIMARY_EMBEDDING_MODEL,
        'index_dir': PRIMARY_INDEX_DIR,
        'role': 'primary',
    },
    *[
        {
            'experiment_id': f'w5-{model_slug(model)}-candidate-v1',
            'model': model,
            'index_dir': M5_ROOT / model_slug(model),
            'role': 'candidate',
        }
        for model in CANDIDATE_EMBEDDING_MODELS
    ],
]
RRF_WEIGHT_CANDIDATES = ((0.75, 0.25), (0.50, 0.50), (0.25, 0.75))
for candidate_model in CANDIDATE_EMBEDDING_MODELS:
    for dense_weight, bm25_weight in RRF_WEIGHT_CANDIDATES:
        if (dense_weight, bm25_weight) == (0.50, 0.50):
            continue
        MODEL_EXPERIMENTS.append(
            {
                'experiment_id': (
                    f'w5-{model_slug(candidate_model)}-rrf-'
                    f'{int(dense_weight * 100)}-{int(bm25_weight * 100)}-v1'
                ),
                'model': candidate_model,
                'index_dir': M5_ROOT / model_slug(candidate_model),
                'role': 'candidate_rrf',
                'weights': (dense_weight, bm25_weight),
            }
        )

RUN_CANDIDATE_EXPERIMENTS = os.getenv('CS30_RUN_CANDIDATES', '0') == '1'
RUN_FROZEN_TEST = os.getenv('CS30_RUN_FROZEN_TEST', '0') == '1'
ALLOW_DIRTY_LOCAL = os.getenv('CS30_ALLOW_DIRTY_LOCAL', '0') == '1'
FROZEN_EXPERIMENT_ID = os.getenv('CS30_FROZEN_EXPERIMENT_ID', 'w5-minilm-primary-v1')
FROZEN_RETRIEVAL_MODE = os.getenv('CS30_FROZEN_RETRIEVAL_MODE', 'hybrid')

print('Top-K:', TOP_K)
print('K values:', K_VALUES)
for experiment in MODEL_EXPERIMENTS:
    print(
        experiment['role'], experiment['experiment_id'],
        experiment['model'], experiment['index_dir'],
    )"""
    ),
    new_markdown_cell("## Data and artifact validation"),
    new_code_cell(
        """RAW_GOLD = PROJECT_ROOT / 'm3_gold' / 'gold_v0_1_1.jsonl'
gold_records = [
    json.loads(line)
    for line in RAW_GOLD.read_text(encoding='utf-8').splitlines()
    if line.strip()
]
dev_records = [row for row in gold_records if row['split'] == 'proposed_dev']
test_records = [row for row in gold_records if row['split'] == 'proposed_test']

assert len(gold_records) == 20
assert len(dev_records) == 12
assert len(test_records) == 8
assert {row['question_id'] for row in dev_records}.isdisjoint(
    {row['question_id'] for row in test_records}
)
assert all(row['answerable'] is True for row in gold_records)

print('Gold split counts:', Counter(row['split'] for row in gold_records))
print('Answerable records:', sum(row['answerable'] is True for row in gold_records))
print('Production refusal calibration available:', False)"""
    ),
    new_code_cell(
        """M4_REQUIRED = (
    PREPARED_DOCUMENT,
    PREPARED_CORPUS_MANIFEST,
    EVIDENCE_SOURCE_BLOCKS,
    NORMALIZED_GOLD,
    GOLD_MAPPING,
)


def index_required(index_dir: Path) -> tuple[Path, ...]:
    return (
        index_dir / 'artifact.json',
        index_dir / 'chunks.json',
        index_dir / 'index.faiss',
    )


def missing_files(paths: tuple[Path, ...]) -> list[Path]:
    return [path for path in paths if not path.is_file()]


INDEX_MISSING = missing_files(index_required(PRIMARY_INDEX_DIR))
M4_MISSING = missing_files(M4_REQUIRED)
PRIMARY_MISSING = M4_MISSING + INDEX_MISSING
RUN_REAL_RETRIEVAL = not INDEX_MISSING
RUN_PRIMARY_DEV = not PRIMARY_MISSING

if PRIMARY_MISSING:
    print('The primary workflow is pending these official inputs:')
    for path in PRIMARY_MISSING:
        print(' -', path.relative_to(PROJECT_ROOT))
else:
    print('All primary M4/M5 inputs are present; real retrieval and Dev evaluation are enabled.')

if GIT_EXECUTABLE is None and RUN_PRIMARY_DEV:
    raise FileNotFoundError('Git is required by the evaluation CLI; set GIT_EXECUTABLE.')

if RUN_PRIMARY_DEV and not ALLOW_DIRTY_LOCAL:
    git_check = subprocess.run(
        [str(GIT_EXECUTABLE), 'status', '--porcelain'],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    if git_check.stdout.strip():
        raise RuntimeError(
            'The checkout must be clean for reportable runs. '
            'Set CS30_ALLOW_DIRTY_LOCAL=1 only for explicitly non-reportable local validation.'
        )

if RUN_FROZEN_TEST and PRIMARY_MISSING:
    raise FileNotFoundError(
        'Frozen Test was requested, but official M4/M5 inputs are incomplete.'
    )"""
    ),
    new_markdown_cell("## Automated retrieval and refusal gates"),
    new_code_cell(
        """test_command = [
    sys.executable,
    '-m',
    'pytest',
    '-q',
    'tests/test_real_retrieval.py',
    'tests/test_m6_w5_refusal.py',
    'tests/test_m6_model_policy.py',
    'tests/test_config_knob_reachability.py',
]
print('Running:', subprocess.list2cmdline(test_command))
subprocess.run(test_command, cwd=PROJECT_ROOT, check=True)
print('Retrieval, provenance, model-policy, configuration, and controlled-refusal gates passed.')"""
    ),
    new_markdown_cell(
        """## Real BM25, Dense, and Hybrid smoke check

The checks below validate rank order, result count, duplicate IDs, source fields,
and provenance. The three modes must use the same corpus, chunk configuration,
and index version."""
    ),
    new_code_cell(
        """from cs30.config import AppConfig, RetrievalConfig
from cs30.pipeline import build_real_retrieval_deps


def make_retrieval_config(
    mode: RetrievalMode,
    *,
    index_dir: Path,
    expected_model: str,
    dense_weight: float = 1.0,
    bm25_weight: float = 1.0,
) -> AppConfig:
    return AppConfig(
        environment='staging',
        fixture_mode=False,
        retrieval=RetrievalConfig(
            mode=mode,
            top_k=TOP_K,
            index_dir=str(index_dir),
            expected_embedding_model=expected_model,
            rrf_dense_weight=dense_weight,
            rrf_bm25_weight=bm25_weight,
        ),
    )


def run_three_mode_smoke(experiment: dict[str, object]) -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    provenance_identities: set[tuple[str, str, str]] = set()
    output_dir = M6_OUTPUT_ROOT / 'smoke' / str(experiment['experiment_id'])
    output_dir.mkdir(parents=True, exist_ok=True)

    for mode in (RetrievalMode.BM25, RetrievalMode.DENSE, RetrievalMode.HYBRID):
        config = make_retrieval_config(
            mode,
            index_dir=Path(experiment['index_dir']),
            expected_model=str(experiment['model']),
        )
        result = build_real_retrieval_deps(config).retriever.retrieve(
            SMOKE_QUESTION,
            top_k=TOP_K,
        )
        assert len(result.hits) <= TOP_K
        assert [hit.rank for hit in result.hits] == list(range(1, len(result.hits) + 1))
        assert len({hit.chunk_id for hit in result.hits}) == len(result.hits)
        assert all(hit.source.strip() for hit in result.hits)
        assert result.provenance is not None

        provenance = result.provenance
        provenance_identities.add(
            (provenance.corpus_hash, provenance.chunk_config_hash, provenance.index_version)
        )
        payload = result.model_dump(mode='json')
        results[mode.value] = payload

        print(f'\\n{mode.value}: {len(result.hits)} results')
        for hit in result.hits:
            print(
                f'  rank={hit.rank} chunk_id={hit.chunk_id} '
                f'source={hit.source} score={hit.score:.6f}'
            )

    assert len(provenance_identities) == 1, (
        'BM25, Dense, and Hybrid did not use the same corpus/index provenance.'
    )

    raw_path = output_dir / 'raw_rankings.jsonl'
    raw_path.write_text(
        ''.join(
            json.dumps({'mode': mode, **payload}, ensure_ascii=False) + '\\n'
            for mode, payload in results.items()
        ),
        encoding='utf-8',
    )
    print('Raw rankings:', raw_path)
    return results


primary_smoke_results = {}
if RUN_REAL_RETRIEVAL:
    primary_smoke_results = run_three_mode_smoke(MODEL_EXPERIMENTS[0])
else:
    print('Skipped because the official M4/M5 inputs listed above are not present.')"""
    ),
    new_markdown_cell(
        """## Dev experiments and M1 scoring

The primary MiniLM experiment runs first. Candidate models are never implicit
fallbacks: each candidate has its own model name, index directory, and experiment ID.
Set `CS30_RUN_CANDIDATES=1` only after the matching M5 candidate indexes exist.

Each completed condition writes raw Dev/Test JSONL, a run manifest, retrieval scores,
aggregate metrics, answer/citation reports, and a failure list."""
    ),
    new_code_cell(
        """def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding='utf-8'))


def git_is_dirty() -> bool:
    completed = subprocess.run(
        [str(GIT_EXECUTABLE), 'status', '--porcelain'],
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return bool(completed.stdout.strip())


def artifact_versions(index_dir: Path) -> tuple[str, str, str]:
    artifact = load_json(index_dir / 'artifact.json')
    metadata = artifact['metadata']
    mapping = load_json(GOLD_MAPPING)
    return (
        str(metadata['index_version']),
        str(mapping['chunk_config_hash']),
        str(mapping['mapping_version']),
    )


def evaluation_environment(experiment: dict[str, object]) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            'CS30_ENV': 'staging',
            'CS30_FIXTURE_MODE': 'false',
            'CS30_TOP_K': str(TOP_K),
            'CS30_INDEX_DIR': str(experiment['index_dir']),
            'CS30_EXPECTED_EMBEDDING_MODEL': str(experiment['model']),
            'CS30_RRF_DENSE_WEIGHT': str(experiment.get('weights', (1.0, 1.0))[0]),
            'CS30_RRF_BM25_WEIGHT': str(experiment.get('weights', (1.0, 1.0))[1]),
        }
    )
    return environment


def run_and_score(
    experiment: dict[str, object],
    *,
    split: str,
    mode: str,
) -> dict[str, str]:
    experiment_id = str(experiment['experiment_id'])
    output_dir = M6_OUTPUT_ROOT / split / experiment_id / mode
    output_dir.mkdir(parents=True, exist_ok=True)
    run_file = output_dir / f'{experiment_id}_{mode}_{split}.jsonl'
    run_manifest = output_dir / f'{experiment_id}_{mode}_{split}.manifest.json'
    score_summary = output_dir / 'scores.json'
    score_rows = output_dir / 'retrieval_scores.jsonl'
    report_dir = output_dir / 'reports'

    index_version, chunk_version, mapping_version = artifact_versions(
        Path(experiment['index_dir'])
    )
    run_command = [
        sys.executable,
        '-m',
        'cs30.evaluation.cli',
        'run',
        '--gold',
        str(NORMALIZED_GOLD),
        '--document',
        str(PREPARED_DOCUMENT),
        '--corpus-manifest',
        str(PREPARED_CORPUS_MANIFEST),
        '--output',
        str(run_file),
        '--manifest',
        str(run_manifest),
        '--execution-mode',
        'retrieval_only',
        '--retrieval-mode',
        mode,
        '--environment',
        'staging',
        '--split',
        split,
        '--top-k',
        str(TOP_K),
        '--k-values',
        *[str(value) for value in K_VALUES],
        '--dataset-id',
        'm3-gold',
        '--dataset-version',
        'gold-v0.2-from-m3-v0.1.1',
        '--chunk-version',
        chunk_version,
        '--mapping-version',
        mapping_version,
        '--embedding-version',
        str(experiment['model']),
        '--index-version',
        index_version,
    ]
    if git_is_dirty():
        if not ALLOW_DIRTY_LOCAL:
            raise RuntimeError('Refusing a dirty, non-reportable evaluation run.')
        run_command.append('--allow-dirty')

    if run_file.is_file() != run_manifest.is_file():
        raise FileExistsError(
            f'Only one of the run file and manifest exists: {run_file}, {run_manifest}'
        )
    if run_file.is_file() and run_manifest.is_file():
        saved_manifest = load_json(run_manifest)
        if not ALLOW_DIRTY_LOCAL and not saved_manifest['reportable']:
            raise ValueError(f'Refusing to reuse a non-reportable run: {run_manifest}')
        print('Using completed run:', run_file)
    else:
        if Path(str(run_file) + '.inprogress').is_file():
            run_command.append('--resume')
        print('Running:', subprocess.list2cmdline(run_command))
        subprocess.run(
            run_command,
            cwd=PROJECT_ROOT,
            env=evaluation_environment(experiment),
            check=True,
        )

    score_command = [
        sys.executable,
        '-m',
        'cs30.evaluation.cli',
        'score',
        '--gold',
        str(NORMALIZED_GOLD),
        '--document',
        str(PREPARED_DOCUMENT),
        '--corpus-manifest',
        str(PREPARED_CORPUS_MANIFEST),
        '--runs',
        str(run_file),
        '--mapping',
        str(GOLD_MAPPING),
        '--manifest',
        str(run_manifest),
        '--output',
        str(score_summary),
        '--scores-output',
        str(score_rows),
        '--answer-citation-output-dir',
        str(report_dir),
        '--k-values',
        *[str(value) for value in K_VALUES],
    ]
    print('Scoring:', subprocess.list2cmdline(score_command))
    subprocess.run(score_command, cwd=PROJECT_ROOT, check=True)

    return {
        'experiment_id': experiment_id,
        'mode': mode,
        'split': split,
        'model': str(experiment['model']),
        'index_dir': str(experiment['index_dir']),
        'run_file': str(run_file),
        'manifest': str(run_manifest),
        'scores': str(score_summary),
        'score_rows': str(score_rows),
        'exceptions': str(report_dir / 'answer_citation_failures.jsonl'),
    }"""
    ),
    new_code_cell(
        """completed_evaluations: list[dict[str, str]] = []

if RUN_PRIMARY_DEV:
    primary_experiment = MODEL_EXPERIMENTS[0]
    for retrieval_mode in ('bm25', 'dense', 'hybrid'):
        completed_evaluations.append(
            run_and_score(
                primary_experiment,
                split='proposed_dev',
                mode=retrieval_mode,
            )
        )
else:
    print('Primary Dev evaluation is pending the official M4/M5 artifacts.')

if RUN_CANDIDATE_EXPERIMENTS:
    if not RUN_PRIMARY_DEV:
        raise FileNotFoundError(
            'Run the official MiniLM primary Dev evaluation before candidate experiments.'
        )
    for experiment in MODEL_EXPERIMENTS[1:]:
        candidate_missing = missing_files(
            M4_REQUIRED + index_required(Path(experiment['index_dir']))
        )
        if candidate_missing:
            print(f"Skipping {experiment['experiment_id']}; missing candidate index files:")
            for path in candidate_missing:
                print(' -', path.relative_to(PROJECT_ROOT))
            continue
        modes = ('hybrid',) if experiment['role'] == 'candidate_rrf' else ('dense', 'hybrid')
        for retrieval_mode in modes:
            completed_evaluations.append(
                run_and_score(
                    experiment,
                    split='proposed_dev',
                    mode=retrieval_mode,
                )
            )
else:
    print('Candidate experiments are disabled. Set CS30_RUN_CANDIDATES=1 after indexes exist.')"""
    ),
    new_markdown_cell("## Independent Dev result validation"),
    new_code_cell(
        """if RUN_PRIMARY_DEV:
    validation_command = [
        sys.executable,
        str(PROJECT_ROOT / 'scripts' / 'validate_w5_m6_dev.py'),
    ]
    if not ALLOW_DIRTY_LOCAL:
        validation_command.append('--require-clean')
    subprocess.run(validation_command, cwd=PROJECT_ROOT, check=True)
else:
    print('Independent Dev validation is pending official inputs.')"""
    ),
    new_markdown_cell("## Frozen Test gate"),
    new_code_cell(
        """if RUN_FROZEN_TEST:
    frozen_matches = [
        experiment
        for experiment in MODEL_EXPERIMENTS
        if experiment['experiment_id'] == FROZEN_EXPERIMENT_ID
    ]
    if len(frozen_matches) != 1:
        raise ValueError(f'Unknown frozen experiment ID: {FROZEN_EXPERIMENT_ID}')
    frozen_experiment = frozen_matches[0]
    if FROZEN_RETRIEVAL_MODE not in ('bm25', 'dense', 'hybrid'):
        raise ValueError(f'Invalid frozen retrieval mode: {FROZEN_RETRIEVAL_MODE}')
    dev_scores = (
        M6_OUTPUT_ROOT / 'proposed_dev' / FROZEN_EXPERIMENT_ID
        / FROZEN_RETRIEVAL_MODE / 'scores.json'
    )
    if not dev_scores.is_file():
        raise FileNotFoundError(
            f'Frozen Test requires the selected Dev score artifact: {dev_scores}'
        )
    frozen_selection_path = M6_OUTPUT_ROOT / 'frozen_selection.json'
    frozen_selection = {
        'experiment_id': FROZEN_EXPERIMENT_ID,
        'retrieval_mode': FROZEN_RETRIEVAL_MODE,
        'dev_scores_sha256': hashlib.sha256(dev_scores.read_bytes()).hexdigest(),
    }
    if frozen_selection_path.is_file():
        existing_selection = json.loads(frozen_selection_path.read_text(encoding='utf-8'))
        if existing_selection != frozen_selection:
            raise ValueError('Frozen Test selection differs from the existing frozen selection.')
    else:
        frozen_selection_path.write_text(
            json.dumps(frozen_selection, indent=2) + '\\n', encoding='utf-8'
        )
    frozen_missing = missing_files(
        M4_REQUIRED + index_required(Path(frozen_experiment['index_dir']))
    )
    if frozen_missing:
        raise FileNotFoundError(
            'Frozen Test inputs are incomplete: ' + ', '.join(str(path) for path in frozen_missing)
        )
    completed_evaluations.append(
        run_and_score(
            frozen_experiment,
            split='proposed_test',
            mode=FROZEN_RETRIEVAL_MODE,
        )
    )
else:
    print('Test remains locked. Freeze one Dev configuration, then set CS30_RUN_FROZEN_TEST=1.')"""
    ),
    new_markdown_cell("## M1 handoff manifest"),
    new_code_cell(
        """def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


M6_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
handoff_files = sorted(
    path
    for path in M6_OUTPUT_ROOT.rglob('*')
    if path.is_file()
    and path.name != 'handoff_manifest.json'
    and 'failed_attempts' not in path.parts
)
handoff_manifest = {
    'created_at_utc': datetime.now(timezone.utc).isoformat(),
    'status': (
        'pending_official_artifacts'
        if not completed_evaluations
        else 'dev_complete_provisional_m5_index'
    ),
    'git_dirty': git_is_dirty() if GIT_EXECUTABLE is not None else None,
    'm5_artifact_status': 'M6 local rebuild pending M5 owner validation',
    'm4_release_tag': 'w5-m4-official-v1',
    'm5_release_tag': 'w5-m5-minilm-local-rebuild-v1',
    'primary_model': PRIMARY_EMBEDDING_MODEL,
    'top_k': TOP_K,
    'k_values': list(K_VALUES),
    'answerability_note': (
        'All 20 current Gold questions are answerable. Controlled refusal tests do not '
        'calibrate a production threshold.'
    ),
    'missing_primary_inputs': [str(path) for path in PRIMARY_MISSING],
    'completed_evaluations': completed_evaluations,
    'dev_metric_summary': [
        {
            'mode': item['mode'],
            'hit_at_5': load_json(Path(item['scores']))['retrieval']['by_k']['5']['hit_at_k'],
            'recall_at_5': load_json(Path(item['scores']))['retrieval']['by_k']['5'][
                'recall_at_k'
            ],
            'mrr': load_json(Path(item['scores']))['retrieval']['mrr'],
        }
        for item in completed_evaluations
        if item['split'] == 'proposed_dev'
    ],
    'files': [
        {
            'path': str(path.relative_to(PROJECT_ROOT)),
            'bytes': path.stat().st_size,
            'sha256': sha256(path),
        }
        for path in handoff_files
    ],
}
handoff_path = M6_OUTPUT_ROOT / 'handoff_manifest.json'
handoff_path.write_text(
    json.dumps(handoff_manifest, indent=2, ensure_ascii=False) + '\\n',
    encoding='utf-8',
)

print('Handoff status:', handoff_manifest['status'])
print('Handoff manifest:', handoff_path)
for metric in handoff_manifest['dev_metric_summary']:
    print(metric)
print('Delivered files:', len(handoff_manifest['files']))"""
    ),
    new_markdown_cell(
        """## Takeaways

- MiniLM is the mandatory primary run; MPNet, E5, BGE-base, and BGE-M3 remain
  explicitly identified candidate experiments.
- BM25, Dense, and Hybrid use one M5 artifact and are checked for matching provenance.
- Dev `run` and M1 `score` commands execute with `subprocess.run(..., check=True)`.
- Top-K is fixed at 5 and reported at K = 1, 3, and 5.
- Raw rankings, Dev/Test JSONL, manifests, scores, and failure reports are recorded in
  the M1 handoff manifest when artifacts are available.
- The current M5 index is a local rebuild pending M5 owner validation. Results are
  real Dev retrieval measurements, but not yet an owner-approved W5 index result.
- The current answerable-only Gold set cannot calibrate production refusal behavior."""
    ),
]


notebook = new_notebook(
    cells=cells,
    metadata={
        "kernelspec": {
            "display_name": "Python 3 (w5_m6_code .venv)",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.11"},
    },
)
nbformat.write(notebook, NOTEBOOK)
print(NOTEBOOK)
