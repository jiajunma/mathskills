# LaTeX Analysis JSON Schema

## Top-level structure

```json
{
  "metadata": { ... },
  "objects": [ ... ],
  "dependencies": [ ... ],
  "sections": [ ... ],
  "notation_table": [ ... ],
  "dot_graph": "digraph G { ... }"
}
```

## metadata

| Field | Type | Description |
|-------|------|-------------|
| source_file | string | Input filename |
| title | string | Document title from \title{} |
| authors | string[] | Authors from \author{} |
| date | string | Date if available |
| analyzed_at | string (ISO 8601) | Analysis timestamp |
| pdf_file | string\|null | Companion PDF filename (auto-discovered from same directory as .tex) |

## objects[]

Each object represents a definition, theorem, lemma, proof, etc.

| Field | Type | Description |
|-------|------|-------------|
| id | string | Unique ID, from \label or auto-generated as `type:number`. External refs use `ext:cite_key:type:number` |
| type | string | One of: definition, theorem, lemma, proposition, corollary, remark, proof, example, axiom, conjecture, notation, assumption, claim |
| number | string\|null | Display number, e.g. "3.2". Auto-populated from `.aux` file if available (from LaTeX compilation) |
| title | string\|null | Descriptive name summarizing the mathematical content (required for all non-proof objects after enrichment). E.g. "Freeness of U(p̄) as right U(p̄)^N-module" |
| source | string | `"internal"` for objects defined in the document, `"external"` for results referenced via `\cite[detail]{key}` |
| label | string\|null | \label value if present |
| cite_key | string\|null | Bibliography key for external objects (e.g. `"meyer_resolutions_2010"`). Null for internal objects |
| cite_detail | string\|null | Full cite detail string for external objects (e.g. `"Thm 3.1"`). Null for internal objects |
| content_latex | string | Raw LaTeX content (original OCR text, never modified). Empty string for external objects |
| content_latex_corrected | string\|null | OCR-corrected LaTeX content (added by Claude during enrichment when OCR errors are found) |
| content_plain | string\|null | Plain-text summary (added by Claude during enrichment) |
| section | string\|null | Section title this object belongs to |
| source_line | integer | Line number in source file |
| explicit_refs | string[] | Labels from \ref{}, \eqref{} |
| citations | string[] | Keys from \cite{} |
| proves | string\|null | ID of statement this proof proves (proof type only) |
| proved_by | string\|null | ID of proof that proves this statement |
| pdf_page | integer\|null | PDF page number. Auto-populated from `.aux` file if available, otherwise estimated from TOC mapping. Can be corrected during enrichment |

## dependencies[]

Each edge in the dependency graph.

| Field | Type | Description |
|-------|------|-------------|
| from | string | ID of dependent object |
| to | string | ID of dependency |
| relation | string | One of: references, uses, proves, implicit, cites, uses_definition, cites_result |
| evidence | string | How dependency was determined |

## notation_table[]

Each entry represents a mathematical symbol or notation defined in the document.

| Field | Type | Description |
|-------|------|-------------|
| symbol | string | The LaTeX symbol, e.g. `$\mathfrak{g}$` |
| description | string | What the symbol denotes |
| defined_in | string | ID of the object where this symbol is defined |
| source_line | integer | Line number where the definition appears |

Notation table entries are auto-extracted by `extract_structure.py` from definition and notation objects, then refined during enrichment. They power the `uses_definition` dependency edges: if object A's content contains a symbol defined in object B, a `uses_definition` edge is added from A to B.

## sections[]

| Field | Type | Description |
|-------|------|-------------|
| id | string | Section ID |
| level | integer | 1=section, 2=subsection, 3=subsubsection |
| title | string | Section title |
| source_line | integer | Line number |
| object_ids | string[] | IDs of objects in this section |

## Enrichment guidelines for Claude

During semantic enrichment, Claude should:

1. **Name every non-proof object**: Set `title` to a concise descriptive name capturing the mathematical essence. Use standard notation (↪, ≅, ⊗, →) when helpful. This is critical for the visualization.
2. **OCR correction**: For OCR'd documents, compare `content_latex` against the PDF original (using `pdf_page`). Fix obvious OCR errors (e.g., `of` → `𝔤`, garbled headings) and write the corrected text to `content_latex_corrected`. Preserve `content_latex` unchanged as the original OCR output.
3. **Add content_plain**: Write a concise plain-text summary of each object
4. **Fix proof associations**: If `proves` is null for a proof, determine which statement it proves from context
5. **Add implicit dependencies**: If an object uses a concept defined elsewhere without \ref, add a dependency with relation "implicit"
6. **Verify and enrich notation table**: Review the auto-extracted `notation_table` entries. Add missing symbols, fix descriptions, and remove false positives. Ensure every key notation in the document is captured.
7. **Verify object types**: Confirm that auto-detected types are correct
8. **Merge duplicates**: If the same theorem appears twice (e.g., stated in intro and later formally), keep the formal version
9. **Verify pdf_page**: If `pdf_page` values seem off (e.g., from OCR TOC errors), correct them. If `pdf_page` is null and a PDF exists, estimate the page from context
