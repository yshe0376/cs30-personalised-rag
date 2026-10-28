"""Complete V2 UI navigation: question answering first, fixture examples second."""

import streamlit as st


def main() -> None:
    st.navigation(
        [
            st.Page("qa_app.py", title="Ask a question", icon="🎓", default=True),
            st.Page("v2_fixture.py", title="Concept Check examples", icon="🧪"),
        ]
    ).run()


if __name__ == "__main__":
    main()
