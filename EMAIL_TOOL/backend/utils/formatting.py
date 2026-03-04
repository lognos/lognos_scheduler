"""Formatting utilities for text and HTML conversion."""

import logfire
import markdown
import bleach


def convert_markdown_to_html(markdown_text: str) -> str:
    """
    Convert markdown content to sanitized HTML.

    Supports:
    - Tables
    - Fenced code blocks
    - Newline to <br> conversion
    - Sanitization to prevent XSS

    Args:
        markdown_text: Markdown formatted text

    Returns:
        Clean HTML string (content only, no template wrapper)

    Example:
        >>> md = "# Hello\\n\\nThis is **bold** text."
        >>> html = convert_markdown_to_html(md)
        >>> print(html)
        <h1>Hello</h1><p>This is <strong>bold</strong> text.</p>
    """
    with logfire.span("convert_markdown_to_html"):
        # Convert markdown to HTML
        html = markdown.markdown(
            markdown_text,
            extensions=["tables", "fenced_code", "nl2br"],
        )

        # Sanitize HTML (security - prevent XSS)
        allowed_tags = [
            "p",
            "br",
            "strong",
            "em",
            "u",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "ul",
            "ol",
            "li",
            "table",
            "thead",
            "tbody",
            "tr",
            "th",
            "td",
            "blockquote",
            "code",
            "pre",
            "div",
            "span",
            "a",
        ]

        allowed_attributes = {
            "a": ["href", "title"],
            "table": ["class"],
            "th": ["class"],
            "td": ["class"],
            "div": ["class"],
            "span": ["class"],
        }

        clean_html = bleach.clean(
            html,
            tags=allowed_tags,
            attributes=allowed_attributes,
            strip=True,
        )

        logfire.info("Converted markdown to HTML", length=len(clean_html))
        return clean_html
