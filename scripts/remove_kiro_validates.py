#!/usr/bin/env python3
"""Remove Kiro-generated 'Validates: Requirement ...' lines from Python docstrings.

This script processes Python files to remove validation documentation lines that Kiro
adds to docstrings. After removal, it ensures the docstrings remain properly formatted
according to Ruff's formatting rules:

1. Single-line docstrings: Collapsed to one line with closing quotes on the same line
2. Multi-line docstrings: No consecutive blank lines within the docstring

The script can be used as a pre-commit hook or run manually on files/directories.
"""

import re
import sys
from pathlib import Path

# Constants for docstring parsing
TRIPLE_QUOTE_LENGTH = 3
MIN_ARGS_FOR_PATH_PROCESSING = 2

# Regex patterns to match various forms of Validates lines
VALIDATES_PATTERNS = [
    r"^\s*Validates:\s*Requirement.*$",
    r"^\s*\**Validates:\s*Requirement.*\**$",
    r"(?im)^\s*(?:\*\*)?\s*Validates\s*:\s*(?:\*\*)?\s*Requirement.*$",
    r"(?im)^[\s*]*Validates\s*:\s*Requirement\s*[\d\.\s*]*$",
]

_compiled_patterns = [re.compile(pattern) for pattern in VALIDATES_PATTERNS]


def is_validates_line(line: str) -> bool:
    """Check if a line matches any Validates pattern.

    Args:
        line: The line to check.

    Returns:
        True if the line contains a Validates statement, False otherwise.
    """
    return any(pattern.search(line) for pattern in _compiled_patterns)


def get_indent(line: str) -> str:
    """Extract the leading whitespace from a line.

    Args:
        line: The line to analyze.

    Returns:
        The leading whitespace string.
    """
    return line[: len(line) - len(line.lstrip())]


def remove_consecutive_blank_lines(lines: list[str]) -> list[str]:
    """Remove consecutive blank lines, keeping only one.

    Args:
        lines: List of lines to process.

    Returns:
        List with consecutive blank lines collapsed to single blank lines.
    """
    result = []
    previous_was_blank = False

    for line in lines:
        is_blank = not line.strip()

        if is_blank and previous_was_blank:
            continue  # Skip consecutive blank

        result.append(line)
        previous_was_blank = is_blank

    return result


def remove_trailing_blank_lines(lines: list[str]) -> list[str]:
    """Remove blank lines from the end of a list.

    Args:
        lines: List of lines to process.

    Returns:
        List with trailing blank lines removed.
    """
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def get_non_blank_content_lines(lines: list[str]) -> list[str]:
    """Filter out blank lines from a list.

    Args:
        lines: List of lines to filter.

    Returns:
        List containing only non-blank lines.
    """
    return [line for line in lines if line.strip()]


def format_single_line_docstring(content_line: str, base_indent: str) -> str:
    """Format a single-line docstring with proper indentation and closing quotes.

    Args:
        content_line: The content line (without closing quotes).
        base_indent: The indentation to use.

    Returns:
        Properly formatted single-line docstring with newline.
    """
    stripped_content = content_line.strip()
    # Remove opening quotes if present
    if stripped_content.startswith(('"""', "'''")):
        stripped_content = stripped_content[3:]
    return f'{base_indent}"""{stripped_content}"""\n'


def format_multi_line_docstring(lines: list[str], base_indent: str) -> list[str]:
    """Format multi-line docstring by removing consecutive blanks and adding closing quotes.

    Args:
        lines: The docstring content lines (without closing quotes).
        base_indent: The base indentation level.

    Returns:
        Formatted docstring lines with proper closing.
    """
    # Remove consecutive blank lines
    cleaned = remove_consecutive_blank_lines(lines)

    # Remove trailing blank lines before closing quotes
    cleaned = remove_trailing_blank_lines(cleaned)

    # Add closing quotes with proper indentation
    cleaned.append(f'{base_indent}"""\n')

    return cleaned


def has_content_on_opening_line(opening_line: str) -> bool:
    """Check if the opening docstring line has content after the triple quotes.

    Args:
        opening_line: The line containing the opening triple quotes.

    Returns:
        True if there's content after the quotes, False otherwise.
    """
    stripped = opening_line.strip()
    # Check if there's anything after the opening """
    return len(stripped) > TRIPLE_QUOTE_LENGTH and not stripped[TRIPLE_QUOTE_LENGTH:].isspace()


def extract_opening_content(opening_line: str) -> str:
    """Extract content that appears after opening triple quotes.

    Args:
        opening_line: The line containing the opening triple quotes.

    Returns:
        The content after the triple quotes, stripped of whitespace.
    """
    stripped = opening_line.strip()
    return stripped[TRIPLE_QUOTE_LENGTH:].strip() if len(stripped) > TRIPLE_QUOTE_LENGTH else ""


def process_docstring_content(content_lines: list[str], base_indent: str, opening_line: str) -> list[str]:
    """Process docstring content after Validates lines are removed.

    Determines if the result should be a single-line or multi-line docstring
    and formats accordingly.

    Args:
        content_lines: Lines of docstring content (excluding opening/closing quotes).
        base_indent: The base indentation for the docstring.
        opening_line: The original opening line with triple quotes.

    Returns:
        Formatted docstring lines ready to write.
    """
    has_opening_content = has_content_on_opening_line(opening_line)
    opening_content = extract_opening_content(opening_line) if has_opening_content else ""

    non_blank = get_non_blank_content_lines(content_lines)

    # Determine total content lines (opening content + body content)
    total_content_lines = (1 if has_opening_content else 0) + len(non_blank)

    if total_content_lines == 0:
        # Empty docstring after removal
        return [f'{base_indent}"""\n']

    if total_content_lines == 1:
        # Single line of content - format as single-line docstring
        if has_opening_content:
            # Content is on the opening line
            return [f'{base_indent}"""{opening_content}"""\n']
        else:
            # Content is in the body
            return [format_single_line_docstring(non_blank[0], base_indent)]

    # Multiple lines - format as multi-line docstring
    # If opening had content, we need to reconstruct with that content
    if has_opening_content:
        result = [f'{base_indent}"""{opening_content}\n']
        result.extend(format_multi_line_docstring(content_lines, base_indent))
        return result
    else:
        return format_multi_line_docstring(content_lines, base_indent)


def find_docstring_closing(lines: list[str], start_idx: int) -> int | None:
    """Find the index of the closing triple quotes for a docstring.

    Args:
        lines: All lines in the file.
        start_idx: Index to start searching from (after opening quotes).

    Returns:
        Index of the closing quotes line, or None if not found.
    """
    for i in range(start_idx, len(lines)):
        if lines[i].strip().startswith(('"""', "'''")):
            return i
    return None


def extract_docstring_content(lines: list[str], start_idx: int, end_idx: int) -> tuple[list[str], bool]:
    """Extract content lines from a docstring and check for Validates lines.

    Args:
        lines: All lines in the file.
        start_idx: Index after the opening quotes.
        end_idx: Index of the closing quotes.

    Returns:
        Tuple of (content_lines, has_validates_line).
    """
    content_lines = []
    has_validates = False

    for i in range(start_idx, end_idx):
        line = lines[i]
        if is_validates_line(line):
            has_validates = True
            continue  # Skip Validates lines
        content_lines.append(line)

    return content_lines, has_validates


def process_file_lines(lines: list[str]) -> tuple[list[str], bool]:
    """Process all lines in a file, cleaning docstrings that contain Validates lines.

    Args:
        lines: Original file lines (with line endings preserved).

    Returns:
        Tuple of (processed_lines, was_modified).
    """
    result = []
    i = 0
    was_modified = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Check if this is the start of a multi-line docstring
        is_docstring_start = stripped.startswith(('"""', "'''")) and (
            not stripped.endswith(('"""', "'''")) or len(stripped) == TRIPLE_QUOTE_LENGTH
        )

        if not is_docstring_start:
            # Not a docstring start - keep line as is
            result.append(line)
            i += 1
            continue

        # Found docstring opening
        base_indent = get_indent(line)
        opening_line = line
        i += 1

        # Find closing quotes
        closing_idx = find_docstring_closing(lines, i)
        if closing_idx is None:
            # Malformed docstring - keep opening and remaining lines as is
            result.append(opening_line)
            result.extend(lines[i:])
            break

        # Extract content and check for Validates lines
        content_lines, has_validates = extract_docstring_content(lines, i, closing_idx)

        if has_validates:
            # Process and reformat the docstring (includes opening line)
            processed = process_docstring_content(content_lines, base_indent, opening_line)
            result.extend(processed)
            was_modified = True
        else:
            # No Validates lines - keep original opening, content and closing
            result.append(opening_line)
            result.extend(lines[i : closing_idx + 1])

        i = closing_idx + 1

    return result, was_modified


def clean_python_file(filepath: Path) -> bool:
    """Clean a single Python file by removing Validates lines from docstrings.

    Args:
        filepath: Path to the Python file to process.

    Returns:
        True if the file was modified, False otherwise.
    """
    try:
        original_content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"  Error reading {filepath}: {e}", file=sys.stderr)
        return False

    lines = original_content.splitlines(keepends=True)
    new_lines, was_modified = process_file_lines(lines)

    if not was_modified:
        return False

    try:
        new_content = "".join(new_lines)
        filepath.write_text(new_content, encoding="utf-8", newline="\n")
        print(f"  Cleaned: {filepath}")
        return True
    except OSError as e:
        print(f"  Error writing {filepath}: {e}", file=sys.stderr)
        return False


def process_path(path: Path) -> int:
    """Process a file or directory, cleaning all Python files found.

    Args:
        path: Path to a file or directory to process.

    Returns:
        Number of files modified.
    """
    if path.is_file():
        if path.suffix == ".py":
            return 1 if clean_python_file(path) else 0
        return 0

    if path.is_dir():
        count = 0
        for pyfile in path.rglob("*.py"):
            if clean_python_file(pyfile):
                count += 1
        return count

    print(f"  Warning: {path} is neither a file nor directory", file=sys.stderr)
    return 0


def main() -> int:
    """Main entry point for the script.

    Returns:
        Exit code: 0 if successful, 1 if no paths provided.
    """
    if len(sys.argv) < MIN_ARGS_FOR_PATH_PROCESSING:
        print("Usage: python remove_kiro_validates.py <path> [...]", file=sys.stderr)
        print("  <path> can be a Python file or directory", file=sys.stderr)
        return 1

    total_modified = 0
    for arg in sys.argv[1:]:
        path = Path(arg)
        total_modified += process_path(path)

    if total_modified:
        print(f"\nModified {total_modified} file(s)")
    else:
        print("\nNo changes needed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
