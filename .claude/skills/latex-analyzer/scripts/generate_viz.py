#!/usr/bin/env python3
"""
generate_viz.py — Generate HTML visualization from analysis JSON.

Reads the final JSON (with dot_graph) and injects it into the HTML template.

Usage:
    python generate_viz.py input.json [-o output.html] [--template path/to/template.html]
"""

import argparse
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Generate HTML visualization from LaTeX analysis JSON"
    )
    parser.add_argument("input", help="Path to final JSON file (with dot_graph)")
    parser.add_argument("-o", "--output", help="Output HTML file")
    parser.add_argument("--template", help="Path to HTML template (default: assets/viz_template.html)")
    parser.add_argument("--open", action="store_true", help="Open in browser after generating")
    args = parser.parse_args()

    # Find template
    if args.template:
        template_path = args.template
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(script_dir, '..', 'assets', 'viz_template.html')

    if not os.path.exists(template_path):
        print(f"Error: template not found at {template_path}", file=sys.stderr)
        sys.exit(1)

    # Read template
    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()

    # Read data
    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Get title for page
    title = data.get("metadata", {}).get("title", data.get("metadata", {}).get("source_file", "Analysis"))

    # Inject data
    data_json = json.dumps(data, ensure_ascii=False)
    html = template.replace('/*DATA_PLACEHOLDER*/null', data_json)
    html = html.replace('{{TITLE}}', title.replace('"', '&quot;'))

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        base = os.path.splitext(os.path.basename(args.input))[0]
        output_path = base + '.html'

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Generated visualization: {output_path}", file=sys.stderr)
    print(f"  Objects: {len(data.get('objects', []))}", file=sys.stderr)
    print(f"  Dependencies: {len(data.get('dependencies', []))}", file=sys.stderr)

    # Open in browser
    if args.open:
        import webbrowser
        webbrowser.open('file://' + os.path.abspath(output_path))


if __name__ == "__main__":
    main()
