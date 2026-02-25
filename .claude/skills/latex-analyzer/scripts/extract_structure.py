#!/usr/bin/env python3
"""
extract_structure.py — Extract mathematical structure from LaTeX files.

Supports two modes:
1. Standard LaTeX environments (\begin{theorem}...\end{theorem})
2. Inline text patterns (e.g., "Theorem 1.2." from OCR'd documents)

Usage:
    python extract_structure.py input.tex [-o output.json]
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone


# Canonical math object types
CANONICAL_TYPES = {
    "definition", "theorem", "lemma", "proposition", "corollary",
    "remark", "proof", "example", "axiom", "conjecture",
    "notation", "assumption", "claim",
}

# Default newtheorem aliases (common LaTeX packages)
DEFAULT_ALIASES = {
    "thm": "theorem", "theo": "theorem", "thmx": "theorem",
    "lem": "lemma", "lema": "lemma",
    "prop": "proposition",
    "cor": "corollary", "coro": "corollary",
    "defn": "definition", "defin": "definition", "dfn": "definition",
    "rem": "remark", "rmk": "remark",
    "ex": "example", "exam": "example", "exmp": "example",
    "conj": "conjecture",
    "nota": "notation",
    "assump": "assumption", "assum": "assumption",
}

# Patterns for inline math objects (OCR'd documents)
# Matches: "Theorem 1.2", "Proposition 1.4.1.", "Lemma 2.3 [Kostant]"
# Also matches mid-line: "...follows. Theorem 1.2 [Kostant] The map"
INLINE_HEADER_RE = re.compile(
    r'(?:^|(?<=\.\s)|(?<=\.\s\s))'           # start of line or after sentence end
    r'(?:(?:\\textbf\{)|(?:\\textit\{))?'     # optional formatting
    r'(Theorem|Lemma|Proposition|Corollary|Definition|Remark|Example|'
    r'Conjecture|Axiom|Claim|Notation|Assumption)'
    r'(?:\})?\s+'                             # close optional formatting
    r'([\d]+(?:\.[\d]+)*(?:\.\d+)*)'          # number like 1.2, 1.4.1
    r'\.?'                                    # optional trailing dot
    r'(?:\s*\[([^\]]*)\])?'                   # optional attribution [Kostant]
    r'\.?\s*',                                # optional dot + space
    re.IGNORECASE
)

# Proof pattern: "Proof." or "Proof of Theorem X.Y"
PROOF_HEADER_RE = re.compile(
    r'^(?:(?:\\textbf\{)|(?:\\textit\{))?'
    r'Proof'
    r'(?:\})?'
    r'(?:\s+of\s+(Theorem|Lemma|Proposition|Corollary)\s+'
    r'([\d]+(?:\.[\d]+)*))?'
    r'\.?\s*',
    re.IGNORECASE
)


def parse_newtheorem(lines):
    """Extract \\newtheorem declarations to build environment alias map."""
    aliases = dict(DEFAULT_ALIASES)
    # \newtheorem{envname}{Display Name}
    # \newtheorem{envname}[counter]{Display Name}
    # \newtheorem*{envname}{Display Name}
    pattern = re.compile(
        r'\\newtheorem\*?\{(\w+)\}'
        r'(?:\[(\w+)\])?'
        r'\{([^}]+)\}'
    )
    for line in lines:
        for m in pattern.finditer(line):
            env_name = m.group(1).lower()
            display_name = m.group(3).strip().lower()
            # Map to canonical type
            canonical = None
            for ct in CANONICAL_TYPES:
                if ct in display_name or display_name in ct:
                    canonical = ct
                    break
            if canonical:
                aliases[env_name] = canonical
            else:
                # Use display name as-is if close to a canonical type
                aliases[env_name] = display_name
    return aliases


def resolve_canonical_type(env_name, aliases):
    """Resolve an environment name to a canonical type."""
    name = env_name.lower().rstrip('*')
    if name in CANONICAL_TYPES:
        return name
    if name in aliases:
        return aliases[name]
    # Fuzzy match
    for ct in CANONICAL_TYPES:
        if ct.startswith(name) or name.startswith(ct):
            return ct
    return name


def extract_labels(text):
    """Extract \\label{...} from text."""
    return re.findall(r'\\label\{([^}]+)\}', text)


def extract_refs(text):
    """Extract \\ref{...} and \\eqref{...} from text."""
    return re.findall(r'\\(?:eq)?ref\{([^}]+)\}', text)


def extract_citations(text):
    """Extract \\cite{...} keys from text."""
    cites = []
    for m in re.finditer(r'\\cite(?:\[[^\]]*\])?\{([^}]+)\}', text):
        keys = [k.strip() for k in m.group(1).split(',')]
        cites.extend(keys)
    return cites


# --- External reference extraction ---

# Pattern matching \cite[detail]{key} where detail contains a result type
CITE_DETAIL_RE = re.compile(
    r'\\cite\[([^\]]+)\]\{([^}]+)\}'
)

# Result type keywords to match in cite details
RESULT_TYPE_MAP = {
    'thm':         'theorem',
    'theorem':     'theorem',
    'lem':         'lemma',
    'lemma':       'lemma',
    'prop':        'proposition',
    'proposition': 'proposition',
    'cor':         'corollary',
    'corollary':   'corollary',
    'def':         'definition',
    'definition':  'definition',
}

# Regex to extract result type and number from cite detail
# Matches: "Thm 3.1", "Lem. 2.15", "Prop. 2.4.1 (b)", "Cor (2.1.11)", "Def 2.1"
# Also matches parenthesized numbers: "(2.2.4)"
RESULT_DETAIL_RE = re.compile(
    r'(Thm|Theorem|Lem|Lemma|Prop|Proposition|Cor|Corollary|Def|Definition)'
    r'\.?\s*'
    r'(\(?\d+(?:\.\d+)*\)?'            # number like 3.1, 2.4.1, (2.2.4)
    r'(?:\s*\([a-z]\))?)',              # optional sub-part like (b)
    re.IGNORECASE
)

# Section-level references to skip (not concrete results)
SECTION_RE = re.compile(
    r'Section|§|Sect\.',
    re.IGNORECASE
)


def parse_bbl(bbl_path):
    """Parse a .bbl file to extract bibliography metadata.

    Returns dict: {cite_key: {short_label, title, authors}}
    """
    bbl_info = {}
    if not bbl_path or not os.path.exists(bbl_path):
        return bbl_info

    with open(bbl_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    # Match \bibitem[label]{key} followed by author/title text
    bibitem_re = re.compile(
        r'\\bibitem\[([^\]]*)\]\{([^}]+)\}\s*\n(.*?)(?=\\bibitem|\n\\end\{thebibliography\})',
        re.DOTALL
    )

    for m in bibitem_re.finditer(content):
        short_label = m.group(1).strip()
        key = m.group(2).strip()
        body = m.group(3).strip()

        # Extract title from \textsl{...} or \textit{...}
        title_m = re.search(r'\\text(?:sl|it)\{([^}]+)\}', body)
        title = title_m.group(1).strip() if title_m else ''
        # Clean up LaTeX commands in title
        title = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', title)
        title = re.sub(r'[{}]', '', title)
        title = re.sub(r'\s+', ' ', title).strip()

        # Extract authors (text before first \textsl/\textit)
        author_part = re.split(r'\\text(?:sl|it)', body)[0]
        authors = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', author_part)
        authors = re.sub(r'[{}\n]', ' ', authors)
        authors = re.sub(r',\s*$', '', authors.strip())
        authors = re.sub(r'\s+', ' ', authors).strip()

        bbl_info[key] = {
            'short_label': short_label,
            'title': title,
            'authors': authors,
        }

    return bbl_info


def extract_external_refs(lines, bbl_info):
    """Extract external theorem/lemma/etc references from \\cite[detail]{key} patterns.

    Returns list of external object dicts, deduplicated by (key, type, number).
    """
    full_text = "\n".join(lines)
    seen = {}  # (key, canonical_type, number) -> object

    for m in CITE_DETAIL_RE.finditer(full_text):
        detail = m.group(1)
        cite_key = m.group(2).strip()

        # Skip section-level references
        if SECTION_RE.search(detail):
            # But only skip if there's no result type also present
            if not RESULT_DETAIL_RE.search(detail):
                continue

        # Try to extract result type and number
        rm = RESULT_DETAIL_RE.search(detail)
        if not rm:
            continue

        type_word = rm.group(1).lower().rstrip('.')
        canonical_type = RESULT_TYPE_MAP.get(type_word)
        if not canonical_type:
            continue

        number = rm.group(2).strip()
        # Normalize number for dedup: strip wrapping parens, collapse sub-parts
        # "(2.1.11)" -> "2.1.11", "2.4.1 (b)" -> "2.4.1(b)"
        clean_number = re.sub(r'^\((.+)\)$', r'\1', number)  # unwrap full parens
        clean_number = re.sub(r'\s+', '', clean_number)       # remove spaces

        dedup_key = (cite_key, canonical_type, clean_number)
        if dedup_key in seen:
            continue

        # Build title
        # Abbreviate type for display
        type_abbrev = {
            'theorem': 'Thm', 'lemma': 'Lem', 'proposition': 'Prop',
            'corollary': 'Cor', 'definition': 'Def',
        }
        display_detail = f"{type_abbrev.get(canonical_type, canonical_type.capitalize())}. {number}"

        title = f"[{cite_key}] {display_detail}"
        if cite_key in bbl_info:
            info = bbl_info[cite_key]
            # Add authors for richer context
            if info['authors']:
                title = f"[{info['short_label']}] {display_detail}"

        ext_id = f"ext:{cite_key}:{canonical_type}:{clean_number}"

        ext_obj = {
            "id": ext_id,
            "type": canonical_type,
            "number": clean_number,
            "title": title,
            "label": None,
            "source": "external",
            "cite_key": cite_key,
            "cite_detail": detail.strip(),
            "content_latex": "",
            "section": None,
            "source_line": 0,
            "explicit_refs": [],
            "citations": [],
            "proves": None,
            "proved_by": None,
            "pdf_page": None,
        }

        seen[dedup_key] = ext_obj

    return list(seen.values())


def extract_bracket_refs(text):
    """Extract bracket-style references like [9], [6], [Kostant] from text."""
    return re.findall(r'\[(\d+|[A-Z][a-z]+(?:\s+\d+)?)\]', text)


def extract_toc_page_map(lines):
    """Extract section→page mapping from a LaTeX table of contents.

    Parses the \\section{Contents} block to find patterns like:
      1.2 Admissible nilpotents ..... 19
    Returns {section_number: page_number} dict.
    """
    toc_map = {}
    in_toc = False

    for i, line in enumerate(lines):
        # Detect start of TOC section
        if re.match(r'\\section\{Contents\}', line, re.IGNORECASE):
            in_toc = True
            continue
        # Stop at next \section (not Contents)
        if in_toc and re.match(r'\\section\{', line) and not re.match(r'\\section\{Contents\}', line, re.IGNORECASE):
            break
        if not in_toc:
            continue

        # Match patterns like "1.2 Some title ..... 19" or "1.2 Some title 19"
        m = re.match(
            r'\s*([\d]+(?:\.[\d]+)*)\s+'   # section number
            r'(.+?)\s*'                     # title
            r'\.{2,}\s*'                    # dots
            r'(\d+)\s*$',                   # page number
            line
        )
        if m:
            toc_map[m.group(1)] = int(m.group(3))
            continue

        # Also match without dots: "1.2 Some title 19"
        m = re.match(
            r'\s*([\d]+(?:\.[\d]+)*)\s+'
            r'(.+?)\s+'
            r'(\d+)\s*$',
            line
        )
        if m:
            # Heuristic: only accept if page number is reasonable (< 1000)
            page = int(m.group(3))
            if page < 1000:
                toc_map[m.group(1)] = page

    return toc_map


def estimate_pdf_pages(objects, sections, toc_map, total_lines):
    """Estimate PDF page number for each object based on TOC mapping.

    Uses section→page mapping from the TOC, then interpolates within
    each section based on relative line position.
    """
    if not toc_map:
        return

    # Build section_number → (start_line, page) mapping from sections + TOC
    sec_page_info = []  # [(start_line, page, next_start_line, next_page)]
    for sec in sections:
        title = sec["title"]
        # Try to extract section number from title (e.g., "1.2 Admissible nilpotents")
        m = re.match(r'([\d]+(?:\.[\d]+)*)\s', title)
        if not m:
            continue
        sec_num = m.group(1)
        if sec_num in toc_map:
            sec_page_info.append({
                "start_line": sec["source_line"],
                "page": toc_map[sec_num],
                "sec_num": sec_num,
            })

    if not sec_page_info:
        # Fallback: try matching section titles directly
        for sec in sections:
            for sec_num, page in toc_map.items():
                if sec_num in sec["title"]:
                    sec_page_info.append({
                        "start_line": sec["source_line"],
                        "page": page,
                        "sec_num": sec_num,
                    })
                    break

    if not sec_page_info:
        return

    # Sort by start_line
    sec_page_info.sort(key=lambda x: x["start_line"])

    for obj in objects:
        line = obj["source_line"]
        # Find the section this line falls in
        best = None
        next_info = None
        for idx, info in enumerate(sec_page_info):
            if info["start_line"] <= line:
                best = info
                next_info = sec_page_info[idx + 1] if idx + 1 < len(sec_page_info) else None
            else:
                if best is None:
                    # Before first known section, use first section's page
                    best = info
                break

        if best:
            if next_info and next_info["start_line"] > best["start_line"]:
                # Interpolate between sections
                line_frac = (line - best["start_line"]) / (next_info["start_line"] - best["start_line"])
                page_range = next_info["page"] - best["page"]
                obj["pdf_page"] = best["page"] + int(line_frac * page_range)
            else:
                obj["pdf_page"] = best["page"]


def parse_sections(lines):
    """Extract section hierarchy from LaTeX."""
    sections = []
    section_re = re.compile(
        r'\\(section|subsection|subsubsection)\*?\{(.+?)\}\s*$'
    )
    level_map = {"section": 1, "subsection": 2, "subsubsection": 3}
    for i, line in enumerate(lines):
        m = section_re.search(line)
        if m:
            cmd = m.group(1)
            title = m.group(2).strip()
            sections.append({
                "id": f"sec:{len(sections)+1}",
                "level": level_map[cmd],
                "title": title,
                "source_line": i + 1,
                "object_ids": [],
            })
    return sections


def find_section_for_line(sections, line_num):
    """Find which section a given line belongs to."""
    current = None
    for sec in sections:
        if sec["source_line"] <= line_num:
            current = sec["title"]
        else:
            break
    return current


def extract_metadata(lines):
    """Extract document metadata (title, author, date)."""
    metadata = {"source_file": "", "analyzed_at": ""}
    full = "\n".join(lines)

    # Title
    m = re.search(r'\\title\{(.+?)\}', full, re.DOTALL)
    if m:
        metadata["title"] = re.sub(r'\s+', ' ', m.group(1).strip())

    # Author
    m = re.search(r'\\author\{(.+?)\}', full, re.DOTALL)
    if m:
        author_text = m.group(1).strip()
        if author_text != "Q.E.D.":  # skip OCR artifacts
            metadata["authors"] = [a.strip() for a in author_text.split('\\and')]

    # Date
    m = re.search(r'\\date\{(.+?)\}', full)
    if m:
        metadata["date"] = m.group(1).strip()

    return metadata


def extract_env_objects(lines, aliases):
    """Extract objects from standard LaTeX environments."""
    objects = []
    stack = []  # (env_name, canonical_type, title, start_line, content_lines)

    begin_re = re.compile(r'\\begin\{(\w+\*?)\}(?:\[([^\]]*)\])?')
    end_re = re.compile(r'\\end\{(\w+\*?)\}')

    math_envs = set(CANONICAL_TYPES) | set(aliases.keys())

    for i, line in enumerate(lines):
        # Check for \begin
        for m in begin_re.finditer(line):
            env_name = m.group(1).rstrip('*')
            if env_name.lower() in math_envs:
                title = m.group(2) if m.group(2) else None
                canonical = resolve_canonical_type(env_name, aliases)
                stack.append((env_name, canonical, title, i + 1, []))

        # Collect content for active environments
        if stack:
            stack[-1][4].append(line)

        # Check for \end
        for m in end_re.finditer(line):
            end_name = m.group(1).rstrip('*')
            if stack and stack[-1][0].rstrip('*') == end_name.rstrip('*'):
                env_name, canonical, title, start_line, content_lines = stack.pop()
                content = "\n".join(content_lines)
                labels = extract_labels(content)
                refs = extract_refs(content)
                cites = extract_citations(content)

                obj_id = labels[0] if labels else f"{canonical}:{start_line}"
                objects.append({
                    "id": obj_id,
                    "type": canonical,
                    "number": None,
                    "title": title,
                    "label": labels[0] if labels else None,
                    "content_latex": content.strip(),
                    "section": None,  # filled later
                    "source_line": start_line,
                    "explicit_refs": refs,
                    "citations": cites,
                    "proves": None,
                    "proved_by": None,
                    "pdf_page": None,
                })
    return objects


def extract_inline_objects(lines, aliases):
    """Extract math objects from inline text patterns (OCR'd documents)."""
    objects = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].strip()

        # Check for proof header
        pm = PROOF_HEADER_RE.match(line)
        if pm:
            start_line = i + 1
            proves_type = pm.group(1)
            proves_num = pm.group(2)
            content_lines = [lines[i]]
            i += 1

            # Collect until Q.E.D. or next header or section
            while i < n:
                l = lines[i].strip()
                if 'Q.E.D.' in l or '\\qed' in l.lower():
                    content_lines.append(lines[i])
                    i += 1
                    break
                if INLINE_HEADER_RE.match(l):
                    break
                if PROOF_HEADER_RE.match(l) and i > start_line:
                    break
                if re.match(r'\\section', l):
                    break
                content_lines.append(lines[i])
                i += 1

            content = "\n".join(content_lines)
            proves_ref = None
            if proves_type and proves_num:
                proves_ref = f"{proves_type.lower()}:{proves_num}"

            obj_id = f"proof:{start_line}"
            if proves_ref:
                obj_id = f"proof:{proves_ref}"

            objects.append({
                "id": obj_id,
                "type": "proof",
                "number": None,
                "title": f"Proof of {proves_type} {proves_num}" if proves_type else "Proof",
                "label": None,
                "content_latex": content.strip(),
                "section": None,
                "source_line": start_line,
                "explicit_refs": extract_refs(content),
                "citations": extract_citations(content),
                "bracket_refs": extract_bracket_refs(content),
                "proves": proves_ref,
                "proved_by": None,
                "pdf_page": None,
            })
            continue

        # Check for theorem-like header
        m = INLINE_HEADER_RE.match(line)
        if m:
            obj_type = m.group(1).lower()
            obj_num = m.group(2)
            attribution = m.group(3)
            start_line = i + 1
            content_lines = [lines[i]]
            i += 1

            # Collect content until next header, proof, or section
            while i < n:
                l = lines[i].strip()
                if INLINE_HEADER_RE.match(l):
                    break
                if PROOF_HEADER_RE.match(l):
                    break
                if re.match(r'\\section', l):
                    break
                # Stop at empty line followed by a new header
                if l == '' and i + 1 < n:
                    next_l = lines[i + 1].strip()
                    if (INLINE_HEADER_RE.match(next_l) or
                        PROOF_HEADER_RE.match(next_l) or
                        re.match(r'\\section', next_l)):
                        i += 1
                        break
                content_lines.append(lines[i])
                i += 1

            content = "\n".join(content_lines)
            canonical = resolve_canonical_type(obj_type, aliases)
            obj_id = f"{canonical}:{obj_num}"
            title_str = attribution if attribution else None

            objects.append({
                "id": obj_id,
                "type": canonical,
                "number": obj_num,
                "title": title_str,
                "label": None,
                "content_latex": content.strip(),
                "section": None,
                "source_line": start_line,
                "explicit_refs": extract_refs(content),
                "citations": extract_citations(content),
                "bracket_refs": extract_bracket_refs(content),
                "proves": None,
                "proved_by": None,
                "pdf_page": None,
            })
            continue

        i += 1

    return objects


def parse_aux(aux_path):
    """Parse a LaTeX .aux file to extract label → number and page mappings.

    Parses \\newlabel{label}{{number}{page}...} entries.
    Returns dict: {label: {"number": str, "page": int}}.
    """
    label_map = {}
    if not aux_path or not os.path.exists(aux_path):
        return label_map

    with open(aux_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    # Match \newlabel{label}{{number}{page}...}
    # The number can contain LaTeX like {$\ast $} for starred theorems
    newlabel_re = re.compile(
        r'\\newlabel\{([^}]+)\}\{\{([^}]*)\}\{(\d+)\}'
    )

    for m in newlabel_re.finditer(content):
        label = m.group(1)
        number = m.group(2).strip()
        page = int(m.group(3))
        # Skip toc-related labels
        if label.startswith('tocindent'):
            continue
        label_map[label] = {"number": number, "page": page}

    return label_map


def resolve_includes(filepath, lines):
    """Resolve \\input{} and \\include{} directives."""
    resolved = []
    base_dir = os.path.dirname(os.path.abspath(filepath))
    input_re = re.compile(r'\\(?:input|include)\{([^}]+)\}')

    for line in lines:
        m = input_re.search(line)
        if m:
            inc_path = m.group(1)
            if not inc_path.endswith('.tex'):
                inc_path += '.tex'
            full_path = os.path.join(base_dir, inc_path)
            if os.path.exists(full_path):
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    inc_lines = f.readlines()
                resolved.extend([l.rstrip('\n') for l in inc_lines])
            else:
                resolved.append(line)
        else:
            resolved.append(line)
    return resolved


def extract_notation_table(objects):
    """Extract a notation/symbol table from definition and notation objects.

    Scans content_latex for symbol definition patterns like:
    - Let $X$ denote/be ...
    - We define $X$ ...
    - We set $X = ...$
    - We write $X$ for ...
    - $X$ denotes ...

    Returns a list of notation entries.
    """
    notation_table = []

    # Patterns to extract symbol definitions
    patterns = [
        # "Let $X$ denote/be ..."
        re.compile(
            r'[Ll]et\s+(\$[^$]+\$)\s+(?:denote|be|denotes)\s+(.+?)(?:\.|$)',
            re.DOTALL
        ),
        # "We define $X$ ..." / "we define $X$ to be ..."
        re.compile(
            r'[Ww]e\s+define\s+(\$[^$]+\$)\s+(.+?)(?:\.|$)',
            re.DOTALL
        ),
        # "We set $X = ...$" / "we set $X$ = ..."
        re.compile(
            r'[Ww]e\s+set\s+(\$[^$]+\$)\s*(.+?)(?:\.|$)',
            re.DOTALL
        ),
        # "We write $X$ for ..."
        re.compile(
            r'[Ww]e\s+write\s+(\$[^$]+\$)\s+(?:for|to\s+denote)\s+(.+?)(?:\.|$)',
            re.DOTALL
        ),
        # "$X$ denotes ..."
        re.compile(
            r'(\$[^$]+\$)\s+denotes?\s+(.+?)(?:\.|$)',
            re.DOTALL
        ),
        # "denote by $X$ ..."
        re.compile(
            r'denote\s+by\s+(\$[^$]+\$)\s+(.+?)(?:\.|$)',
            re.DOTALL
        ),
        # "$X := ...$" or "$X = ...$" in definitions
        re.compile(
            r'(\$[^$]*?[A-Za-z_\\]+[^$]*?\s*:?=\s*[^$]+\$)',
            re.DOTALL
        ),
    ]

    # Prefer definition/notation objects, but if none exist, scan all non-proof objects
    def_objects = [o for o in objects if o["type"] in ("definition", "notation")]
    if not def_objects:
        def_objects = [o for o in objects if o["type"] != "proof"]

    for obj in def_objects:
        content = obj.get("content_latex", "")
        if not content:
            continue

        seen_symbols = set()
        for pat in patterns:
            for m in pat.finditer(content):
                symbol = m.group(1).strip()
                # Clean up symbol - limit to reasonable length
                if len(symbol) > 100:
                    continue
                if symbol in seen_symbols:
                    continue
                seen_symbols.add(symbol)

                description = m.group(2).strip() if m.lastindex >= 2 else ""
                # Truncate long descriptions
                if len(description) > 200:
                    description = description[:200] + "..."

                notation_table.append({
                    "symbol": symbol,
                    "description": description,
                    "defined_in": obj["id"],
                    "source_line": obj["source_line"],
                })

    return notation_table


def associate_proofs(objects):
    """Associate proof objects with their theorem/lemma/proposition."""
    # Index non-proof objects by id
    stmt_index = {}
    for obj in objects:
        if obj["type"] != "proof":
            stmt_index[obj["id"]] = obj
            # Also index by number pattern
            if obj["number"]:
                key = f"{obj['type']}:{obj['number']}"
                stmt_index[key] = obj

    for obj in objects:
        if obj["type"] != "proof":
            continue

        # Case 1: explicit proves reference
        if obj.get("proves") and obj["proves"] in stmt_index:
            target = stmt_index[obj["proves"]]
            obj["proves"] = target["id"]
            target["proved_by"] = obj["id"]
            continue

        # Case 2: proof immediately follows a statement (by source line proximity)
        best = None
        best_dist = float('inf')
        for other in objects:
            if other["type"] == "proof":
                continue
            if other["type"] in ("remark", "example", "notation"):
                continue
            dist = obj["source_line"] - other["source_line"]
            if 0 < dist < best_dist:
                best_dist = dist
                best = other

        if best and best_dist <= 20:  # within 20 lines (OCR'd docs have gaps)
            obj["proves"] = best["id"]
            best["proved_by"] = obj["id"]


def build_dependencies(objects, notation_table=None):
    """Build dependency edges from explicit refs, inline references, and symbol usage."""
    deps = []
    obj_index = {}
    for obj in objects:
        obj_index[obj["id"]] = obj
        if obj.get("number"):
            # Multiple keys for matching
            obj_index[f"{obj['type']}:{obj['number']}"] = obj

    for obj in objects:
        # From explicit \ref
        for ref in obj.get("explicit_refs", []):
            if ref in obj_index and ref != obj["id"]:
                deps.append({
                    "from": obj["id"],
                    "to": ref,
                    "relation": "references",
                    "evidence": f"\\ref{{{ref}}}",
                })

        # From proves relationship
        if obj.get("proves") and obj["proves"] in obj_index:
            deps.append({
                "from": obj["id"],
                "to": obj["proves"],
                "relation": "proves",
                "evidence": "proof association",
            })

        # Scan content for inline references like "Theorem 1.2" or "by Lemma 2.3"
        content = obj.get("content_latex", "")
        ref_pattern = re.compile(
            r'(?:by|from|using|see|cf\.?|via)\s+'
            r'(Theorem|Lemma|Proposition|Corollary|Definition|Remark)\s+'
            r'([\d]+(?:\.[\d]+)*)',
            re.IGNORECASE
        )
        for rm in ref_pattern.finditer(content):
            ref_type = rm.group(1).lower()
            ref_num = rm.group(2)
            ref_id = f"{ref_type}:{ref_num}"
            if ref_id in obj_index and ref_id != obj["id"]:
                # Avoid duplicates
                if not any(d["from"] == obj["id"] and d["to"] == ref_id for d in deps):
                    deps.append({
                        "from": obj["id"],
                        "to": ref_id,
                        "relation": "uses",
                        "evidence": f"inline reference: {rm.group(0).strip()}",
                    })

        # Also scan for "Theorem X.Y" without context words (direct mentions)
        direct_pattern = re.compile(
            r'(Theorem|Lemma|Proposition|Corollary|Definition)\s+'
            r'([\d]+(?:\.[\d]+)*)',
            re.IGNORECASE
        )
        for rm in direct_pattern.finditer(content):
            ref_type = rm.group(1).lower()
            ref_num = rm.group(2)
            ref_id = f"{ref_type}:{ref_num}"
            if ref_id in obj_index and ref_id != obj["id"]:
                if not any(d["from"] == obj["id"] and d["to"] == ref_id for d in deps):
                    deps.append({
                        "from": obj["id"],
                        "to": ref_id,
                        "relation": "references",
                        "evidence": f"direct mention: {rm.group(0).strip()}",
                    })

    # External reference dependencies (\cite[detail]{key} -> ext:key:type:num)
    ext_index = {}  # (cite_key, canonical_type, clean_number) -> ext_obj_id
    for obj in objects:
        if obj.get("source") == "external":
            ext_index[(obj["cite_key"], obj["type"], obj["number"])] = obj["id"]

    if ext_index:
        for obj in objects:
            if obj.get("source") == "external":
                continue
            content = obj.get("content_latex", "")
            if not content:
                continue
            for cm in CITE_DETAIL_RE.finditer(content):
                detail = cm.group(1)
                cite_key = cm.group(2).strip()
                rm = RESULT_DETAIL_RE.search(detail)
                if not rm:
                    continue
                type_word = rm.group(1).lower().rstrip('.')
                canonical_type = RESULT_TYPE_MAP.get(type_word)
                if not canonical_type:
                    continue
                number = rm.group(2).strip()
                clean_num = re.sub(r'^\((.+)\)$', r'\1', number)
                clean_num = re.sub(r'\s+', '', clean_num)
                ext_id = ext_index.get((cite_key, canonical_type, clean_num))
                if ext_id and ext_id != obj["id"]:
                    if not any(d["from"] == obj["id"] and d["to"] == ext_id for d in deps):
                        deps.append({
                            "from": obj["id"],
                            "to": ext_id,
                            "relation": "cites_result",
                            "evidence": f"\\cite[{detail.strip()}]{{{cite_key}}}",
                        })

    # Symbol-level dependency detection from notation table
    if notation_table:
        # Build symbol → definition_id index
        symbol_def_map = {}
        for entry in notation_table:
            symbol = entry["symbol"]
            def_id = entry["defined_in"]
            if def_id in obj_index:
                symbol_def_map[symbol] = def_id

        for obj in objects:
            content = obj.get("content_latex", "")
            if not content:
                continue
            for symbol, def_id in symbol_def_map.items():
                # Skip self-references
                if def_id == obj["id"]:
                    continue
                # Extract the LaTeX content inside $ delimiters for matching
                symbol_inner = symbol.strip('$')
                if not symbol_inner:
                    continue
                # Check if this symbol appears in the object's content
                if symbol_inner in content:
                    # Avoid duplicate edges
                    if not any(d["from"] == obj["id"] and d["to"] == def_id
                               and d["relation"] == "uses_definition" for d in deps):
                        deps.append({
                            "from": obj["id"],
                            "to": def_id,
                            "relation": "uses_definition",
                            "evidence": f"uses symbol {symbol} defined in {def_id}",
                        })

    return deps


def main():
    parser = argparse.ArgumentParser(
        description="Extract mathematical structure from LaTeX files"
    )
    parser.add_argument("input", help="Path to .tex file")
    parser.add_argument("-o", "--output", help="Output JSON file (default: stdout)")
    args = parser.parse_args()

    # Read file
    with open(args.input, 'r', encoding='utf-8', errors='replace') as f:
        raw_lines = [l.rstrip('\n') for l in f.readlines()]

    # Resolve includes
    lines = resolve_includes(args.input, raw_lines)

    # Parse newtheorem declarations
    aliases = parse_newtheorem(lines)

    # Extract metadata
    metadata = extract_metadata(lines)
    metadata["source_file"] = os.path.basename(args.input)
    metadata["analyzed_at"] = datetime.now(timezone.utc).isoformat()

    # Auto-discover companion PDF file
    input_abs = os.path.abspath(args.input)
    pdf_path = os.path.splitext(input_abs)[0] + '.pdf'
    if os.path.exists(pdf_path):
        metadata["pdf_file"] = os.path.basename(pdf_path)
    else:
        metadata["pdf_file"] = None

    # Auto-discover .bbl file
    bbl_path = os.path.splitext(input_abs)[0] + '.bbl'
    if not os.path.exists(bbl_path):
        # Try any .bbl in the same directory
        input_dir = os.path.dirname(input_abs)
        bbl_files = [f for f in os.listdir(input_dir) if f.endswith('.bbl')]
        if bbl_files:
            bbl_path = os.path.join(input_dir, bbl_files[0])
        else:
            bbl_path = None
    bbl_info = parse_bbl(bbl_path) if bbl_path else {}

    # Auto-discover .aux file (from LaTeX compilation)
    aux_path = os.path.splitext(input_abs)[0] + '.aux'
    if not os.path.exists(aux_path):
        aux_path = None
    aux_info = parse_aux(aux_path) if aux_path else {}
    if aux_info:
        print(f"Found .aux file with {len(aux_info)} labels", file=sys.stderr)

    # Extract TOC page mapping
    toc_map = extract_toc_page_map(lines)

    # Extract sections
    sections = parse_sections(lines)

    # Try environment-based extraction first
    env_objects = extract_env_objects(lines, aliases)

    # Also try inline extraction
    inline_objects = extract_inline_objects(lines, aliases)

    # Use whichever found more objects, or merge
    if len(env_objects) >= len(inline_objects):
        objects = env_objects
    else:
        objects = inline_objects

    # Assign numbers and pages from .aux file
    if aux_info:
        for obj in objects:
            label = obj.get("label")
            if label and label in aux_info:
                info = aux_info[label]
                if info["number"] and not obj.get("number"):
                    obj["number"] = info["number"]
                if info["page"] and not obj.get("pdf_page"):
                    obj["pdf_page"] = info["page"]

    # Mark all internal objects
    for obj in objects:
        obj["source"] = "internal"
        obj["cite_key"] = None
        obj["cite_detail"] = None

    # Extract external references and append
    external_objects = extract_external_refs(lines, bbl_info)
    objects.extend(external_objects)

    # Assign sections to objects
    for obj in objects:
        obj["section"] = find_section_for_line(sections, obj["source_line"])

    # Estimate PDF pages from TOC
    estimate_pdf_pages(objects, sections, toc_map, len(lines))

    # Associate proofs with their statements
    associate_proofs(objects)

    # Extract notation table from definitions/notations
    notation_table = extract_notation_table(objects)

    # Build dependencies (including symbol-level detection)
    dependencies = build_dependencies(objects, notation_table)

    # Assign section object_ids
    for sec in sections:
        sec["object_ids"] = [
            obj["id"] for obj in objects
            if obj["section"] == sec["title"]
        ]

    # Clean up bracket_refs (not part of final schema, used internally)
    for obj in objects:
        obj.pop("bracket_refs", None)

    result = {
        "metadata": metadata,
        "objects": objects,
        "dependencies": dependencies,
        "sections": sections,
        "notation_table": notation_table,
    }

    output = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        ext_count = sum(1 for o in objects if o.get("source") == "external")
        int_count = len(objects) - ext_count
        print(f"Wrote {len(objects)} objects ({int_count} internal, {ext_count} external) and {len(dependencies)} dependencies to {args.output}",
              file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
