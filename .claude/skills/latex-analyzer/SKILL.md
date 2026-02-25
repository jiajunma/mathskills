---
name: latex-analyzer
description: Analyze LaTeX (.tex) files to extract mathematical structure — definitions, theorems, lemmas, propositions, corollaries, proofs — build dependency graphs, and generate interactive Blueprint-style visualizations. Use when working with .tex files containing mathematical content, when asked to analyze a paper's structure, or when building a dependency graph of mathematical results.
argument-hint: [path-to-tex-file]
allowed-tools: ["Bash(python3 *)", "Read", "Write", "Glob", "Grep"]
---

# LaTeX Analyzer — Mathematical Structure Extraction

## Workflow

When invoked with a `.tex` file path, follow these steps:

### Step 1: Structural Extraction

Run the Python extraction script:

```bash
python3 SKILL_DIR/scripts/extract_structure.py "$ARGUMENTS" -o "${BASE}_raw.json"
```

Where `SKILL_DIR` is the directory containing this SKILL.md and `BASE` is the input filename without extension.

The script auto-discovers:
- **`.bbl` files** — extracts external theorem/lemma/proposition references from `\cite[detail]{key}` patterns. These appear as external objects with `source: "external"` and `cites_result` dependency edges.
- **`.aux` files** — if the `.tex` file has been compiled with LaTeX, parses `\newlabel` entries to assign accurate theorem numbers and PDF page numbers to labeled objects. To get `.aux` files, run `pdflatex` (or similar) on the `.tex` file before extraction.

### Step 2: Semantic Enrichment

Read the raw JSON output and enrich it:

1. **Review extracted objects** — verify types are correct, fix any misidentified objects
2. **Name every object** — for each non-proof object, set `title` to a concise descriptive name summarizing its mathematical content. Examples:
   - Theorem: "Freeness of U(p̄) as right U(p̄)^N-module"
   - Lemma: "Vanishing of n-cohomology for Whittaker modules"
   - Definition: "Admissible nilpotent elements"
   - Corollary: "Finite generation of U(p̄)^N"
   - Names should capture the mathematical essence, not just repeat the statement. Use standard notation (↪, ≅, ⊗, etc.) when helpful.
3. **OCR correction** (for OCR'd documents) — compare each object's `content_latex` against the PDF original (view the PDF page via `pdf_page`). Fix obvious OCR errors:
   - Garbled math symbols (e.g., `of` → `𝔤`, `0` → `𝔬`)
   - Corrupted headings (e.g., `COROIOIL` → `Corollary`)
   - Missing or wrong LaTeX commands
   - Write corrected text to `content_latex_corrected`; keep `content_latex` as the untouched OCR original
4. **Associate proofs** — for any proof where `proves` is null, determine which theorem/lemma it proves by reading its content and context
5. **Add implicit dependencies** — scan object content for references like "by Theorem X.Y" or "using Definition Z" that weren't captured by the extractor
6. **Verify notation table** — review the auto-extracted `notation_table`:
   - Add any missing symbols/notations that the regex patterns didn't capture
   - Fix descriptions that are incomplete or garbled by OCR
   - Remove false positives (non-definitional pattern matches)
   - Ensure each key notation used in the document has an entry
7. **Add content_plain** — write a concise plain-text summary for each important object (theorems, key definitions, main lemmas)
8. **Remove noise** — delete objects that are not genuine mathematical content (e.g., "Q.E.D." parsed as a section)
9. **Verify pdf_page** — check that auto-estimated `pdf_page` values are reasonable; correct any that are clearly wrong (OCR TOC errors can cause bad estimates)
10. **Verify external references** — review auto-extracted external objects (`source: "external"`). Name them with descriptive titles if possible (e.g., from the referenced paper's content). Remove any false positives

Write the enriched result to `${BASE}_enriched.json`.

Refer to `SKILL_DIR/references/json_schema.md` for the data model.

### Step 3: Build Dependency Graph

Run the graph builder:

```bash
python3 SKILL_DIR/scripts/build_graph.py "${BASE}_enriched.json" -o "${BASE}_final.json"
```

This validates the DAG, detects cycles, computes topological ordering, and generates the DOT graph representation.

### Step 4: Generate Visualization

Run the visualization generator:

```bash
python3 SKILL_DIR/scripts/generate_viz.py "${BASE}_final.json" -o "${BASE}_blueprint.html" --open
```

This produces a Blueprint-style interactive HTML page with:
- Sidebar listing all mathematical objects grouped by section
- Interactive dependency graph rendered via d3-graphviz
- Detail panel showing full content with KaTeX-rendered mathematics
- PDF preview panel — clicking a node shows the corresponding PDF page (requires the PDF file in the same directory as the HTML output)
- Search and filter capabilities

### Step 5: Summary

Present to the user:
- Number of objects extracted by type (definitions, theorems, lemmas, etc.)
- Key dependency chains identified
- Any issues found (cycles, unresolved references, orphaned proofs)
- Path to the generated HTML file

## Notes

- The extractor handles both standard LaTeX environments (`\begin{theorem}...\end{theorem}`) and inline patterns from OCR'd documents (`Theorem 1.2. ...`)
- For large documents, focus enrichment on the most important objects first
- The dependency graph excludes proof nodes by default (toggle available in the HTML)
- All scripts use Python standard library only — no pip install required
- If a companion PDF exists (same name as .tex), it will be auto-discovered and linked. Place the PDF alongside the generated HTML for the PDF viewer to work
- PDF page numbers are estimated from the LaTeX table of contents; enrichment can refine these
