"""Wikilink formatting utilities for Obsidian/Graphify.

This module provides utility functions for creating, parsing, and manipulating
Obsidian wikilinks ([[Link]]) used throughout the Graphify vault structure.

Wikilinks enable bidirectional linking in Obsidian, forming the backbone of
the knowledge graph. This module handles:
- Basic wikilink formatting
- Wikilink parsing
- Alias support ([[Target|Display]])
- Filename sanitization for note files
- URL-friendly slug generation
"""
import re


def format_wikilink(text: str) -> str:
    """Format text as a wikilink: [[text]].

    Creates a standard Obsidian wikilink from the given text. The text
    is used as both the target and display text.

    Args:
        text: The link target text (e.g., "Python", "Google", "Sent")

    Returns:
        Formatted wikilink string (e.g., "[[Python]]")

    Example:
        >>> format_wikilink("Python")
        '[[Python]]'
        >>> format_wikilink("Google")
        '[[Google]]'
    """
    return f"[[{text}]]"


def parse_wikilink(link: str) -> str | None:
    """Extract the inner text from a wikilink [[text]].

    Parses a wikilink string and returns the target text. Handles both
    simple wikilinks ([[target]]) and aliased wikilinks ([[target|alias]]).

    Args:
        link: Wikilink string to parse (e.g., "[[Python]]" or "[[Python|Py]]")

    Returns:
        The target text if valid wikilink, None otherwise

    Example:
        >>> parse_wikilink("[[Python]]")
        'Python'
        >>> parse_wikilink("[[Python|Py]]")
        'Python'
        >>> parse_wikilink("not a link")
        None
    """
    match = re.match(r"\[\[(.+?)\]\]", link)
    if not match:
        return None
    inner = match.group(1)
    return inner.split("|", 1)[0].strip()


def format_wikilink_with_alias(text: str, alias: str) -> str:
    """Format wikilink with display alias: [[text|alias]].

    Creates an Obsidian wikilink where the target and display text differ.
    Useful for showing user-friendly names while linking to canonical pages.

    Args:
        text: The link target (page name)
        alias: The display text shown in the note

    Returns:
        Formatted wikilink with alias (e.g., "[[Python|Python 3]]")

    Example:
        >>> format_wikilink_with_alias("Python", "Python 3")
        '[[Python|Python 3]]'
        >>> format_wikilink_with_alias("React", "React.js")
        '[[React|React.js]]'
    """
    return f"[[{text}|{alias}]]"


def sanitize_for_filename(text: str) -> str:
    """Sanitize text for use as a filename (remove invalid chars).

    Replaces filesystem-invalid characters with dashes and collapses
    multiple consecutive dashes. Used for generating note filenames
    from application dedup_keys and entity names.

    Args:
        text: Raw text to sanitize

    Returns:
        Filesystem-safe string with only alphanumeric, dash, underscore

    Example:
        >>> sanitize_for_filename("linkedin::12345")
        'linkedin_12345'
        >>> sanitize_for_filename("C++ Developer")
        'C--Developer'
        >>> sanitize_for_filename("Google/Cloud")
        'Google-Cloud'
    """
    # Replace path separators and other problematic chars
    text = text.replace("::", "_")
    text = text.replace("/", "-").replace("\\", "-")
    text = text.replace(":", "-").replace("*", "-")
    text = text.replace("?", "-").replace("\"", "-")
    text = text.replace("<", "-").replace(">", "-")
    text = text.replace("|", "-")
    text = text.replace("#", "sharp").replace("+", "plus")
    # Collapse multiple dashes
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug.

    Lowercases text, removes non-alphanumeric characters (except spaces
    and dashes), converts spaces to dashes, and collapses multiple dashes.
    Used for generating clean URLs and identifiers.

    Args:
        text: Raw text to slugify

    Returns:
        Lowercase URL-safe slug

    Example:
        >>> slugify("Senior Python Developer")
        'senior-python-developer'
        >>> slugify("C# / .NET Engineer")
        'c-net-engineer'
        >>> slugify("React & Node.js")
        'react-node-js'
    """
    text = text.lower()
    text = text.replace("#", "-sharp ").replace("+", "-plus ")
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")