from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

ROOT = Path(__file__).resolve().parent
NOTEBOOK = ROOT / "M6_W5_retrieval_dev_test.ipynb"


cells = [
    new_markdown_cell(
        """# M6 W5 Retrieval Evaluation and Handoff

## TL;DR

This notebook is the reproducible M6 handoff for BGE-M3 Hybrid retrieval.
It uses the repository interfaces, the M4/M5 release artifact layout,
`BAAI/bge-m3` with its matching 1024-dimensional FAISS index, `top_k=5`,
weighted RRF (Dense 25% / BM25 75%), and Hit/Recall at 1, 3, and 5 plus MRR.

The notebook automatically runs real retrieval and Dev evaluation when the official
artifacts are present. If an artifact is missing, it reports the exact missing path
instead of presenting fixture output as a real result. The proposed Test split remains
locked until `CS30_RUN_FROZEN_TEST=1` is explicitly set after the BGE-M3 Dev run.
Earlier BM25 and BGE-M3 Dense runs already used the eight Test questions. Any
BGE-M3 Hybrid Test run is therefore another exploratory use of that split,
not an untouched final Test.
The user accepted the M3/M5 inputs for this experiment without changing their
source review labels."""
    ),
    new_markdown_cell(
        """## Context and methods

### Key assumptions

- M4 artifacts follow `artifacts/w5/m4-v3/`.
- The selected BGE-M3 index follows `artifacts/w5/m5_release_v2/bge-m3/`.
- The index must identify `BAAI/bge-m3`, 1024 dimensions, and the same M4
  corpus and chunk configuration as the mapping.
- The current 20-question Gold set is answerable-only. Refusal checks below are
  controlled engineering gates, not evidence of a calibrated production threshold.
- BGE-M3 Hybrid uses RRF `k=60`, 50 candidates per retriever, and weights
  Dense 0.25 / BM25 0.75. It is selected by the user, not a Dev winner claim.
- The eight Test questions were already evaluated with BM25 and BGE-M3 Dense,
  so any Hybrid Test result is explicitly exploratory."""
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
from datetime import UTC, datetime
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
from cs30.evaluation.manifest import capture_git_state
from cs30.retrieval.model_policy import CANDIDATE_EMBEDDING_MODELS

TOP_K = 5
K_VALUES = (1, 3, 5)
RRF_K = 60
RRF_INPUT_TOP_K = 50
RRF_DENSE_WEIGHT = 0.25
RRF_BM25_WEIGHT = 0.75
BM25_MIN_SCORE = 0.0
DENSE_MIN_SIMILARITY = None
SMOKE_QUESTION = 'What is acceleration?'

M4_ROOT = PROJECT_ROOT / 'artifacts' / 'w5' / 'm4-v3'
PREPARED_CORPUS_DIR = M4_ROOT / 'prepared_corpus'
PREPARED_DOCUMENT = PREPARED_CORPUS_DIR / 'openstax_document.json'
PREPARED_CORPUS_MANIFEST = PREPARED_CORPUS_DIR / 'corpus_manifest.json'
EVIDENCE_SOURCE_BLOCKS = PREPARED_CORPUS_DIR / 'evidence_source_blocks.jsonl'
NORMALIZED_GOLD = M4_ROOT / 'gold_normalized' / 'gold_v0_2_from_m3_v0_1_1.jsonl'
GOLD_MAPPING = M4_ROOT / 'gold_mapping' / 'evaluation_mapping_v0_1.json'

M5_ROOT = PROJECT_ROOT / 'artifacts' / 'w5' / 'm5_release_v2'
SELECTED_EMBEDDING_MODEL = 'BAAI/bge-m3'
assert SELECTED_EMBEDDING_MODEL in CANDIDATE_EMBEDDING_MODELS
PRIMARY_INDEX_DIR = M5_ROOT / 'bge-m3'
M6_OUTPUT_ROOT = PROJECT_ROOT / 'artifacts' / 'w5' / 'm6'
EXPERIMENT_ID = 'w5-bge-m3-hybrid-25-75-release-v2'
MODEL_EXPERIMENTS = [{
    'experiment_id': EXPERIMENT_ID,
    'model': SELECTED_EMBEDDING_MODEL,
    'index_dir': PRIMARY_INDEX_DIR,
    'role': 'selected_bge_m3_hybrid_25_75',
    'weights': (RRF_DENSE_WEIGHT, RRF_BM25_WEIGHT),
}]

RUN_FROZEN_TEST = os.getenv('CS30_RUN_FROZEN_TEST', '0') == '1'
ALLOW_DIRTY_LOCAL = os.getenv('CS30_ALLOW_DIRTY_LOCAL', '0') == '1'
FROZEN_EXPERIMENT_ID = EXPERIMENT_ID
FROZEN_RETRIEVAL_MODE = 'hybrid'

print('Top-K:', TOP_K)
print('K values:', K_VALUES)
print('Hybrid RRF:', RRF_K, RRF_INPUT_TOP_K, RRF_DENSE_WEIGHT, RRF_BM25_WEIGHT)
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
            'The checkout must be clean for provenance-safe runs. '
            'Set CS30_ALLOW_DIRTY_LOCAL=1 only for explicitly non-reportable local validation.'
        )

if RUN_FROZEN_TEST and PRIMARY_MISSING:
    raise FileNotFoundError(
        'Exploratory Test was requested, but official M4/M5 inputs are incomplete.'
    )"""
    ),
    new_markdown_cell(
        """## BGE-M3 release identity check

The new Release archive contains both BGE-base and BGE-M3. This notebook checks
the selected BGE-M3 artifact, embedding dimension, chunk count, and M4 corpus
identity before running any retrieval. The Release `artifact.json` uses a UTF-8
BOM; the shared loader accepts that encoding without altering source bytes."""
    ),
    new_code_cell(
        """if RUN_PRIMARY_DEV:
    bge_artifact = json.loads(
        (PRIMARY_INDEX_DIR / 'artifact.json').read_text(encoding='utf-8-sig')
    )
    bge_chunks = json.loads((PRIMARY_INDEX_DIR / 'chunks.json').read_text(encoding='utf-8'))
    corpus_path = M4_ROOT / 'retrieval_corpus' / 'records.jsonl'
    assert bge_artifact['metadata']['embedding_model'] == SELECTED_EMBEDDING_MODEL
    assert int(bge_artifact['metadata']['dimension']) == 1024
    assert bge_artifact['chunk_count'] == len(bge_chunks) == 3684
    assert bge_artifact['metadata']['corpus_id'] == (
        'sha256:' + hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    )
    print('Selected model:', bge_artifact['metadata']['embedding_model'])
    print('Index version:', bge_artifact['metadata']['index_version'])
    print('Index dimensions:', bge_artifact['metadata']['dimension'])
    print('Corpus-bound chunks:', len(bge_chunks))
else:
    print('BGE-M3 identity check is pending the released index.')"""
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
        """### Retrieval cache evidence

`src/cs30/retrieval/real.py` implements `_ResultCache`. Hybrid, Dense, and
BM25 retrievers cache by query and configuration, including RRF weights.
Focused tests cover repeated queries, configuration keys, and mutation isolation."""
    ),
    new_code_cell(
        """cache_test_command = [
    sys.executable, '-m', 'pytest', '-q', 'tests/test_real_retrieval.py',
    '-k', 'cache',
]
subprocess.run(cache_test_command, cwd=PROJECT_ROOT, check=True)
print('Focused retrieval cache tests passed: repeated query, configuration keys, and isolation.')"""
    ),
    new_markdown_cell(
        """## Real BGE-M3 Hybrid smoke check

The check below validates rank order, result count, duplicate IDs, source fields,
model identity, and provenance using Dense 25% / BM25 75%."""
    ),
    new_code_cell(
        """from cs30.config import AppConfig, RetrievalConfig
from cs30.pipeline import build_real_retrieval_deps


def make_retrieval_config(
    mode: RetrievalMode,
    *,
    index_dir: Path,
    expected_model: str,
    dense_weight: float = RRF_DENSE_WEIGHT,
    bm25_weight: float = RRF_BM25_WEIGHT,
) -> AppConfig:
    return AppConfig(
        environment='staging',
        fixture_mode=False,
        retrieval=RetrievalConfig(
            mode=mode,
            top_k=TOP_K,
            index_dir=str(index_dir),
            expected_embedding_model=expected_model,
            rrf_k=RRF_K,
            rrf_input_top_k=RRF_INPUT_TOP_K,
            rrf_dense_weight=dense_weight,
            rrf_bm25_weight=bm25_weight,
        ),
    )


def run_hybrid_smoke(experiment: dict[str, object]) -> dict[str, object]:
    output_dir = M6_OUTPUT_ROOT / 'smoke' / str(experiment['experiment_id'])
    output_dir.mkdir(parents=True, exist_ok=True)

    config = make_retrieval_config(
        RetrievalMode.HYBRID,
        index_dir=Path(experiment['index_dir']),
        expected_model=str(experiment['model']),
        dense_weight=RRF_DENSE_WEIGHT,
        bm25_weight=RRF_BM25_WEIGHT,
    )
    result = build_real_retrieval_deps(config).retriever.retrieve(
        SMOKE_QUESTION, top_k=TOP_K,
    )
    assert len(result.hits) <= TOP_K
    assert [hit.rank for hit in result.hits] == list(range(1, len(result.hits) + 1))
    assert len({hit.chunk_id for hit in result.hits}) == len(result.hits)
    assert all(hit.source.strip() for hit in result.hits)
    assert result.mode == RetrievalMode.HYBRID
    assert result.provenance is not None
    assert result.provenance.embedding_model == SELECTED_EMBEDDING_MODEL
    assert result.provenance.index_version == bge_artifact['metadata']['index_version']
    payload = result.model_dump(mode='json')

    print(f'BGE-M3 Hybrid (Dense 25% / BM25 75%): {len(result.hits)} results')
    for hit in result.hits:
        print(
            f'  rank={hit.rank} chunk_id={hit.chunk_id} '
            f'source={hit.source} score={hit.score:.6f}'
        )

    raw_path = output_dir / 'raw_rankings.jsonl'
    raw_path.write_text(
        json.dumps({'mode': 'hybrid', 'dense_weight': RRF_DENSE_WEIGHT,
                    'bm25_weight': RRF_BM25_WEIGHT, **payload}, ensure_ascii=False) + '\\n',
        encoding='utf-8',
    )
    print('Raw rankings:', raw_path)
    return payload


primary_smoke_results = {}
if RUN_PRIMARY_DEV:
    primary_smoke_results = run_hybrid_smoke(MODEL_EXPERIMENTS[0])
else:
    print('Skipped because the official M4/M5 inputs listed above are not present.')"""
    ),
    new_markdown_cell(
        """## BGE-M3 Dev experiment and M1 scoring

Only BGE-M3 Hybrid at Dense 25% / BM25 75% is evaluated here. The release also contains MiniLM,
BGE-base, E5, and MPNet, but none is an implicit fallback or run in this notebook.

Each completed condition writes raw Dev/Test JSONL, a run manifest, retrieval scores,
aggregate metrics, answer/citation reports, and a failure list."""
    ),
    new_code_cell(
        """def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding='utf-8-sig'))


def git_is_dirty() -> bool:
    completed = subprocess.run(
        [str(GIT_EXECUTABLE), 'status', '--porcelain'],
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return bool(completed.stdout.strip())

def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def artifact_versions(index_dir: Path) -> tuple[str, str, str]:
    artifact = load_json(index_dir / 'artifact.json')
    metadata = artifact['metadata']
    mapping = load_json(GOLD_MAPPING)

    m4_manifest = load_json(
        PROJECT_ROOT
        / 'artifacts'
        / 'w5'
        / 'm4-v3'
        / 'retrieval_corpus'
        / 'manifest.json'
    )
    mapping_chunk_hash = str(mapping['chunk_config_hash'])

    artifact_corpus_id = str(metadata['corpus_id'])
    m4_corpus_id = str(m4_manifest['corpus_id'])

    if artifact_corpus_id != m4_corpus_id:
        raise ValueError(
            'Index and M4 manifest use different corpora: '
            f'{artifact_corpus_id!r} != {m4_corpus_id!r}'
        )

    if int(artifact['chunk_count']) != int(m4_manifest['record_count']):
        raise ValueError(
            'Index and M4 manifest have different record counts: '
            f"{artifact['chunk_count']!r} != {m4_manifest['record_count']!r}"
        )

    return (
        str(metadata['index_version']),
        mapping_chunk_hash,
        str(mapping['mapping_version']),
    )


def evaluation_environment(experiment: dict[str, object]) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop('CS30_BM25_MIN_SCORE', None)
    environment.pop('CS30_DENSE_MIN_SIMILARITY', None)
    environment.update(
        {
            'CS30_ENV': 'staging',
            'CS30_FIXTURE_MODE': 'false',
            'CS30_TOP_K': str(TOP_K),
            'CS30_INDEX_DIR': str(experiment['index_dir']),
            'CS30_EXPECTED_EMBEDDING_MODEL': str(experiment['model']),
            'CS30_RRF_K': str(RRF_K),
            'CS30_RRF_INPUT_TOP_K': str(RRF_INPUT_TOP_K),
            'CS30_RRF_DENSE_WEIGHT': str(experiment['weights'][0]),
            'CS30_RRF_BM25_WEIGHT': str(experiment['weights'][1]),
            'CS30_BM25_MIN_SCORE': str(BM25_MIN_SCORE),
            'CS30_DENSE_MIN_SIMILARITY': (
                ''
                if DENSE_MIN_SIMILARITY is None
                else str(DENSE_MIN_SIMILARITY)
            ),
            
            'CS30_BM25_STOPWORDS': 'true',
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

    index_dir = Path(experiment['index_dir'])
    index_version, chunk_version, mapping_version = artifact_versions(index_dir)
    signature_path = output_dir / 'experiment_signature.manifest.json'
    git_state = capture_git_state(PROJECT_ROOT)

    expected_signature = {
    'git_commit': git_state.commit,
    'git_dirty': git_state.dirty,
    'git_snapshot_sha256': git_state.snapshot_sha256,
    'artifact_json_sha256': file_sha256(index_dir / 'artifact.json'),
    'chunks_json_sha256': file_sha256(index_dir / 'chunks.json'),
    'index_faiss_sha256': file_sha256(index_dir / 'index.faiss'),
    'gold_sha256': file_sha256(NORMALIZED_GOLD),
    'prepared_document_sha256': file_sha256(PREPARED_DOCUMENT),
    'prepared_corpus_manifest_sha256': file_sha256(
        PREPARED_CORPUS_MANIFEST
    ),
    'gold_mapping_sha256': file_sha256(GOLD_MAPPING),
    'model': str(experiment['model']),
    'index_version': index_version,
    'chunk_config_hash': chunk_version,
    'mapping_version': mapping_version,
    'retrieval_mode': mode,
    'split': split,
    'top_k': TOP_K,
    'k_values': list(K_VALUES),
    'rrf_k': RRF_K,
    'rrf_input_top_k': RRF_INPUT_TOP_K,
    'rrf_dense_weight': float(experiment['weights'][0]),
    'rrf_bm25_weight': float(experiment['weights'][1]),
    'bm25_min_score': BM25_MIN_SCORE,
    'dense_min_similarity': DENSE_MIN_SIMILARITY,
    }
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
        '--provisional',
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
        if not signature_path.is_file():
            raise ValueError(
                f'Existing run has no experiment signature. '
                f'Move or delete {output_dir} and rerun.'
            )

        saved_signature = load_json(signature_path)
        if saved_signature != expected_signature:
            raise ValueError(
                f'Existing run does not match the current experiment. '
                f'Move or delete {output_dir} and rerun.'
            )

        saved_manifest = load_json(run_manifest)
        if not ALLOW_DIRTY_LOCAL and saved_manifest['git_dirty']:
            raise ValueError(f'Refusing to reuse a dirty run: {run_manifest}')
        print('Using verified completed run:', run_file)
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
        signature_path.write_text(
            json.dumps(expected_signature, indent=2, ensure_ascii=False) + '\\n',
            encoding='utf-8',
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
    completed_evaluations.append(
        run_and_score(
            primary_experiment,
            split='proposed_dev',
            mode='hybrid',
        )
    )
else:
    print('BGE-M3 Dev evaluation is pending the M4/M5 release inputs.')"""
    ),
    new_markdown_cell("## Independent Dev result validation"),
    new_code_cell(
        """if RUN_PRIMARY_DEV:
    validation_command = [
        sys.executable,
        str(PROJECT_ROOT / 'scripts' / 'validate_w5_m6_dev.py'),
        '--experiment-id', EXPERIMENT_ID,
        '--modes', 'hybrid',
        '--expected-model', SELECTED_EMBEDDING_MODEL,
    ]
    if not ALLOW_DIRTY_LOCAL:
        validation_command.append('--require-clean')
    subprocess.run(validation_command, cwd=PROJECT_ROOT, check=True)
else:
    print('Independent Dev validation is pending official inputs.')"""
    ),
    new_markdown_cell("## BGE-M3 Dev check before exploratory Test"),
    new_code_cell(
        """dev_mode_scores = {}
for item in completed_evaluations:
    if item['experiment_id'] != FROZEN_EXPERIMENT_ID or item['split'] != 'proposed_dev':
        continue
    retrieval = load_json(Path(item['scores']))['retrieval']
    dev_mode_scores[item['mode']] = {
        'hit_at_5': retrieval['by_k']['5']['hit_at_k'],
        'mrr': retrieval['mrr'],
    }

if RUN_PRIMARY_DEV:
    assert set(dev_mode_scores) == {'hybrid'}
    assert FROZEN_RETRIEVAL_MODE == 'hybrid'
    print('BGE-M3 Hybrid 25/75 Dev metrics:', dev_mode_scores['hybrid'])
    print('BGE-M3 Hybrid 25/75 was selected by the user, not declared the Dev winner.')
else:
    print('BGE-M3 Dev check is pending the released inputs.')"""
    ),
    new_markdown_cell(
        """## BGE-M3 exploratory Test gate

The eight proposed Test questions were already used for BM25 and BGE-M3 Dense.
If enabled, this BGE-M3 Hybrid Test is another exploratory evaluation. It is never
described as an untouched one-time final Test."""
    ),
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
    if FROZEN_RETRIEVAL_MODE != 'hybrid':
        raise ValueError('This BGE-M3 experiment only permits Hybrid retrieval')
    dev_scores = (
        M6_OUTPUT_ROOT / 'proposed_dev' / FROZEN_EXPERIMENT_ID
        / FROZEN_RETRIEVAL_MODE / 'scores.json'
    )
    if not dev_scores.is_file():
        raise FileNotFoundError(
            f'Exploratory Test requires the selected Dev score artifact: {dev_scores}'
        )
    frozen_selection_path = M6_OUTPUT_ROOT / 'frozen_selection_bge_m3_hybrid_25_75_v2.json'
    frozen_selection = {
        'experiment_id': FROZEN_EXPERIMENT_ID,
        'retrieval_mode': FROZEN_RETRIEVAL_MODE,
        'dev_scores_sha256': hashlib.sha256(dev_scores.read_bytes()).hexdigest(),
        'selection_rule': 'User-selected BGE-M3 Hybrid 25/75; no Dev winner claim',
        'rrf_k': RRF_K,
        'rrf_input_top_k': RRF_INPUT_TOP_K,
        'rrf_dense_weight': RRF_DENSE_WEIGHT,
        'rrf_bm25_weight': RRF_BM25_WEIGHT,
        'test_usage': 'exploratory repeat after prior BM25 and BGE-M3 Dense Test runs',
        'dev_mode_scores': dev_mode_scores,
    }
    if frozen_selection_path.is_file():
        existing_selection = json.loads(frozen_selection_path.read_text(encoding='utf-8'))
        if existing_selection != frozen_selection:
            raise ValueError('Exploratory Test selection differs from the saved selection.')
    else:
        frozen_selection_path.write_text(
            json.dumps(frozen_selection, indent=2) + '\\n', encoding='utf-8'
        )
    frozen_missing = missing_files(
        M4_REQUIRED + index_required(Path(frozen_experiment['index_dir']))
    )
    if frozen_missing:
        raise FileNotFoundError(
            'Exploratory Test inputs are incomplete: '
            + ', '.join(str(path) for path in frozen_missing)
        )
    completed_evaluations.append(
        run_and_score(
            frozen_experiment,
            split='proposed_test',
            mode=FROZEN_RETRIEVAL_MODE,
        )
    )
else:
    print('BGE-M3 exploratory Test is locked; set CS30_RUN_FROZEN_TEST=1 to run it.')"""
    ),
    new_markdown_cell("## Independent exploratory Test validation"),
    new_code_cell(
        """if RUN_FROZEN_TEST:
    test_validation_command = [
        sys.executable,
        str(PROJECT_ROOT / 'scripts' / 'validate_w5_m6_dev.py'),
        '--split', 'proposed_test',
        '--experiment-id', EXPERIMENT_ID,
        '--modes', 'hybrid',
        '--expected-model', SELECTED_EMBEDDING_MODEL,
        '--selection-file', 'frozen_selection_bge_m3_hybrid_25_75_v2.json',
    ]
    if not ALLOW_DIRTY_LOCAL:
        test_validation_command.append('--require-clean')
    subprocess.run(test_validation_command, cwd=PROJECT_ROOT, check=True)
else:
    print('Exploratory Test validation is skipped because the Test gate is closed.')"""
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
handoff_files = {
    path
    for item in completed_evaluations
    for path in Path(item['run_file']).parent.rglob('*')
    if path.is_file()
}
smoke_file = M6_OUTPUT_ROOT / 'smoke' / EXPERIMENT_ID / 'raw_rankings.jsonl'
selection_file = M6_OUTPUT_ROOT / 'frozen_selection_bge_m3_hybrid_25_75_v2.json'
for path in (smoke_file, selection_file):
    if path.is_file():
        handoff_files.add(path)
has_frozen_test = any(item['split'] == 'proposed_test' for item in completed_evaluations)
run_reportability = [
    load_json(Path(item['manifest']))['reportable'] for item in completed_evaluations
]
handoff_manifest = {
    'created_at_utc': datetime.now(UTC).isoformat(),
    'status': (
        'pending_official_artifacts'
        if not completed_evaluations
        else (
            'bge_m3_hybrid_exploratory_test_complete_nonreportable'
            if has_frozen_test else 'bge_m3_hybrid_dev_complete_nonreportable'
        )
    ),
    'git_dirty': git_is_dirty() if GIT_EXECUTABLE is not None else None,
    'm3_m5_user_accepted_for_experiment': True,
    'test_usage': 'exploratory repeat after prior BM25 and BGE-M3 Dense Test runs',
    'm5_artifact_status': (
        'User accepted this local rebuild for the W5 experiment; '
        'the release itself remains labeled pending M5 owner validation'
    ),
    'gold_annotation_status': 'm3_initial (not reviewed)',
    'formal_reportable': bool(run_reportability) and all(run_reportability),
    'm4_release_tag': 'w5-m4-official-v1',
    'm5_release_tag': 'w5-m5-minilm-local-rebuild-v1',
    'm5_release_asset': 'm5_release_v2.zip',
    'm5_release_asset_sha256': '5a1c8caed9a57de2b23a02be9316e8c9c4af592097d0cc37fe9fb655775cad72',
    'selected_model': SELECTED_EMBEDDING_MODEL,
    'selected_retrieval_mode': 'hybrid',
    'rrf_k': RRF_K,
    'rrf_input_top_k': RRF_INPUT_TOP_K,
    'rrf_dense_weight': RRF_DENSE_WEIGHT,
    'rrf_bm25_weight': RRF_BM25_WEIGHT,
    'top_k': TOP_K,
    'k_values': list(K_VALUES),
    'answerability_note': (
        'All 20 current Gold questions are answerable. Controlled refusal tests do not '
        'calibrate a production threshold.'
    ),
    'missing_primary_inputs': [str(path) for path in PRIMARY_MISSING],
    'completed_evaluations': completed_evaluations,
    'frozen_selection': (
        load_json(selection_file) if has_frozen_test else None
    ),
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
    'test_metric_summary': [
        {
            'mode': item['mode'],
            'hit_at_5': load_json(Path(item['scores']))['retrieval']['by_k']['5']['hit_at_k'],
            'recall_at_5': load_json(Path(item['scores']))['retrieval']['by_k']['5'][
                'recall_at_k'
            ],
            'mrr': load_json(Path(item['scores']))['retrieval']['mrr'],
        }
        for item in completed_evaluations
        if item['split'] == 'proposed_test'
    ],
    'files': [
        {
            'path': str(path.relative_to(PROJECT_ROOT)),
            'bytes': path.stat().st_size,
            'sha256': sha256(path),
        }
        for path in sorted(handoff_files)
    ],
}
handoff_path = M6_OUTPUT_ROOT / 'handoff_manifest_bge_m3_hybrid_25_75_v2.json'
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

- This revision evaluates `BAAI/bge-m3` with weighted Hybrid retrieval from
  `m5_release_v2.zip`: Dense 25% / BM25 75%, RRF `k=60`, 50 candidates per mode.
- The released index is 1024-dimensional and bound to the same M4 corpus.
- Dev `run` and M1 `score` commands execute with `subprocess.run(..., check=True)`.
- Top-K is fixed at 5 and reported at K = 1, 3, and 5.
- Raw rankings, Dev/Test JSONL, manifests, scores, and failure reports are recorded in
  the BGE-M3 handoff manifest when artifacts are available.
- BGE-M3 Hybrid 25/75 was requested by the user. Because BM25 and BGE-M3 Dense
  already used the proposed Test questions, a Hybrid Test result is exploratory,
  not an untouched final Test.
- M3/M5 inputs are user-accepted for this experiment, but the released Gold
  still says `m3_initial` and M5 is labeled a local rebuild. The CLI therefore
  keeps the real Dev/Test runs `reportable=false`; no source review metadata is
  rewritten.
- The cache implementation and focused repeated-query tests are identified above.
- The current answerable-only Gold set cannot calibrate production refusal behavior."""
    ),
]


notebook = new_notebook(
    cells=cells,
    metadata={
        "kernelspec": {
            "display_name": "Python 3 (cs30-personalised-rag .venv)",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.11"},
    },
)
nbformat.write(notebook, NOTEBOOK)
print(NOTEBOOK)
