"""Normalize common generated LaTeX delimiters for Streamlit Markdown."""

from __future__ import annotations

import re

_TOKENS = re.compile(
    r"(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]+`|"
    r"\$\$[\s\S]*?\$\$|(?<!\\)\$(?!\$)[^$\n]+(?<!\\)\$|"
    r"\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\))"
)
_COMMAND = re.compile(r"\\[A-Za-z]+")


def _display(expression: str) -> str:
    return "\n\n$$\n" + expression.strip() + "\n$$\n\n"


def _format_bare(text: str) -> str:
    # Only infer math for bracketed LaTeX or an entire equation line, avoiding
    # ordinary prose and Markdown links. Never rewrite textbook source records.
    text = re.sub(
        r"\(([^()\n]*\\[A-Za-z]+[^()\n]*)\)",
        lambda match: "$" + match[1].strip() + "$", text,
    )
    text = re.sub(
        r"\[([^\[\]\n]*\\[A-Za-z]+[^\[\]\n]*)\](?!\()",
        lambda match: "$" + match[1].strip() + "$", text,
    )
    lines = []
    for line in text.split("\n"):
        expression = line.strip()
        if (
            "$" not in expression
            and "=" in expression
            and _COMMAND.search(expression)
            and re.match(r"^(?:\\[A-Za-z]+\b|[A-Za-z]\s*[_=^{])", expression)
        ):
            lines.append(_display(expression))
        else:
            lines.append(line)
    return "\n".join(lines)


def format_math_markdown(text: str) -> str:
    """Render explicit LaTeX math; preserve existing math and code verbatim.

    This is display formatting, not algebra validation or formula reconstruction.
    """
    parts = _TOKENS.split(text)
    for index, part in enumerate(parts):
        if index % 2 == 0:
            parts[index] = _format_bare(part)
        elif part.startswith(r"\["):
            parts[index] = _display(part[2:-2])
        elif part.startswith(r"\("):
            parts[index] = "$" + part[2:-2].strip() + "$"
    return "".join(parts)
