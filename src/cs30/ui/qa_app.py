"""Free-text V2 Q&A with shared generation, validation and optional practice."""

from __future__ import annotations

import importlib
import os
from html import escape
from pathlib import Path
from tempfile import mkdtemp
from uuid import uuid4

import streamlit as st
import streamlit.components.v1 as components

from cs30.evaluation.concept_check_reporting import (
    build_concept_check_report,
    render_concept_check_csv,
    render_concept_check_json,
    render_concept_check_markdown,
)

# UI helper modules in dependency order (later ones import earlier ones).
_UI_MODULES = (
    "cs30.ui.concept_check",
    "cs30.ui.concept_check_demo",
    "cs30.ui.v2_fixture",
    "cs30.ui.v2_runtime",
)


def _reload_changed_ui_modules() -> None:
    """Keep a long-running Streamlit server in step with edited UI helper files.

    Streamlit re-reads this page on every run but keeps imported helper modules in
    memory, so after a file update the page could import names an old module lacks.
    Each module is reloaded once per server process and again whenever its file
    changes; its dependants are then reloaded too, so imported names stay in sync.
    """

    dirty = False
    for name in _UI_MODULES:
        module = importlib.import_module(name)
        stamp = Path(module.__file__).stat().st_mtime_ns
        if dirty or getattr(module, "_cs30_file_stamp", None) != stamp:
            # No stamp yet means the in-memory copy may predate this check: reload once.
            module = importlib.reload(module)
            module._cs30_file_stamp = stamp
            dirty = True


_reload_changed_ui_modules()

from cs30.ui.concept_check import (  # noqa: E402
    clear_quiz_component,
    inject_concept_check_styles,
    render_quiz,
)
from cs30.ui.concept_check_demo import record_demo_attempt  # noqa: E402
from cs30.ui.v2_fixture import inject_v2_styles  # noqa: E402
from cs30.ui.v2_runtime import (  # noqa: E402
    TEAM_MODELS,
    QuestionRun,
    UiBm25Retriever,
    UiHybridRetriever,
    load_ui_corpus,
    refresh_controls,
    run_question,
)
from cs30.v2.contracts import StudentLevel, StudentProfile  # noqa: E402

QUIZ_KEY = "qa-quiz"
LIVE_MODE = "Team V2 · DeepInfra"
FIXTURE_MODE = "Fixture mode · offline, no API key"
RETRIEVAL_OPTIONS = {
    "hybrid": "Hybrid · Qwen3 0.10 + BM25 0.90 (M6 system retriever)",
    "bm25": "BM25 baseline (comparison only)",
}
REPO_ROOT = Path(__file__).resolve().parents[3]


def hybrid_index_dir() -> Path:
    """M6/M5 Qwen3 index folder (artifact.json + index/index.faiss)."""

    configured = os.environ.get("CS30_UI_HYBRID_INDEX", "").strip()
    return Path(configured) if configured else REPO_ROOT / "artifacts/v2/m6_qwen3_hybrid"


def get_retriever(kind: str, corpus, directory: Path, corpus_path: str):
    """Build once per session: the Qwen3 model load is slow, retrieval itself is fast."""

    key = f"qa-retriever-{kind}-{corpus_path}-{corpus.synthetic}"
    if key not in st.session_state:
        if kind == "hybrid":
            st.write(
                "Loading Qwen3-Embedding-0.6B and the M6 FAISS index "
                "(first run downloads the model, about 1.2 GB)"
            )
            st.session_state[key] = UiHybridRetriever(
                corpus, hybrid_index_dir(), directory / "hybrid-index"
            )
        else:
            st.session_state[key] = UiBm25Retriever(
                corpus, directory / ("fixture-index" if corpus.synthetic else "real-index")
            )
    return st.session_state[key]


EXAMPLES = {
    "Acceleration": "What is average acceleration?",
    "Newton's second law": "How are net force, mass and acceleration related?",
    "Out of scope": "Which team won the football match yesterday?",
}


def apply_example() -> None:
    """Fill the input on click (V1 pills); model execution still requires submission."""

    label = st.session_state.get("qa-example")
    if label:
        st.session_state["qa-question"] = EXAMPLES[label]


def clear_question() -> None:
    """Clear obsolete output when its source/model/baseline changes, retaining events."""

    st.session_state.pop("qa-run", None)
    clear_practice()


def clear_practice() -> None:
    st.session_state.pop("qa-selection", None)
    clear_quiz_component(QUIZ_KEY)


def session_directory() -> Path:
    if "qa-directory" not in st.session_state:
        st.session_state["qa-directory"] = mkdtemp(prefix="cs30-v2-qa-")
    return Path(st.session_state["qa-directory"])


def render_answer(run: QuestionRun) -> None:
    """Show the exact validated output and generation-time settings, never relabel it."""

    validated = run.runtime.validated
    st.markdown("### Answer")
    if run.mode == "offline-integration":
        st.info(
            "Simulated answer. Fixture mode never calls a language model, so this fixed "
            "placeholder only shows where the answer appears. In Team V2 mode the selected "
            "model writes the answer from the evidence below."
        )
    if validated.abstained:
        st.warning(validated.answer.explanation)
    else:
        st.write(validated.answer.explanation)
    snapshot = run.prepared.snapshot
    st.caption(
        f"Level used: {snapshot.profile.level.value.title()} · "
        f"Profile source: {snapshot.profile_source.value} · "
        f"Citation integrity: {validated.citation_status.upper()}"
    )
    st.markdown("#### Evidence and sources")
    cited = set(validated.resolved_citations)
    first_cited = next(
        (item.evidence_id for item in run.bundle.evidence_items if item.chunk_id in cited), None
    )
    for item in run.bundle.evidence_items:
        marker = "Cited" if item.chunk_id in cited else "Retrieved only"
        with st.expander(
            f"{item.evidence_id} · {item.source_name} · Chapter {item.chapter_id} · {marker}",
            expanded=item.evidence_id == first_cited,
        ):
            st.write(item.text)
            st.code(item.source_locator, language=None)
            st.caption(f"Chunk ID: {item.chunk_id} · Rank: {item.rank}")
    if not run.bundle.evidence_items:
        st.info(
            "No evidence was retrieved. The generator returns an abstention without a model call."
        )


def render_practice(run, corpus, directory, enabled) -> None:
    """Continue from the actual validated answer, using the shared selection contract."""

    runtime = refresh_controls(run, corpus, directory, enabled)
    st.divider()
    st.markdown("### Concept Check")
    if not enabled:
        st.info("Concept Check is off. Topic changes are paused; existing history is kept.")
        return
    if not corpus.synthetic:
        st.caption(
            "Real-corpus selection uses the released Topic map. No compatible reviewed "
            "practice releases are installed; fixture questions are never mixed into this corpus."
        )

    def select():
        clear_practice()
        prepared = runtime.service.prepare(runtime.retrieval, runtime.profile)
        st.session_state["qa-selection"] = runtime.service.select(
            prepared, runtime.retrieval, runtime.validated
        )

    selection = st.session_state.get("qa-selection")
    if selection is None or selection.question is None:
        st.caption("Practise with a short question on this answer's cited Topic.")
        quiz_column, _ = st.columns(2)
        if quiz_column.button("Quiz me", type="primary", use_container_width=True):
            select()
            st.rerun()
    if selection is not None:
        if selection.question is None:
            code = selection.error_code.value if selection.error_code else selection.status.value
            st.info(f"No practice question is offered for this answer. Reason: {code}")
        else:

            def revoke(attempt_id):
                runtime.service.revoke(attempt_id, event_id=f"revoke-{attempt_id}")
                clear_practice()

            render_quiz(
                selection.question,
                on_submit=lambda choice: record_demo_attempt(runtime, selection.question, choice),
                on_skip=lambda: record_demo_attempt(runtime, selection.question, None),
                on_next=select,
                on_revoke=revoke,
                key=QUIZ_KEY,
            )
    state = runtime.replayer.replay(runtime.event_store.events(runtime.profile.profile_id))
    resolution = runtime.service.resolver.resolve_cited_topic(runtime.retrieval, runtime.validated)
    topic_id = resolution.topic_id
    st.markdown(
        '<p class="cc-field-title qa-section-gap">Topic progress</p>', unsafe_allow_html=True
    )
    if topic_id is None:
        st.caption(f"Topic unavailable: {resolution.error_code or resolution.status.value}")
        return
    title = next(t.title for t in corpus.registry.topics if t.topic_id == topic_id)
    topic = state.topics.get(topic_id)
    current_level = topic.level if topic else runtime.profile.level
    cards = (
        ("Topic", title),
        ("Topic level", current_level.value.title()),
        ("Mastery", f"{topic.mastery_score:.2f}" if topic else "0.50"),
        ("Scored attempts", str(topic.total_attempts if topic else 0)),
    )
    st.markdown(
        '<div class="cc-state-grid">'
        + "".join(
            '<div class="cc-state-item">'
            f'<span class="cc-state-label">{escape(label)}</span>'
            f'<span class="cc-state-value">{escape(value)}</span>'
            "</div>"
            for label, value in cards
        )
        + "</div>",
        unsafe_allow_html=True,
    )
    st.caption("Updated automatically from your scored Concept Check answers.")
    st.markdown(
        '<p class="cc-field-title qa-section-gap">Adjust this Topic level</p>'
        '<p class="qa-section-help">Feel this Topic is too easy or too hard? Choose a new '
        "level and give a short, specific reason. The change is recorded with your reason, "
        "earlier answers are kept, and it applies from your next generated answer.</p>",
        unsafe_allow_html=True,
    )
    with st.container(border=True, key="qa-adjust"):
        select_col, reason_col, apply_col = st.columns([1, 2, 1], vertical_alignment="bottom")
        new_level = select_col.selectbox(
            "New Topic level",
            list(StudentLevel),
            index=list(StudentLevel).index(current_level),
            format_func=lambda x: x.value.title(),
        )
        reason = reason_col.text_input(
            "Reason for level change",
            placeholder="e.g. I already covered this in a previous course",
        )
        apply = apply_col.button("Apply Topic level", type="primary", use_container_width=True)
        if apply:
            if not reason.strip():
                st.error("A reason is required.")
            elif new_level == current_level:
                st.info("This is already the current level. Nothing was changed.")
            else:
                try:
                    runtime.service.override_level(
                        topic_id, new_level, reason=reason, event_id=uuid4().hex
                    )
                except (ValueError, OSError):
                    st.error("The Topic change could not be saved. No success is claimed.")
                else:
                    clear_practice()
                    st.rerun()


def compact_report_headings(markdown: str) -> str:
    """Show report titles at the Answer heading size; the downloaded file is unchanged."""

    lines = []
    for line in markdown.splitlines():
        if line.startswith("# "):
            continue  # the dialog title already names the report
        if line.startswith("## "):
            line = "#### " + line[3:]
        lines.append(line)
    return "\n".join(lines)


def inject_qa_styles() -> None:
    """Page-only typography; the shared V1/V2 style helpers stay unchanged."""

    st.markdown(
        """
        <style>
        [data-testid="stTab"], [data-testid="stTab"] p,
        [data-baseweb="tab"] p { font-size: 1.15rem !important; }
        .qa-helper-title {
            margin: 12px 0 6px;
            color: var(--cs30-muted, #706a64);
            font-size: 1.05rem !important;
            font-weight: 650;
        }
        :root { --qa-body-size: 1rem; }
        /* Body text and form labels match the Technical run details summary. */
        .st-key-qa-question textarea,
        [data-testid="stMain"] [data-testid="stTextInput"] input,
        [data-testid="stMain"] [data-testid="stSelectbox"] input,
        [data-testid="stMain"] [data-testid="stSelectbox"] [data-baseweb="select"],
        [data-testid="stMain"] [data-testid="stSelectbox"] [data-baseweb="select"] div,
        [role="listbox"] [role="option"],
        button[data-variant="pills"],
        button[data-variant="pills"] p,
        [data-testid="stButtonGroup"] button p,
        [data-testid="stMain"] [data-testid="stMarkdownContainer"]
            p:not(.qa-helper-title, .v2-eyebrow),
        [data-testid="stMain"] [data-testid="stCaptionContainer"] p,
        [data-testid="stMain"] [data-testid="stMarkdownContainer"] li,
        [data-testid="stMain"] [data-testid="stExpander"] summary p,
        [class*="st-key-cc-options"] [role="radiogroup"] p,
        [data-testid="stMain"] .cc-state-label,
        [data-testid="stMain"] .cc-state-value,
        [data-testid="stMain"] .cc-answer-option {
            font-size: var(--qa-body-size) !important;
        }
        /* Sidebar: the Concept Check switch sits on one line with its label. */
        [data-testid="stSidebar"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"] {
            align-items: center;
        }
        [data-testid="stSidebar"] [data-testid="stCheckbox"] label p {
            font-size: 1.1rem !important;
            font-weight: 650;
            line-height: 1.3;
        }
        .qa-section-gap { margin-top: 28px !important; }
        .st-key-qa-practice-control [data-testid="stCheckbox"] label {
            display: flex;
            align-items: center !important;
        }
        .st-key-qa-practice-control [data-testid="stCheckbox"] label p {
            font-size: var(--qa-body-size) !important;
            font-weight: 700 !important;
            line-height: 1.3 !important;
            margin: 0 !important;
        }
        .qa-section-help {
            margin: -2px 0 10px;
            color: var(--cs30-muted, #706a64);
            font-size: var(--qa-body-size) !important;
            line-height: 1.5;
        }
        /* The Apply button matches the height of the inputs beside it. */
        .st-key-qa-adjust [data-testid="stButton"] button {
            min-height: 40px !important;
            height: 40px !important;
            padding-top: 0;
            padding-bottom: 0;
        }
        /* Section headings share the title's heavier weight and tighter spacing. */
        [data-testid="stMain"] h3, [data-testid="stMain"] h4,
        [data-testid="stMainBlockContainer"] h3, [data-testid="stMainBlockContainer"] h4 {
            font-weight: 700 !important;
            letter-spacing: -0.02em !important;
        }
        [data-testid="stExpandSidebarButton"]::after {
            content: "Session report" !important;
            font-size: var(--qa-body-size) !important;
        }
        [data-testid="stSidebar"][aria-expanded="true"] {
            width: var(--qa-report-width, 300px) !important;
            max-width: 60vw !important;
            min-width: min(250px, 60vw) !important;
        }
        .st-key-qa-open-demo {
            position: fixed;
            left: var(--qa-demo-x, 180px);
            top: var(--qa-demo-y, 11px);
            width: auto !important;
            z-index: 999990;
        }
        .st-key-qa-open-demo div[data-testid="stButton"] > button[kind="secondary"] {
            min-height: 38px !important;
            padding: 6px 14px !important;
            border-radius: 999px !important;
            border: 1px solid #f06f54 !important;
            background: #fff4f1 !important;
            color: #df5b40 !important;
        }
        .st-key-qa-open-demo div[data-testid="stButton"] > button[kind="secondary"]:hover {
            background: #ffe6df !important;
        }
        .st-key-qa-open-demo [data-testid="stButton"] button p {
            font-size: var(--qa-body-size) !important;
            font-weight: 650 !important;
        }
        /* Secondary actions (Undo, Skip) are outlined so the primary action stands out. */
        div[data-testid="stButton"] > button[kind="secondary"] {
            border: 1px solid #f06f54 !important;
            color: #df5b40 !important;
            background: #ffffff !important;
        }
        div[data-testid="stButton"] > button[kind="secondary"] p { color: #df5b40 !important; }
        div[data-testid="stButton"] > button[kind="secondary"]:hover {
            background: #fff4f1 !important;
        }
        div[data-testid="stButton"] > button p { font-size: 1rem !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_report_panel(run, corpus, directory, enabled) -> None:
    """Render the report inside Streamlit's native sidebar."""

    with st.sidebar:
        st.markdown("## Session report")
        if isinstance(run, QuestionRun) and corpus is not None:
            render_report(run, corpus, directory, enabled)
        else:
            st.info("Run a question first. Reports are derived from recorded practice events.")


def render_report(run, corpus, directory, enabled):
    runtime = refresh_controls(run, corpus, directory, enabled)
    try:
        events = runtime.event_store.events(runtime.profile.profile_id)
        if not events:
            st.info("No events have been recorded for this profile yet.")
            return
        report = build_concept_check_report(
            events,
            starting_levels={runtime.profile.profile_id: runtime.profile.level},
            topic_registry=corpus.registry,
        )
        st.markdown(compact_report_headings(render_concept_check_markdown(report)))
        downloads = [
            ("CSV", render_concept_check_csv, "csv", "text/csv"),
            ("JSON", render_concept_check_json, "json", "application/json"),
            ("Markdown", render_concept_check_markdown, "md", "text/markdown"),
        ]
        for column, (label, renderer, suffix, mime) in zip(
            st.columns(len(downloads)), downloads, strict=True
        ):
            column.download_button(
                f"Download {label}",
                renderer(report),
                f"session.{suffix}",
                mime=mime,
                on_click="ignore",  # downloading does not rerun the page
            )
    except Exception:
        st.warning("The report is unavailable. Recorded events have been retained.")


BACK_TO_TOP_JS = """
<script>
(function () {
  const doc = window.parent.document;
  const win = doc.defaultView;
  doc.qaSidebarLayoutCleanup?.();
  const placeDemoButton = () => {
    const sidebar = doc.querySelector('[data-testid="stSidebar"]');
    if (sidebar?.getAttribute("aria-expanded") === "true") {
      doc.documentElement.style.setProperty(
        "--qa-demo-x", sidebar.getBoundingClientRect().right + 18 + "px"
      );
      doc.documentElement.style.setProperty("--qa-demo-y", "11px");
    } else {
      const reportButton = doc.querySelector('[data-testid="stExpandSidebarButton"]');
      if (reportButton) {
        const rect = reportButton.getBoundingClientRect();
        doc.documentElement.style.setProperty("--qa-demo-x", rect.right + 10 + "px");
        doc.documentElement.style.setProperty("--qa-demo-y", rect.top + "px");
      }
    }
  };
  // Follow the native collapse animation, including its final frame.
  let frame;
  const followLayout = () => {
    win.cancelAnimationFrame(frame);
    const until = win.performance.now() + 400;
    const tick = () => {
      placeDemoButton();
      if (win.performance.now() < until) frame = win.requestAnimationFrame(tick);
    };
    tick();
  };
  const sidebar = doc.querySelector('[data-testid="stSidebar"]');
  doc.qaDemoButtonObserver?.disconnect();
  const sizeObserver = new ResizeObserver(followLayout);
  if (sidebar) sizeObserver.observe(sidebar);
  doc.qaDemoHeaderObserver?.disconnect();
  const stateObserver = new MutationObserver(followLayout);
  if (sidebar) stateObserver.observe(sidebar, { attributes: true,
    attributeFilter: ["aria-expanded"] });
  const header = doc.querySelector('[data-testid="stHeader"]');
  if (header) stateObserver.observe(header, { childList: true, subtree: true });

  // Keep the native sidebar and handle; allow report tables up to 60% of the viewport.
  const setReportWidth = (width) => {
    const maximum = win.innerWidth * 0.6;
    const bounded = Math.max(Math.min(250, maximum), Math.min(width, maximum));
    doc.documentElement.style.setProperty("--qa-report-width", bounded + "px");
    return bounded;
  };
  let savedWidth;
  try { savedWidth = Number(win.localStorage.getItem("qa-report-width")); } catch {}
  setReportWidth(savedWidth > 0 ? savedWidth : sidebar?.getBoundingClientRect().width || 300);
  let dragging = false;
  let previousUserSelect;
  const resizeHandleSelector = '[data-testid="stSidebarResizeHandle"], '
    + '[data-testid="stSidebar"] div[style*="cursor: col-resize"]';
  const rememberWidth = (width) => {
    try { win.localStorage.setItem("qa-report-width", String(width)); } catch {}
  };
  const startResize = (event) => {
    if (event.button !== 0 ||
        !event.target.closest(resizeHandleSelector)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    dragging = true;
    previousUserSelect = doc.body.style.userSelect;
    doc.body.style.userSelect = "none";
  };
  const moveResize = (event) => {
    if (!dragging) return;
    event.preventDefault();
    const current = doc.querySelector('[data-testid="stSidebar"]');
    if (current) setReportWidth(event.clientX - current.getBoundingClientRect().left);
    placeDemoButton();
  };
  const stopResize = () => {
    if (!dragging) return;
    dragging = false;
    doc.body.style.userSelect = previousUserSelect;
    rememberWidth(parseFloat(doc.documentElement.style.getPropertyValue("--qa-report-width")));
  };
  const resetWidth = (event) => {
    if (!event.target.closest(resizeHandleSelector)) return;
    rememberWidth(setReportWidth(300));
    followLayout();
  };
  const resizeWindow = () => {
    setReportWidth(parseFloat(doc.documentElement.style.getPropertyValue("--qa-report-width")));
    followLayout();
  };
  doc.addEventListener("mousedown", startResize, true);
  doc.addEventListener("mousemove", moveResize, true);
  doc.addEventListener("mouseup", stopResize, true);
  doc.addEventListener("dblclick", resetWidth, true);
  win.addEventListener("blur", stopResize);
  win.addEventListener("resize", resizeWindow);
  doc.qaSidebarLayoutCleanup = () => {
    stopResize();
    win.cancelAnimationFrame(frame);
    sizeObserver.disconnect();
    stateObserver.disconnect();
    doc.removeEventListener("mousedown", startResize, true);
    doc.removeEventListener("mousemove", moveResize, true);
    doc.removeEventListener("mouseup", stopResize, true);
    doc.removeEventListener("dblclick", resetWidth, true);
    win.removeEventListener("blur", stopResize);
    win.removeEventListener("resize", resizeWindow);
  };
  followLayout();
  // Remove controls and observers from the retired custom report sidebar.
  ["qa-report-open", "qa-report-close", "qa-report-handle", "qa-report-pill",
   "qa-floating-style", "qa-floating-style-v2", "qa-floating-style-v3",
   "qa-floating-style-v4", "qa-floating-style-v5"].forEach((id) => {
    doc.getElementById(id)?.remove();
  });
  if (doc.qaReport) doc.qaReport.open = false;
  if (doc.qaReportIndependent) doc.qaReportIndependent.open = false;
  doc.qaSidebarObserver?.disconnect();
  doc.body.classList.remove("qa-report-open", "qa-resizing");
  let button = doc.getElementById("qa-back-to-top");
  if (button) button.remove();
  button = doc.createElement("button");
  button.id = "qa-back-to-top";
  button.type = "button";
  button.textContent = "↑";
  button.title = "Back to the question box";
  button.setAttribute("aria-label", "Back to the question box");
  button.style.cssText = "position:fixed;right:28px;bottom:28px;z-index:9990;"
    + "width:46px;height:46px;border:0;border-radius:50%;background:#f06f54;"
    + "color:white;font-size:24px;cursor:pointer;display:none;";
  button.onclick = () => {
    const box = doc.querySelector(".st-key-qa-question");
    box?.scrollIntoView({ behavior: "smooth", block: "start" });
    box?.querySelector("textarea")?.focus({ preventScroll: true });
  };
  doc.body.appendChild(button);
  if (doc.qaQuestionScrollHandler) {
    doc.removeEventListener("scroll", doc.qaQuestionScrollHandler, true);
  }
  doc.qaQuestionScrollHandler = () => {
    const box = doc.querySelector(".st-key-qa-question");
    button.style.display = box && box.getBoundingClientRect().bottom < 0 ? "block" : "none";
  };
  doc.addEventListener("scroll", doc.qaQuestionScrollHandler, true);
  doc.qaQuestionScrollHandler();
})();
</script>
"""


SCROLL_TO_ANSWER_JS = """
<script>
// run: %s
(function () {
  const doc = window.parent.document;
  let tries = 0;
  const go = () => {
    const answer = doc.querySelector(".st-key-qa-answer");
    if (!answer) { if (tries++ < 40) setTimeout(go, 50); return; }
    let el = answer;
    while (el && !(el.scrollHeight > el.clientHeight &&
                   /(auto|scroll)/.test(getComputedStyle(el).overflowY))) {
      el = el.parentElement;
    }
    const scroller = el || doc.scrollingElement;
    const top = answer.getBoundingClientRect().top
      - (el ? el.getBoundingClientRect().top : 0) + scroller.scrollTop - 72;
    scroller.scrollTo({ top: Math.max(top, 0), behavior: "smooth" });
  };
  go();
})();
</script>
"""


def scroll_to_answer(run_id: str) -> None:
    """After a new answer, bring the Answer heading into view (once per run)."""

    components.html(SCROLL_TO_ANSWER_JS % escape(run_id), height=0)


def render_back_to_top() -> None:
    """Floating up-arrow that appears once the question box has scrolled out of view."""

    components.html(BACK_TO_TOP_JS, height=0)


def demo_settings() -> dict:
    """Keep configuration independently of dialog widget cleanup on dismissal."""

    return dict(
        st.session_state.setdefault(
            "qa-demo-settings",
            {
                "mode": LIVE_MODE
                if os.environ.get("DEEPINFRA_API_KEY", "").strip()
                else FIXTURE_MODE,
                "model": next(iter(TEAM_MODELS)),
                "retrieval": next(iter(RETRIEVAL_OPTIONS)),
            },
        )
    )


def save_demo_settings() -> None:
    previous = demo_settings()
    updated = {
        "mode": st.session_state.get("qa-mode", previous["mode"]),
        "model": st.session_state.get("qa-model", previous["model"]),
        "retrieval": st.session_state.get("qa-retrieval", previous["retrieval"]),
    }
    if updated != previous:
        clear_question()
    st.session_state["qa-demo-settings"] = updated


def close_demo_mode() -> None:
    save_demo_settings()
    st.session_state["qa-demo-open"] = False


@st.dialog("Demo Mode", width="small", on_dismiss=close_demo_mode)
def show_demo_mode() -> None:
    """Open existing operator controls in a native modal without resizing the page."""

    settings = demo_settings()
    for key, value in (
        ("qa-mode", settings["mode"]),
        ("qa-model", settings["model"]),
        ("qa-retrieval", settings["retrieval"]),
    ):
        st.session_state.setdefault(key, value)
    modes = [LIVE_MODE, FIXTURE_MODE]
    mode = st.selectbox(
        "Demo mode",
        modes,
        key="qa-mode",
        on_change=save_demo_settings,
        label_visibility="collapsed",
    )
    live = mode == LIVE_MODE
    st.caption(
        "Fixture mode needs no API key: test corpus + simulated answers, "
        "full pipeline and Concept Check."
    )
    st.selectbox(
        "Answer model",
        list(TEAM_MODELS),
        format_func=lambda value: TEAM_MODELS[value].label,
        key="qa-model",
        on_change=save_demo_settings,
        disabled=not live,
    )
    st.caption("One model answers each question. The three models are evaluated separately.")
    st.selectbox(
        "Retrieval",
        list(RETRIEVAL_OPTIONS),
        format_func=lambda value: RETRIEVAL_OPTIONS[value],
        key="qa-retrieval",
        on_change=save_demo_settings,
        disabled=not live,
    )
    if not live:
        st.caption("Fixture mode searches the small test corpus with BM25 (no Qwen3 index).")
    else:
        st.caption(
            "Hybrid is the team's selected retriever (decision table 2026-10-23). "
            "Top-5 fused results go to the answer model."
        )
    with st.expander("Connection details"):
        st.write(
            "DeepInfra key: "
            + ("configured" if os.environ.get("DEEPINFRA_API_KEY") else "not configured")
        )
        st.caption(
            "Set DEEPINFRA_API_KEY in the server terminal. Do not paste it into reports or chat."
        )
        st.write(f"Hybrid index folder: `{hybrid_index_dir()}`")
        st.caption(
            "Retrieval reuses M6's code path (materialise_v2_retrieval_view -> "
            "build_real_retrieval_deps) and M7's freeze_v2_retrieval converter. "
            "M7's level-aware Role reranking (lambda) is not applied on this page."
        )
    if st.button("Done", type="primary", use_container_width=True):
        close_demo_mode()
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="CS-30 · Ask a question", page_icon="🎓", layout="wide")
    inject_v2_styles()
    inject_concept_check_styles()
    inject_qa_styles()
    directory = session_directory()
    if st.button("Demo Mode", key="qa-open-demo"):
        st.session_state["qa-demo-open"] = True
    if st.session_state.get("qa-demo-open", False):
        show_demo_mode()
    settings = demo_settings()
    mode = settings["mode"]
    live = mode == LIVE_MODE
    model_id = settings["model"]
    retrieval_kind = settings["retrieval"] if live else "bm25"
    st.markdown('<p class="v2-eyebrow">CS-30 / VERSION 2</p>', unsafe_allow_html=True)
    st.title("Personalised Learning Assistant")
    st.caption(
        "Answers are grounded in four physics textbooks. Check the evidence, "
        "then test yourself with a Concept Check."
    )
    if live:
        st.info(
            f"TEAM MODEL · {TEAM_MODELS[model_id].label} · DeepInfra · "
            f"V2 four-book corpus · {RETRIEVAL_OPTIONS[retrieval_kind]}"
        )
    else:
        st.warning(
            "FIXTURE MODE · SYNTHETIC CORPUS + SIMULATED ANSWERS · Not model-quality evidence"
        )
    st.session_state.setdefault("qa-question", EXAMPLES["Acceleration"])
    render_back_to_top()
    st.markdown("### Starting level")
    level_column, practice_column = st.columns(2, gap="large", vertical_alignment="center")
    with level_column:
        level = st.selectbox(
            "Starting level",
            list(StudentLevel),
            format_func=lambda x: x.value.title(),
            key="qa-level",
            on_change=clear_question,
            label_visibility="collapsed",
        )
    with practice_column:
        with st.container(key="qa-practice-control"):
            enabled = st.toggle(
                "Enable Concept Check", value=False, key="qa-enabled", on_change=clear_practice
            )
    level_help, practice_help = st.columns(2, gap="large")
    level_help.caption("Choose your physics background as the starting point for explanations.")
    practice_help.caption(
        "Optional practice and dynamic Topic levels. Changes apply to your next generated answer."
    )
    st.markdown("### Ask a physics question")
    st.text_area(
        "Your physics question", key="qa-question", height=110, label_visibility="collapsed"
    )
    st.markdown('<p class="qa-helper-title">Try an example</p>', unsafe_allow_html=True)
    st.pills(
        "Try a prepared question",
        options=list(EXAMPLES),
        selection_mode="single",
        key="qa-example",
        on_change=apply_example,
        label_visibility="collapsed",
    )
    learning = st.container()
    topic_dir = Path(__file__).resolve().parents[3] / "artifacts/v2/topics/releases/2.0.0-rc.1"
    corpus_path = os.environ.get("CS30_UI_CORPUS", "")
    cache_key = f"qa-corpus-{live}-{corpus_path}"
    corpus = None
    try:
        if cache_key not in st.session_state:
            st.session_state[cache_key] = load_ui_corpus(
                Path(corpus_path) if corpus_path else None, topic_dir, synthetic=not live
            )
        corpus = st.session_state[cache_key]
    except (OSError, ValueError) as exc:
        st.error(f"V2 corpus readiness check failed: {exc}")
    with learning:
        missing_key = live and not os.environ.get("DEEPINFRA_API_KEY", "").strip()
        missing_index = (
            live
            and retrieval_kind == "hybrid"
            and not (hybrid_index_dir() / "index" / "index.faiss").is_file()
        )
        if missing_index:
            st.error(
                f"M6 Qwen3 hybrid index not found at {hybrid_index_dir()}. "
                "Set CS30_UI_HYBRID_INDEX to the qwen3-embedding folder from the "
                "m6-w6-qwen3-hybrid-dev-v1 release. No BM25 fallback is used."
            )
        if missing_key:
            st.warning(
                "DeepInfra is not configured on this machine. Generate answer becomes "
                "available after setup. Switch Demo mode to Fixture mode to test the "
                "full workflow without a key."
            )
        generate_column, _ = st.columns(2)  # same width as Next question / Quiz me
        clicked = generate_column.button(
            "Generate answer" if live else "Generate answer · fixture",
            type="primary",
            disabled=corpus is None or missing_key or missing_index,
            use_container_width=True,
        )
        if clicked:
            clear_question()
            profile = StudentProfile(
                profile_id=f"qa-{directory.name}-{live}-{level.value}", level=level
            )
            try:
                with st.status("Running V2 question-answering pipeline", expanded=True) as status:
                    retriever = get_retriever(retrieval_kind, corpus, directory, corpus_path)
                    run = run_question(
                        st.session_state["qa-question"],
                        profile,
                        corpus,
                        retriever,
                        directory,
                        enabled=enabled,
                        live=live,
                        model_id=model_id,
                        progress=st.write,
                    )
                    st.session_state["qa-run"] = run
                    st.session_state["qa-scroll-to-answer"] = run.run_id
                    status.update(label="Pipeline completed", state="complete", expanded=False)
            except Exception as exc:
                st.error(
                    f"The pipeline stopped ({type(exc).__name__}). "
                    "No fallback answer was substituted."
                )
                if isinstance(exc, ValueError):
                    st.caption(str(exc))
        run = st.session_state.get("qa-run")
        if isinstance(run, QuestionRun):
            if st.session_state["qa-question"].strip() != run.runtime.retrieval.query:
                st.warning(
                    "The input has changed. "
                    "The result below belongs to the previous submitted question."
                )
            st.caption(f"Submitted question: {run.runtime.retrieval.query}")
            with st.container(key="qa-answer"):
                render_answer(run)
            scroll_id = st.session_state.pop("qa-scroll-to-answer", None)
            if scroll_id:
                scroll_to_answer(scroll_id)
            try:
                render_practice(run, corpus, directory, enabled)
            except OSError:
                st.error("Practice storage is unavailable. No saved progress is claimed.")
            with st.expander("Technical run details"):
                st.json(
                    {
                        "run_id": run.run_id,
                        "mode": run.mode,
                        "steps": run.steps,
                        "model": run.trace.model if run.trace else None,
                        "retrieval": run.steps[0],
                        "corpus": run.runtime.retrieval.provenance.model_dump(mode="json"),
                        "profile_source": run.prepared.snapshot.profile_source.value,
                        "generation_level": run.prepared.snapshot.profile.level.value,
                        "retrieval_topic": run.prepared.retrieval_topic.model_dump(mode="json")
                        if run.prepared.retrieval_topic
                        else None,
                    }
                )
        else:
            st.info(
                "Enter a question and run the pipeline to see an answer, "
                "sources and practice availability."
            )
            if enabled:
                st.caption(
                    "Concept Check is on. After the answer appears, scroll below it for "
                    "**Quiz me**, **Topic progress** and **Adjust this Topic level** "
                    "(new level + reason)."
                )
    render_report_panel(st.session_state.get("qa-run"), corpus, directory, enabled)


if __name__ == "__main__":
    main()
