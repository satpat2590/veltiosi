"""Markdown parsing and manipulation utilities for Veltiosi."""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


def extract_wikilinks(content: str) -> List[str]:
    """Extract all wikilinks from markdown content.

    Args:
        content: Markdown content

    Returns:
        List of wikilink targets (without brackets)
    """
    # Pattern for [[Link]] or [[Folder/Link]]
    pattern = r"\[\[([^\]]+)\]\]"
    matches = re.findall(pattern, content)

    # Clean up the matches
    links = []
    for match in matches:
        # Remove any alias (| alias)
        link = match.split("|")[0].strip()
        if link:
            links.append(link)

    return links


def extract_heading(content: str) -> Optional[str]:
    """Extract the first heading from markdown content.

    Args:
        content: Markdown content

    Returns:
        First heading text (without #), or None if no heading
    """
    lines = content.split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
        elif line.startswith("## "):
            return line[3:].strip()
        elif line.startswith("### "):
            return line[4:].strip()

    return None


def has_slope_section(content: str) -> bool:
    """Check if markdown content has a slope section.

    Looks for headings containing "slope" (case-insensitive).

    Args:
        content: Markdown content

    Returns:
        True if slope section found
    """
    lines = content.split("\n")
    for line in lines:
        line = line.strip().lower()
        if line.startswith(("# ", "## ", "### ")) and "slope" in line:
            return True

    return False


def extract_generated_section(
    content: str, section_name: str, start_marker: str, end_marker: str
) -> Optional[str]:
    """Extract a generated section from markdown content.

    Args:
        content: Markdown content
        section_name: Name of the section (for debugging)
        start_marker: Start marker pattern
        end_marker: End marker pattern

    Returns:
        Section content (without markers), or None if not found
    """
    # Build the full markers with section name
    full_start_marker = f"{start_marker} section={section_name} -->"
    full_end_marker = f"{end_marker} section={section_name} -->"

    start_idx = content.find(full_start_marker)
    if start_idx == -1:
        return None

    end_idx = content.find(full_end_marker, start_idx)
    if end_idx == -1:
        return None

    # Extract content between markers
    section_start = start_idx + len(full_start_marker)
    return content[section_start:end_idx].strip()


def replace_generated_section(
    content: str,
    section_name: str,
    new_content: str,
    start_marker: str,
    end_marker: str,
) -> str:
    """Replace a generated section in markdown content.

    Args:
        content: Original markdown content
        section_name: Name of the section
        new_content: New section content
        start_marker: Start marker pattern
        end_marker: End marker pattern

    Returns:
        Updated markdown content
    """
    # Build the full markers
    full_start_marker = f"{start_marker} section={section_name} -->"
    full_end_marker = f"{end_marker} section={section_name} -->"

    # Check if section exists
    start_idx = content.find(full_start_marker)
    if start_idx == -1:
        # Section doesn't exist, append it
        section = f"\n\n{full_start_marker}\n{new_content}\n{full_end_marker}"
        return content.rstrip() + section

    # Section exists, replace it
    end_idx = content.find(full_end_marker, start_idx)
    if end_idx == -1:
        # Malformed section, append new one at end
        section = f"\n\n{full_start_marker}\n{new_content}\n{full_end_marker}"
        return content.rstrip() + section

    # Replace the section
    before = content[:start_idx]
    after = content[end_idx + len(full_end_marker) :]
    return before + full_start_marker + "\n" + new_content + "\n" + full_end_marker + after


def extract_frontmatter(content: str) -> Tuple[Optional[Dict], str]:
    """Extract frontmatter from markdown content.

    Args:
        content: Markdown content

    Returns:
        Tuple of (frontmatter dict or None, content without frontmatter)
    """
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, content

    frontmatter_lines = []
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        frontmatter_lines.append(lines[i])
        i += 1

    if i >= len(lines):
        # No closing ---
        return None, content

    # Parse frontmatter
    frontmatter = {}
    for line in frontmatter_lines:
        if ":" in line:
            key, value = line.split(":", 1)
            frontmatter[key.strip()] = value.strip()

    # Return content after frontmatter
    remaining_content = "\n".join(lines[i + 1 :])
    return frontmatter, remaining_content


def normalize_wikilink(link: str, current_path: Path) -> str:
    """Normalize a wikilink to a consistent format.

    Args:
        link: Wikilink target
        current_path: Path of the current note

    Returns:
        Normalized wikilink
    """
    # Remove any alias
    link = link.split("|")[0].strip()

    # If link contains a slash, it might be a path
    if "/" in link:
        # Check if it's a relative path
        if not link.startswith("/"):
            # Try to resolve relative to current path's parent
            try:
                resolved = (current_path.parent / link).resolve()
                # Convert back to wiki path format
                # This is simplified - actual Obsidian resolution is more complex
                return link
            except:
                pass

    return link


def count_links(content: str) -> Dict[str, int]:
    """Count different types of links in markdown content.

    Args:
        content: Markdown content

    Returns:
        Dict with counts for wikilinks, markdown links, and external links
    """
    wikilinks = len(extract_wikilinks(content))

    # Markdown links [text](url)
    md_link_pattern = r"\[[^\]]+\]\([^)]+\)"
    md_links = len(re.findall(md_link_pattern, content))

    # External URLs (http/https)
    url_pattern = r"https?://[^\s<>\"']+"
    external_links = len(re.findall(url_pattern, content))

    return {
        "wikilinks": wikilinks,
        "markdown_links": md_links,
        "external_links": external_links,
    }


def extract_table_rows(content: str, table_heading: Optional[str] = None) -> List[List[str]]:
    """Extract rows from a markdown table.

    Args:
        content: Markdown content
        table_heading: Optional heading to find specific table

    Returns:
        List of rows, each row is a list of cells
    """
    lines = content.split("\n")
    in_table = False
    rows = []

    for line in lines:
        line = line.strip()

        # Check if we're looking for a specific table
        if table_heading and line.startswith("## ") and table_heading.lower() in line.lower():
            # Found the section, start looking for table
            in_table = True
            continue

        # Look for table start
        if "|" in line and ("---" in line or "===" in line):
            in_table = True
            continue

        # If in table and line contains pipes
        if in_table and "|" in line:
            # Skip separator rows
            if re.match(r"^\|?[-:| ]+\|?$", line):
                continue

            # Parse row
            cells = [cell.strip() for cell in line.split("|") if cell.strip()]
            if cells:
                rows.append(cells)

        # If we exit the table section
        elif in_table and line.startswith("#"):
            break

    return rows


def add_table_row(table_content: str, new_row: List[str]) -> str:
    """Add a row to a markdown table.

    Args:
        table_content: Existing table content (including headers and separators)
        new_row: New row to add

    Returns:
        Updated table content
    """
    lines = table_content.split("\n")

    # Find the separator line (contains --- or ===)
    separator_idx = -1
    for i, line in enumerate(lines):
        if "|" in line and ("---" in line or "===" in line):
            separator_idx = i
            break

    if separator_idx == -1:
        # Not a valid table
        return table_content

    # Insert new row after separator
    new_row_str = "| " + " | ".join(new_row) + " |"
    lines.insert(separator_idx + 1, new_row_str)

    return "\n".join(lines)


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for use in Obsidian.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename
    """
    # Remove invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, "")

    # Replace multiple spaces with single space
    filename = re.sub(r"\s+", " ", filename)

    # Trim whitespace
    filename = filename.strip()

    # Ensure it ends with .md
    if not filename.endswith(".md"):
        filename += ".md"

    return filename


def generate_markdown_table(headers: List[str], rows: List[List[str]]) -> str:
    """Generate a markdown table from headers and rows.

    Args:
        headers: List of header strings
        rows: List of rows, each row is a list of strings

    Returns:
        Markdown table as string
    """
    if not headers:
        return ""

    # Create header row
    header_row = "| " + " | ".join(headers) + " |"

    # Create separator row
    separator_row = "| " + " | ".join(["---" for _ in headers]) + " |"

    # Create data rows
    data_rows = []
    for row in rows:
        # Ensure row has same number of columns as headers
        if len(row) != len(headers):
            # Pad or truncate row
            if len(row) < len(headers):
                row = row + [""] * (len(headers) - len(row))
            else:
                row = row[: len(headers)]

        data_row = "| " + " | ".join(str(cell) for cell in row) + " |"
        data_rows.append(data_row)

    # Combine all rows
    table_lines = [header_row, separator_row] + data_rows
    return "\n".join(table_lines)
