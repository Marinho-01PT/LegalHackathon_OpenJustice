"""Visual layer: palette in .streamlit/config.toml, the rest here.
Ink #1D2622 · paper #F3F5F2 · Amtsgrün #2F5D50 · Frist-Amber #A8620F · muted #66716B"""
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap');
:root { --ink:#1D2622; --green:#2F5D50; --green-soft:#E1EBE6; --amber:#A8620F; --amber-soft:#F8EEDF;
        --muted:#66716B; --line:#D3D9D2; --paper:#FFFFFF; }
.block-container { max-width: 1120px; padding-top: 2.4rem; }
h1, h2, h3, h4 { letter-spacing: -0.015em; }

/* page head */
.oj-head h1 { font-size: 2.5rem; font-weight: 700; line-height: 1.1; margin: 0 0 .5rem; padding: 0; }
.oj-head p { color: var(--muted); font-size: 1.08rem; max-width: 62ch; margin: 0 0 1.6rem; }

/* answer: serif for reading legal text */
[class*="st-key-oj-answer"] p, [class*="st-key-oj-answer"] li {
  font-family: 'Source Serif 4', Georgia, serif; font-size: 1.06rem; line-height: 1.68; max-width: 68ch; }
[class*="st-key-oj-answer"] h4 { font-size: 1.02rem; font-weight: 600; margin: 1.1rem 0 .2rem; padding: 0; }
[class*="st-key-oj-deadline"] { background: var(--amber-soft); border-left: 3px solid var(--amber);
  border-radius: 0 6px 6px 0; padding: .8rem 1rem .3rem; margin: .8rem 0; }
[class*="st-key-oj-deadline"] strong { color: var(--amber); }

/* outcome */
.oj-outcome { display:flex; align-items:baseline; gap:.7rem; margin:.2rem 0 1rem; }
.oj-outcome .k { color: var(--muted); font-size:.9rem; }
.oj-outcome .v { font-size:1.35rem; font-weight:700; color: var(--green); }
.oj-arm { font-weight:600; font-size:1.05rem; margin-bottom:.3rem; }
.oj-arm span { color: var(--muted); font-weight:400; font-size:.9rem; margin-left:.4rem; }

/* Prüfpfad: the protocol path the case walked */
.oj-path { position:relative; margin:.4rem 0 0 .45rem; padding-left:1.5rem; border-left:2px solid var(--line); }
.oj-step { position:relative; padding:0 0 1.05rem; }
.oj-step::before { content:""; position:absolute; left:calc(-1.5rem - 8px); top:.32rem; box-sizing:border-box;
  width:14px; height:14px; border-radius:50%; background:var(--paper); border:2px solid var(--green); }
.oj-step.fact::before { border-color:#9AA49E; }
.oj-step.outcome { padding-bottom:0; }
.oj-step.outcome::before { background:var(--green); width:18px; height:18px; left:calc(-1.5rem - 10px); top:.2rem; }
.oj-step .lbl { font-weight:600; }
.oj-step.running::before { border-style:dashed; animation: oj-spin 1.6s linear infinite; }
.oj-step.running .lbl { color: var(--muted); font-weight:500; }
@keyframes oj-spin { to { transform: rotate(360deg); } }
.oj-step.outcome .lbl { color: var(--green); font-size:1.05rem; }
.oj-step .val { display:inline-block; margin-left:.45rem; padding:.05rem .55rem; border-radius:999px;
  background:var(--green-soft); color:var(--green); font-size:.84rem; font-weight:600; }
.oj-step .val.no { background:var(--amber-soft); color:var(--amber); }
.oj-step.fact .val { background:#ECEFEA; color:var(--muted); font-weight:500; }
.oj-step .q { color:var(--muted); font-size:.88rem; margin-top:.1rem; }
.oj-step details { margin-top:.2rem; }
.oj-step summary { color:var(--green); font-size:.85rem; cursor:pointer; }
.oj-step .det { font-size:.88rem; color:var(--ink); background:var(--paper); border:1px solid var(--line);
  border-radius:6px; padding:.5rem .7rem; margin-top:.3rem; white-space:pre-wrap; }

/* sources */
.oj-src { display:flex; flex-wrap:wrap; gap:.4rem; margin:.3rem 0 .4rem; }
.oj-src a, .oj-src span { text-decoration:none; font-size:.86rem; padding:.15rem .6rem; border-radius:999px;
  border:1px solid var(--line); color:var(--ink); background:var(--paper); }
.oj-src .ok { border-color:#9DBDB0; } .oj-src .ok::before { content:"✓ "; color:var(--green); font-weight:700; }
.oj-src .missing { border-color:#E0B98A; background:var(--amber-soft); } .oj-src .missing::before { content:"✕ "; color:var(--amber); font-weight:700; }
.oj-src .unchecked { color:var(--muted); }

/* FAQ rows */
[class*="st-key-oj-faq-"] { border-bottom:1px solid var(--line); padding:.35rem 0 .55rem; }
.oj-meta { color: var(--muted); font-size:.88rem; }
.oj-status { display:flex; align-items:center; gap:.5rem; font-size:.9rem; }
.oj-status i { width:9px; height:9px; border-radius:50%; display:inline-block; }

@media (prefers-reduced-motion: reduce) { * { transition:none !important; animation:none !important; } }
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def head(title: str, lead: str) -> None:
    import html
    st.markdown(f'<div class="oj-head"><h1>{html.escape(title)}</h1><p>{html.escape(lead)}</p></div>',
                unsafe_allow_html=True)
