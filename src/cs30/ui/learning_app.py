"""Compatibility entry: online learning now lives on the shared M8 page."""

import streamlit as st

from cs30.ui.qa_app import ONLINE_MODE, main

if __name__ == "__main__":
    st.session_state.setdefault(
        "qa-demo-settings",
        {"mode": ONLINE_MODE, "model": "openai/gpt-oss-20b", "retrieval": "hybrid"},
    )
    main()
