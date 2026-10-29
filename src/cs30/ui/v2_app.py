"""V2 UI entry point: a single learning page (question answering + optional practice).

The older fixture-only page (v2_fixture.py) is kept on disk but no longer listed in
the navigation, so the demo shows one learning flow.
"""

import streamlit as st


def main() -> None:
    st.navigation(
        [
            st.Page("qa_app.py", title="Ask a question", icon="🎓", default=True),
        ],
        position="hidden",
    ).run()


if __name__ == "__main__":
    main()
