import io
import re
import fitz  # PyMuPDF
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Swim Team Highlighter", layout="wide")
st.title("Swim Team / Name Highlighter")

uploaded_file = st.file_uploader("Upload psych sheet PDF", type=["pdf"])

search_type = st.radio(
    "Search by:",
    ["Team Code", "Swimmer Name"],
    horizontal=True
)

query_input = st.text_input(
    "Enter your search term:",
    placeholder="e.g. MAC-MA or John Smith"
)

st.info("Search is case-insensitive and line-based.")


# ------------------------------------------------------------
# UTILITIES
# ------------------------------------------------------------

def normalize(s: str) -> str:
    return s.lower().strip()


def contains_whole_team(line: str, team: str) -> bool:
    """Ensure the team code match is not part of a longer code."""
    line_low = normalize(line)
    return any([
        line_low == team,
        line_low.startswith(team + " "),
        line_low.endswith(" " + team),
        f" {team} " in line_low,
        line_low.startswith(team + "\t"),
        line_low.endswith("\t" + team),
        f"\t{team}\t" in line_low,
    ])


def find_matches(doc, query, mode):
    q = normalize(query)
    matches = []

    for pageno in range(len(doc)):
        page = doc[pageno]
        lines = page.get_text("text").splitlines()

        for i, line in enumerate(lines):
            line_low = normalize(line)
            if mode == "Team Code":
                if contains_whole_team(line, q):
                    matches.append({"page": pageno, "line_num": i, "text": line})
            else:  # Swimmer Name
                if q in line_low:
                    matches.append({"page": pageno, "line_num": i, "text": line})

    return matches


def highlight_lines(input_bytes: bytes, matches):
    """Highlight the full line for each matched line. Returns PDF bytes."""
    doc = fitz.open(stream=input_bytes, filetype="pdf")

    for m in matches:
        page = doc[m["page"]]
        blocks = page.get_text("dict")["blocks"]

        target_text = normalize(m["text"])
        highlighted = False

        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                span_text = " ".join([span["text"] for span in line["spans"]]).strip()
                if normalize(span_text) == target_text:
                    x0 = min(span["bbox"][0] for span in line["spans"])
                    y0 = min(span["bbox"][1] for span in line["spans"])
                    x1 = max(span["bbox"][2] for span in line["spans"])
                    y1 = max(span["bbox"][3] for span in line["spans"])
                    rect = fitz.Rect(x0, y0, x1, y1)
                    try:
                        annot = page.add_highlight_annot(rect)
                        annot.update()
                        highlighted = True
                    except Exception:
                        pass
        # fallback: if no annotation worked, just skip
        if not highlighted:
            continue

    out = io.BytesIO()
    doc.save(out)
    doc.close()
    out.seek(0)
    return out.read()


# ------------------------------------------------------------
# MAIN APP LOGIC
# ------------------------------------------------------------

if uploaded_file and query_input.strip():
    raw = uploaded_file.read()

    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception as e:
        st.error(f"Failed to open PDF: {e}")
        st.stop()

    matches = find_matches(doc, query_input, search_type)

    if not matches:
        st.warning("No matches found. You can still download the original PDF.")
        highlighted = raw  # return original PDF
    else:
        st.success(f"Found **{len(matches)}** matching lines.")

        df = pd.DataFrame([
            {"Page": m["page"] + 1, "Line": m["line_num"] + 1, "Text": m["text"]}
            for m in matches
        ])
        st.dataframe(df, use_container_width=True)

        with st.spinner("Generating highlighted PDF…"):
            highlighted = highlight_lines(raw, matches)

    # debug info: show size of PDF
    st.write(f"Prepared PDF file size: {len(highlighted)} bytes")

    st.download_button(
        "Download Highlighted PDF",
        data=highlighted,
        file_name=f"highlighted.pdf",
        mime="application/pdf"
    )

else:
    st.info("Upload a PDF and enter a team code or swimmer name.")
