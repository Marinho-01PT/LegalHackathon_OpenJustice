import streamlit as st

from app.core.service import friendly_error
from app.ui import state


def render() -> None:
    s, svc = state.settings(), state.service()
    with st.sidebar:
        st.markdown(f"### {s.app_name}")
        if svc.mock:
            st.markdown('<div class="oj-status"><i style="background:#A8620F"></i>Demo-Modus</div>', unsafe_allow_html=True)
            st.caption("Kein API-Key aktiv: Die Antworten sind Platzhalter. Tragen Sie OJ_API_KEY in der Datei .env ein.")
        else:
            st.markdown('<div class="oj-status"><i style="background:#2F5D50"></i>Verbunden mit OpenJustice</div>',
                        unsafe_allow_html=True)
        st.write("")

        try:
            protos = state.protocols(s.cache_key)
        except Exception as exc:
            st.error(friendly_error(exc))
            protos = []
        names = {p["id"]: p["name"] for p in protos}
        if s.default_protocol and s.default_protocol not in names and not svc.mock:
            names[s.default_protocol] = s.default_protocol
        ids = list(names)
        if ids:
            idx = ids.index(s.default_protocol) if s.default_protocol in ids else 0
            st.selectbox("Prüfschema", ids, index=idx, format_func=lambda i: names[i], key="protocol_id",
                         help="Das Protokoll, das euer Legal-Team im OpenJustice-Editor gebaut hat.")
            _scope_note(svc, st.session_state.get("protocol_id"))
        else:
            st.warning("Kein Prüfschema gefunden. Erstellen Sie eines in OpenJustice oder setzen Sie OJ_PROTOCOL_ID.")

        try:
            mods = state.models(s.cache_key)
        except Exception as exc:
            st.error(friendly_error(exc))
            mods = [s.default_model] if s.default_model else []
        if mods:
            pref = s.default_model if s.default_model in mods else next((m for m in mods if "apertus" in m.lower()), mods[0])
            st.selectbox("Modell", mods, index=mods.index(pref), key="model",
                         help="Beide Varianten (mit und ohne Prüfschema) laufen auf diesem Modell.")

        if st.button("Liste aktualisieren", type="tertiary", icon=":material/refresh:"):
            st.cache_data.clear()
            st.rerun()
        st.divider()
        st.caption("Orientierungshilfe, keine Rechtsberatung und kein Entscheid.")


def _scope_note(svc, pid) -> None:
    """Quiet note under the protocol selector: what it covers (APP_SCOPE or the protocol's description)."""
    import html
    import os
    if not pid:
        return
    scope = os.environ.get("APP_SCOPE", "").strip()
    if not scope:
        try:
            scope = svc.protocol_info(pid).get("description", "")
        except Exception:
            scope = ""
    if scope:
        st.markdown(f'<div class="oj-scope">{html.escape(scope)}<br><span>Für andere Themen ist die Einschätzung '
                    f'nicht verlässlich.</span></div>', unsafe_allow_html=True)
