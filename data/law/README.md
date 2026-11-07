# Law texts (Gesetzestexte)

Used for two things:
1. **Upload to OpenJustice** (`python3 -m ojbench upload <file> --code OR`) → the `plan_based_rag` engine reads and
   quotes them; quotes are verified server-side (`/file-library/citations/pinpoints`). IDs land in `files.json`.
2. **Local article check** (`*.txt`, file name = law code, e.g. `OR.txt`) → every "Art. 269d OR" in an answer is
   checked for existence (metric `articles exist`).

## How to get them (Fedlex, official, free – Swiss laws are not copyrighted, Art. 5 URG)
1. Open fedlex.admin.ch → SR 220 (OR), version in force → HTML / print view.
2. Download the current version as **PDF** (for the upload) and **HTML**.
3. Make the text file: open the HTML in the browser → select all → copy → paste into `data/law/OR.txt`
   (or: `textutil -convert txt OR.html -output OR.txt` on macOS). Lines must start with "Art. 253", "Art. 269d" …
4. Partial texts are fine: only articles inside the covered range (e.g. 253–274g) are checked, others stay "unchecked".
