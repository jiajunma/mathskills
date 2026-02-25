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


def extract_bracket_refs(text):
    """Extract bracket-style references like [9], [6], [Kostant] from text."""
    return re.findall(r'\[(\d+|[A-Z][a-z]+(?:\s+\d+)?)\]', text)


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
            })
            continue

        i += 1

    return objects


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


def build_dependencies(objects):
    """Build dependency edges from explicit refs and inline references."""
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

    # Assign sections to objects
    for obj in objects:
        obj["section"] = find_section_for_line(sections, obj["source_line"])

    # Associate proofs with their statements
    associate_proofs(objects)

    # Build dependencies
    dependencies = build_dependencies(objects)

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
    }

    output = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"Wrote {len(objects)} objects and {len(dependencies)} dependencies to {args.output}",
              file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
