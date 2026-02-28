"""
HFBBCode — BBCode parser for HackForums post content.

Converts BBCode from HF post messages to plain text or HTML.
Handles all BBCode tags used on HackForums.

Usage:
    from HFBBCode import HFBBCode

    raw     = "[b]Hello[/b] [url=https://example.com]click here[/url]"
    text    = HFBBCode.to_text(raw)   # "Hello click here"
    html    = HFBBCode.to_html(raw)   # "<b>Hello</b> <a href='...'>click here</a>"
    preview = HFBBCode.preview(raw, length=100)  # plain text, truncated
"""

import re


class HFBBCode:
    """
    Parse and convert BBCode from HackForums post messages.

    HF uses standard MyBB BBCode. All methods are static — no instance needed.
    """

    # ── Public API ─────────────────────────────────────────────────────────────

    @staticmethod
    def to_text(bbcode: str) -> str:
        """
        Strip all BBCode tags and return plain text.

        Preserves the visible text content of links, quotes, etc.
        Useful for mention/quote detection, search, notifications.

        Args:
            bbcode: Raw BBCode string from HF API post message field.

        Returns:
            Plain text string with all BBCode removed.

        Example:
            >>> HFBBCode.to_text("[b]Hello[/b] [url=https://x.com]world[/url]")
            'Hello world'
        """
        s = bbcode or ""
        s = HFBBCode._handle_special_blocks(s, html=False)
        s = HFBBCode._replace_tags(s, html=False)
        s = HFBBCode._clean(s)
        return s.strip()

    @staticmethod
    def to_html(bbcode: str) -> str:
        """
        Convert BBCode to HTML.

        Args:
            bbcode: Raw BBCode string from HF API post message field.

        Returns:
            HTML string.

        Example:
            >>> HFBBCode.to_html("[b]bold[/b] [i]italic[/i]")
            '<b>bold</b> <i>italic</i>'
        """
        s = bbcode or ""
        s = HFBBCode._handle_special_blocks(s, html=True)
        s = HFBBCode._replace_tags(s, html=True)
        s = s.replace("\n", "<br>")
        return s.strip()

    @staticmethod
    def preview(bbcode: str, length: int = 120) -> str:
        """
        Get a short plain-text preview of a post.

        Strips BBCode, collapses whitespace, and truncates.

        Args:
            bbcode: Raw BBCode string.
            length: Max characters (default 120).

        Returns:
            Plain text preview string, truncated with '...' if needed.

        Example:
            >>> HFBBCode.preview("[quote]old stuff[/quote] my actual reply here", length=20)
            'my actual reply here'
        """
        text = HFBBCode.to_text(bbcode)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > length:
            return text[:length].rsplit(" ", 1)[0] + "..."
        return text

    @staticmethod
    def extract_mentions(bbcode: str) -> list[str]:
        """
        Extract all @mentions from a post.

        HF uses [mention]username[/mention] or @username patterns.

        Args:
            bbcode: Raw BBCode string.

        Returns:
            List of mentioned usernames (lowercase, deduplicated).

        Example:
            >>> HFBBCode.extract_mentions("hey [mention]Au Jus Demon[/mention] what's up")
            ['au jus demon']
        """
        mentions = []
        # [mention]username[/mention]
        for m in re.finditer(r"\[mention\](.*?)\[/mention\]", bbcode, re.IGNORECASE):
            mentions.append(m.group(1).strip().lower())
        # @username (word boundary)
        for m in re.finditer(r"@([\w\s]{1,30}?)(?=\s|$|\[|,|\.|!|\?)", bbcode):
            name = m.group(1).strip().lower()
            if name and name not in mentions:
                mentions.append(name)
        return list(dict.fromkeys(mentions))  # deduplicate preserving order

    @staticmethod
    def extract_quotes(bbcode: str) -> list[dict]:
        """
        Extract all quoted content from a post.

        Args:
            bbcode: Raw BBCode string.

        Returns:
            List of dicts with keys: 'author' (str or None), 'content' (plain text).

        Example:
            >>> HFBBCode.extract_quotes("[quote='Stan']hello[/quote] my reply")
            [{'author': 'Stan', 'content': 'hello'}]
        """
        quotes = []
        # [quote='author' pid='123'] or [quote=author] or [quote]
        pattern = re.compile(
            r"\[quote(?:=(?:'([^']*)'|\"([^\"]*)\"|([^'\"\]]*)))?"
            r"(?:\s+pid=['\"]?\d+['\"]?)?\](.*?)\[/quote\]",
            re.IGNORECASE | re.DOTALL,
        )
        for m in pattern.finditer(bbcode):
            author  = m.group(1) or m.group(2) or m.group(3) or None
            content = HFBBCode.to_text(m.group(4) or "")
            quotes.append({"author": author.strip() if author else None, "content": content.strip()})
        return quotes

    @staticmethod
    def extract_links(bbcode: str) -> list[dict]:
        """
        Extract all URLs from a post.

        Args:
            bbcode: Raw BBCode string.

        Returns:
            List of dicts with keys: 'url', 'text'.

        Example:
            >>> HFBBCode.extract_links("[url=https://example.com]click[/url]")
            [{'url': 'https://example.com', 'text': 'click'}]
        """
        links = []
        # [url=href]text[/url]
        for m in re.finditer(r"\[url=([^\]]+)\](.*?)\[/url\]", bbcode, re.IGNORECASE | re.DOTALL):
            links.append({"url": m.group(1).strip(), "text": HFBBCode.to_text(m.group(2))})
        # [url]href[/url]
        for m in re.finditer(r"\[url\](.*?)\[/url\]", bbcode, re.IGNORECASE):
            links.append({"url": m.group(1).strip(), "text": m.group(1).strip()})
        return links

    @staticmethod
    def is_reply_to(bbcode: str, username: str) -> bool:
        """
        Check if a post is quoting or mentioning a specific username.

        Args:
            bbcode:   Raw BBCode string.
            username: Username to check for (case-insensitive).

        Returns:
            True if the post quotes or mentions the username.

        Example:
            >>> HFBBCode.is_reply_to("[quote='Stan']hi[/quote] yeah", "stan")
            True
        """
        name  = username.lower().strip()
        quotes   = HFBBCode.extract_quotes(bbcode)
        mentions = HFBBCode.extract_mentions(bbcode)
        if any(q["author"] and q["author"].lower() == name for q in quotes):
            return True
        if name in mentions:
            return True
        return False

    @staticmethod
    def strip_quotes(bbcode: str) -> str:
        """
        Remove all quoted content from a post, leaving only the new content.

        Useful for getting just what the user actually wrote.

        Args:
            bbcode: Raw BBCode string.

        Returns:
            BBCode with quote blocks removed, then converted to plain text.
        """
        s = re.sub(
            r"\[quote[^\]]*\].*?\[/quote\]", "", bbcode,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return HFBBCode.to_text(s)

    # ── Internal ───────────────────────────────────────────────────────────────

    @staticmethod
    def _handle_special_blocks(s: str, html: bool) -> str:
        """Handle block-level tags: quote, code, spoiler, hide."""
        # Quote blocks
        if html:
            s = re.sub(
                r"\[quote(?:=(?:'([^']*)'|\"([^\"]*)\"|([^'\"\]]*)))?(?:\s+pid=['\"]?\d+['\"]?)?\]",
                lambda m: f"<blockquote><cite>{(m.group(1) or m.group(2) or m.group(3) or 'Quote')}:</cite>",
                s, flags=re.IGNORECASE,
            )
            s = re.sub(r"\[/quote\]", "</blockquote>", s, flags=re.IGNORECASE)
            s = re.sub(r"\[code(?:=[^\]]*)?\](.*?)\[/code\]", r"<pre><code>\1</code></pre>", s, flags=re.IGNORECASE | re.DOTALL)
            s = re.sub(r"\[spoiler(?:=[^\]]*)?\](.*?)\[/spoiler\]", r"<details><summary>Spoiler</summary>\1</details>", s, flags=re.IGNORECASE | re.DOTALL)
            s = re.sub(r"\[hide\](.*?)\[/hide\]", r"<details><summary>Hidden content</summary>\1</details>", s, flags=re.IGNORECASE | re.DOTALL)
        else:
            # Strip quote author, keep content
            s = re.sub(r"\[quote[^\]]*\]", "", s, flags=re.IGNORECASE)
            s = re.sub(r"\[/quote\]", "", s, flags=re.IGNORECASE)
            s = re.sub(r"\[code(?:=[^\]]*)?\](.*?)\[/code\]", r"\1", s, flags=re.IGNORECASE | re.DOTALL)
            s = re.sub(r"\[spoiler(?:=[^\]]*)?\](.*?)\[/spoiler\]", r"\1", s, flags=re.IGNORECASE | re.DOTALL)
            s = re.sub(r"\[hide\](.*?)\[/hide\]", r"\1", s, flags=re.IGNORECASE | re.DOTALL)
        return s

    @staticmethod
    def _replace_tags(s: str, html: bool) -> str:
        """Replace inline BBCode tags."""
        rules_html = [
            # Text formatting
            (r"\[b\](.*?)\[/b\]",              r"<b>\1</b>"),
            (r"\[i\](.*?)\[/i\]",              r"<i>\1</i>"),
            (r"\[u\](.*?)\[/u\]",              r"<u>\1</u>"),
            (r"\[s\](.*?)\[/s\]",              r"<s>\1</s>"),
            (r"\[strike\](.*?)\[/strike\]",    r"<s>\1</s>"),
            (r"\[sup\](.*?)\[/sup\]",          r"<sup>\1</sup>"),
            (r"\[sub\](.*?)\[/sub\]",          r"<sub>\1</sub>"),
            # Size / color
            (r"\[size=([^\]]+)\](.*?)\[/size\]", r"<span style='font-size:\1'>\2</span>"),
            (r"\[color=([^\]]+)\](.*?)\[/color\]", r"<span style='color:\1'>\2</span>"),
            (r"\[font=([^\]]+)\](.*?)\[/font\]", r"<span style='font-family:\1'>\2</span>"),
            # Alignment
            (r"\[left\](.*?)\[/left\]",        r"<div style='text-align:left'>\1</div>"),
            (r"\[center\](.*?)\[/center\]",    r"<div style='text-align:center'>\1</div>"),
            (r"\[right\](.*?)\[/right\]",      r"<div style='text-align:right'>\1</div>"),
            # Links
            (r"\[url=([^\]]+)\](.*?)\[/url\]", r"<a href='\1'>\2</a>"),
            (r"\[url\](.*?)\[/url\]",          r"<a href='\1'>\1</a>"),
            (r"\[email=([^\]]+)\](.*?)\[/email\]", r"<a href='mailto:\1'>\2</a>"),
            # Images
            (r"\[img\](.*?)\[/img\]",          r"<img src='\1'>"),
            (r"\[img=([^\]]+)\](.*?)\[/img\]", r"<img src='\2' alt='\1'>"),
            # Lists
            (r"\[list\](.*?)\[/list\]",        r"<ul>\1</ul>"),
            (r"\[list=1\](.*?)\[/list\]",      r"<ol>\1</ol>"),
            (r"\[\*\](.*?)(?=\[\*\]|\[/list\]|$)", r"<li>\1</li>"),
            # Misc
            (r"\[mention\](.*?)\[/mention\]",  r"<b>@\1</b>"),
            (r"\[hr\]",                        r"<hr>"),
            (r"\[br\]",                        r"<br>"),
            (r"\[video(?:=[^\]]*)?\](.*?)\[/video\]", r"<a href='\1'>[video]</a>"),
            (r"\[php\](.*?)\[/php\]",          r"<pre><code class='php'>\1</code></pre>"),
        ]

        rules_text = [
            # Keep visible text, drop formatting
            (r"\[b\](.*?)\[/b\]",              r"\1"),
            (r"\[i\](.*?)\[/i\]",              r"\1"),
            (r"\[u\](.*?)\[/u\]",              r"\1"),
            (r"\[s\](.*?)\[/s\]",              r"\1"),
            (r"\[strike\](.*?)\[/strike\]",    r"\1"),
            (r"\[sup\](.*?)\[/sup\]",          r"\1"),
            (r"\[sub\](.*?)\[/sub\]",          r"\1"),
            (r"\[size=([^\]]+)\](.*?)\[/size\]", r"\2"),
            (r"\[color=([^\]]+)\](.*?)\[/color\]", r"\2"),
            (r"\[font=([^\]]+)\](.*?)\[/font\]", r"\2"),
            (r"\[left\](.*?)\[/left\]",        r"\1"),
            (r"\[center\](.*?)\[/center\]",    r"\1"),
            (r"\[right\](.*?)\[/right\]",      r"\1"),
            (r"\[url=([^\]]+)\](.*?)\[/url\]", r"\2"),
            (r"\[url\](.*?)\[/url\]",          r"\1"),
            (r"\[email=([^\]]+)\](.*?)\[/email\]", r"\2"),
            (r"\[img\](.*?)\[/img\]",          r""),
            (r"\[img=([^\]]+)\](.*?)\[/img\]", r""),
            (r"\[list\](.*?)\[/list\]",        r"\1"),
            (r"\[list=1\](.*?)\[/list\]",      r"\1"),
            (r"\[\*\](.*?)(?=\[\*\]|\[/list\]|$)", r"\1 "),
            (r"\[mention\](.*?)\[/mention\]",  r"@\1"),
            (r"\[hr\]",                        r""),
            (r"\[br\]",                        r"\n"),
            (r"\[video(?:=[^\]]*)?\](.*?)\[/video\]", r""),
            (r"\[php\](.*?)\[/php\]",          r"\1"),
        ]

        rules = rules_html if html else rules_text
        for pattern, repl in rules:
            s = re.sub(pattern, repl, s, flags=re.IGNORECASE | re.DOTALL)

        # Strip any remaining unknown [tags]
        s = re.sub(r"\[[^\]]{1,30}\]", "", s)
        return s

    @staticmethod
    def _clean(s: str) -> str:
        """Collapse whitespace and clean up leftovers."""
        s = re.sub(r"\n{3,}", "\n\n", s)
        s = re.sub(r" {2,}", " ", s)
        return s
