"""Email template utilities for consistent HTML formatting."""

import logfire
from datetime import datetime
from jinja2 import Template


def apply_email_template(
    content_html: str,
    subject: str,
    sender_note: str | None = None,
) -> str:
    """
    Wrap content in professional email template.

    Applies consistent styling:
    - Professional fonts and spacing
    - Styled headers, tables, code blocks
    - Footer with LOGNOS Assistant branding
    - Timestamp and optional sender note

    Args:
        content_html: HTML content to wrap (already converted from markdown)
        subject: Email subject (for context)
        sender_note: Optional note about sender/request context

    Returns:
        Complete HTML email with styling and template wrapper

    Example:
        >>> html_content = "<p>Hello <strong>world</strong></p>"
        >>> full_email = apply_email_template(html_content, "Test Subject")
        >>> # Returns full HTML document with styling and footer
    """
    with logfire.span("apply_email_template"):
        template_str = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {
            font-family: 'Helvetica Neue', Arial, sans-serif;
            font-size: 14px;
            line-height: 1.6;
            color: #333333;
            margin: 0;
            padding: 20px;
        }
        .content {
            margin: 20px 0;
        }
        .footer {
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
            font-size: 11px;
            color: #666666;
        }
        h1, h2, h3 { 
            font-weight: 600;
            color: #222222;
        }
        table { 
            border-collapse: collapse; 
            width: 100%; 
            margin: 15px 0;
        }
        th, td { 
            border: 1px solid #ddd; 
            padding: 8px; 
            text-align: left;
        }
        th {
            background-color: #f2f2f2;
            font-weight: bold;
        }
        code {
            background-color: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
        }
        pre {
            background-color: #f4f4f4;
            padding: 10px;
            border-radius: 5px;
            overflow-x: auto;
        }
        blockquote {
            border-left: 4px solid #0078d4;
            padding-left: 15px;
            margin-left: 0;
            color: #555555;
        }
        a {
            color: #0078d4;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="content">
        {{ content }}
    </div>
    
    <div class="footer">
        <p style="font-size: 10px; color: #999999;">Generated automatically by LOGNOS platform on {{ timestamp }}</p>
        {% if sender_note %}
        <p><em>{{ sender_note }}</em></p>
        {% endif %}
    </div>
</body>
</html>
        """

        template = Template(template_str)
        now = datetime.now()

        full_html = template.render(
            content=content_html,
            subject=subject,
            timestamp=now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            sender_note=sender_note,
        )

        logfire.info(
            "Applied email template",
            subject=subject,
            has_sender_note=bool(sender_note),
        )

        return full_html
