"""Häufige Fragen: curated example situations (data/faq.json). One click runs them on the ask page."""
import streamlit as st

from app.core.content import load_faq
from app.ui import nav, theme


def render() -> None:
    theme.head("Häufige Fragen",
               "Typische Situationen aus dem Mietalltag. Wählen Sie eine aus, um sie prüfen zu lassen, "
               "oder passen Sie den Text danach an Ihren Fall an.")
    items = load_faq()
    if not items:
        st.info("Noch keine Fragen hinterlegt. Ergänzen Sie data/faq.json (Felder: id, topic, question, situation).")
        return
    topics = list(dict.fromkeys(i.get("topic", "Allgemein") for i in items))
    for topic in topics:
        st.subheader(topic)
        for it in (i for i in items if i.get("topic", "Allgemein") == topic):
            with st.container(key=f"oj-faq-{it['id']}"):
                c1, c2 = st.columns([5, 1.1], vertical_alignment="center")
                c1.markdown(f"**{it['question']}**")
                c1.markdown(f'<div class="oj-meta">{it["situation"]}</div>', unsafe_allow_html=True)
                if c2.button("Prüfen", key=f"faq-{it['id']}", width="stretch"):
                    st.session_state["prefill"] = {"facts": it["situation"], "question": it["question"]}
                    st.session_state.pop("ask", None)
                    st.switch_page(nav.PAGES["ask"])
        st.write("")
