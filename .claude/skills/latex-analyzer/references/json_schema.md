# LaTeX Analysis JSON Schema

## Top-level structure

```json
{
  "metadata": { ... },
  "objects": [ ... ],
  "dependencies": [ ... ],
  "sections": [ ... ],
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

## objects[]

Each object represents a definition, theorem, lemma, proof, etc.

| Field | Type | Description |
|-------|------|-------------|
| id | string | Unique ID, from \label or auto-generated as `type:number` |
| type | string | One of: definition, theorem, lemma, proposition, corollary, remark, proof, example, axiom, conjecture, notation, assumption, claim |
| number | string\|null | Display number, e.g. "3.2" |
| title | string\|null | Descriptive name summarizing the mathematical content (required for all non-proof objects after enrichment). E.g. "Freeness of U(p̄) as right U(p̄)^N-module" |
| label | string\|null | \label value if present |
| content_latex | string | Raw LaTeX content |
| content_plain | string\|null | Plain-text summary (added by Claude during enrichment) |
| section | string\|null | Section title this object belongs to |
| source_line | integer | Line number in source file |
| explicit_refs | string[] | Labels from \ref{}, \eqref{} |
| citations | string[] | Keys from \cite{} |
| proves | string\|null | ID of statement this proof proves (proof type only) |
| proved_by | string\|null | ID of proof that proves this statement |

## dependencies[]

Each edge in the dependency graph.

| Field | Type | Description |
|-------|------|-------------|
| from | string | ID of dependent object |
| to | string | ID of dependency |
| relation | string | One of: references, uses, proves, implicit, cites |
| evidence | string | How dependency was determined |

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
2. **Add content_plain**: Write a concise plain-text summary of each object
3. **Fix proof associations**: If `proves` is null for a proof, determine which statement it proves from context
4. **Add implicit dependencies**: If an object uses a concept defined elsewhere without \ref, add a dependency with relation "implicit"
5. **Verify object types**: Confirm that auto-detected types are correct
6. **Merge duplicates**: If the same theorem appears twice (e.g., stated in intro and later formally), keep the formal version
