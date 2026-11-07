"""Entry point:  streamlit run app/streamlit_app.py   (from the repo root)

app/core   OpenJustice access, data, checks (no Streamlit; reusable from CLI/tests)
app/ui     theme, shared components, cached state, sidebar
app/views  one module per page; add a page = add a module + one st.Page line below
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import streamlit as st  # noqa: E402

from app.ui import nav, sidebar, state, theme  # noqa: E402
from app.views import ask, cases, faq  # noqa: E402

st.set_page_config(page_title=state.settings().app_name, page_icon="⚖️", layout="wide")
theme.inject()

nav.PAGES.update({
    "ask": st.Page(ask.render, title="Frage stellen", icon=":material/edit_note:", url_path="frage", default=True),
    "faq": st.Page(faq.render, title="Häufige Fragen", icon=":material/help_outline:", url_path="faq"),
    "cases": st.Page(cases.render, title="Fälle vergleichen", icon=":material/compare_arrows:", url_path="vergleich"),
})
page = st.navigation(list(nav.PAGES.values()))
sidebar.render()
page.run()
