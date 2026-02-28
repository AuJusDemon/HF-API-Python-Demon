"""
HFBBCodeBuilder — Programmatic BBCode generation for HackForums posts.

HFBBCode only parses (BBCode → text/HTML). This module goes the other
direction — build BBCode strings programmatically without manual string
concatenation and forgetting to close tags.

Usage:
    from HFBBCodeBuilder import BBCode

    # Method chaining:
    post = (
        BBCode()
        .bold("Important notice")
        .newline()
        .text("Please read the following carefully.")
        .newline(2)
        .quote("Stan", "I think this deal is sketchy")
        .text("I disagree. Here's proof: ")
        .url("https://hackforums.net/showthread.php?tid=123", "thread link")
        .newline()
        .hr()
        .center(BBCode().bold("Stay safe out there").build())
        .build()
    )

    # Then post it:
    from HFPosts import HFPosts
    HFPosts(token).reply(tid=6083735, message=post)

    # Mention a user:
    msg = BBCode().text("Hey ").mention("AuJusDemon").text(", check this out!").build()

    # Code block:
    msg = BBCode().code("python", "print('hello world')").build()

    # Spoiler:
    msg = BBCode().spoiler("Click to reveal", BBCode().text("Secret content!").build()).build()

    # Lists:
    msg = (
        BBCode()
        .list_items(["First item", "Second item", "Third item"])
        .build()
    )

    msg = (
        BBCode()
        .ordered_list(["Step one", "Step two", "Step three"])
        .build()
    )

All methods return self for chaining. Call build() at the end to get the string.

HF ALIGNMENT NOTE:
    HackForums uses [align=x] syntax, not [left]/[center]/[right] standalone tags.
    Valid values: left, center, right, justify
    Example: [align=center]text[/align]

HF FONT NOTE:
    Valid font names on HackForums (from the editor dropdown):
    Arial, Arial Black, Comic Sans MS, Courier New, Georgia, Impact,
    Sans-serif, Serif, Times New Roman, Trebuchet MS, Verdana
"""


class BBCode:
    """
    Fluent BBCode builder.

    All methods return self so they can be chained. Call build() at the end.

    Example:
        post = BBCode().bold("Hello").newline().text("World!").build()
        # "[b]Hello[/b]\\nWorld!"
    """

    def __init__(self, initial: str = ""):
        self._parts: list[str] = [initial] if initial else []

    # ── Build ──────────────────────────────────────────────────────────────────

    def build(self) -> str:
        """
        Produce the final BBCode string.

        Returns:
            Complete BBCode string ready to POST to HF.
        """
        return "".join(self._parts)

    def __str__(self) -> str:
        return self.build()

    # ── Raw ────────────────────────────────────────────────────────────────────

    def raw(self, bbcode: str) -> "BBCode":
        """
        Append raw BBCode string without escaping.

        Use when you already have BBCode you want to embed.

        Args:
            bbcode: Raw BBCode string.

        Example:
            BBCode().raw("[b]pre-made BBCode[/b]").newline().build()
        """
        self._parts.append(bbcode)
        return self

    def text(self, content: str) -> "BBCode":
        """
        Append plain text content (no BBCode wrapping).

        Args:
            content: Plain text string.

        Example:
            BBCode().text("Hello, world!").build()
            # "Hello, world!"
        """
        self._parts.append(content)
        return self

    def newline(self, count: int = 1) -> "BBCode":
        """
        Append newline(s).

        Args:
            count: Number of newlines (default 1).

        Example:
            BBCode().bold("Title").newline(2).text("Body").build()
        """
        self._parts.append("\n" * count)
        return self

    # ── Text formatting ────────────────────────────────────────────────────────

    def bold(self, text: str) -> "BBCode":
        """
        Bold text.

        Example:
            BBCode().bold("Important!").build()
            # "[b]Important![/b]"
        """
        self._parts.append(f"[b]{text}[/b]")
        return self

    def italic(self, text: str) -> "BBCode":
        """Italic text. → [i]text[/i]"""
        self._parts.append(f"[i]{text}[/i]")
        return self

    def underline(self, text: str) -> "BBCode":
        """Underlined text. → [u]text[/u]"""
        self._parts.append(f"[u]{text}[/u]")
        return self

    def strikethrough(self, text: str) -> "BBCode":
        """Strikethrough text. → [s]text[/s]"""
        self._parts.append(f"[s]{text}[/s]")
        return self

    def superscript(self, text: str) -> "BBCode":
        """Superscript text. → [sup]text[/sup]"""
        self._parts.append(f"[sup]{text}[/sup]")
        return self

    def subscript(self, text: str) -> "BBCode":
        """Subscript text. → [sub]text[/sub]"""
        self._parts.append(f"[sub]{text}[/sub]")
        return self

    # ── Size and color ─────────────────────────────────────────────────────────

    def size(self, text: str, size: int | str) -> "BBCode":
        """
        Set text size.

        Args:
            text: Text content.
            size: Font size — integer (e.g. 14) or string (e.g. "14pt", "large").

        Example:
            BBCode().size("Big text", 20).build()
            # "[size=20]Big text[/size]"
        """
        self._parts.append(f"[size={size}]{text}[/size]")
        return self

    def color(self, text: str, color: str) -> "BBCode":
        """
        Set text color.

        Args:
            text:  Text content.
            color: Color name, hex code (#ff0000), or rgb(r,g,b).

        Example:
            BBCode().color("Red text", "red").build()
            BBCode().color("Blue text", "#0070f3").build()
        """
        self._parts.append(f"[color={color}]{text}[/color]")
        return self

    def font(self, text: str, font_family: str) -> "BBCode":
        """
        Set font family.

        Valid fonts on HackForums:
            Arial, Arial Black, Comic Sans MS, Courier New, Georgia,
            Impact, Sans-serif, Serif, Times New Roman, Trebuchet MS, Verdana

        Example:
            BBCode().font("Hello", "Times New Roman").build()
            # "[font=Times New Roman]Hello[/font]"
        """
        self._parts.append(f"[font={font_family}]{text}[/font]")
        return self

    # ── Alignment ──────────────────────────────────────────────────────────────
    # HackForums uses [align=x] syntax. [center], [left], [right] standalone
    # tags do NOT work on HF — only [align=center] etc. are valid.

    def left(self, content: str) -> "BBCode":
        """Left-align content. → [align=left]content[/align]"""
        self._parts.append(f"[align=left]{content}[/align]")
        return self

    def center(self, content: str) -> "BBCode":
        """
        Center content.

        Args:
            content: Content to center. Can be a nested BBCode string.

        Example:
            BBCode().center(BBCode().bold("Centered Title").build()).build()
            # "[align=center][b]Centered Title[/b][/align]"
        """
        self._parts.append(f"[align=center]{content}[/align]")
        return self

    def right(self, content: str) -> "BBCode":
        """Right-align content. → [align=right]content[/align]"""
        self._parts.append(f"[align=right]{content}[/align]")
        return self

    def justify(self, content: str) -> "BBCode":
        """Justify content. → [align=justify]content[/align]"""
        self._parts.append(f"[align=justify]{content}[/align]")
        return self

    # ── Links ──────────────────────────────────────────────────────────────────

    def url(self, href: str, label: str | None = None) -> "BBCode":
        """
        Hyperlink.

        Args:
            href:  URL.
            label: Link text. If not provided, the URL is used as the label.

        Example:
            BBCode().url("https://hackforums.net", "HF").build()
            # "[url=https://hackforums.net]HF[/url]"

            BBCode().url("https://hackforums.net").build()
            # "[url]https://hackforums.net[/url]"
        """
        if label:
            self._parts.append(f"[url={href}]{label}[/url]")
        else:
            self._parts.append(f"[url]{href}[/url]")
        return self

    def email(self, address: str, label: str | None = None) -> "BBCode":
        """Email link. → [email=addr]label[/email]"""
        lbl = label or address
        self._parts.append(f"[email={address}]{lbl}[/email]")
        return self

    def thread_link(self, tid: int, label: str | None = None) -> "BBCode":
        """
        Link to an HF thread by thread ID.

        Args:
            tid:   Thread ID.
            label: Link text (defaults to "thread #TID").

        Example:
            BBCode().thread_link(6083735, "API test thread").build()
        """
        href = f"https://hackforums.net/showthread.php?tid={tid}"
        lbl  = label or f"thread #{tid}"
        return self.url(href, lbl)

    def post_link(self, pid: int, tid: int, label: str | None = None) -> "BBCode":
        """
        Link to a specific post.

        Args:
            pid:   Post ID.
            tid:   Thread ID (required for anchor).
            label: Link text (defaults to "post #PID").
        """
        href = f"https://hackforums.net/showthread.php?tid={tid}&pid={pid}#pid{pid}"
        lbl  = label or f"post #{pid}"
        return self.url(href, lbl)

    def profile_link(self, uid: int, username: str | None = None) -> "BBCode":
        """
        Link to a user's HF profile.

        Args:
            uid:      User ID.
            username: Display name (defaults to "UID {uid}").
        """
        href = f"https://hackforums.net/member.php?action=profile&uid={uid}"
        lbl  = username or f"UID {uid}"
        return self.url(href, lbl)

    # ── Images ─────────────────────────────────────────────────────────────────

    def image(self, src: str, alt: str | None = None) -> "BBCode":
        """
        Inline image.

        Args:
            src: Image URL.
            alt: Alt text (optional, creates [img=alt]src[/img]).

        Example:
            BBCode().image("https://example.com/pic.png").build()
            # "[img]https://example.com/pic.png[/img]"
        """
        if alt:
            self._parts.append(f"[img={alt}]{src}[/img]")
        else:
            self._parts.append(f"[img]{src}[/img]")
        return self

    # ── Quotes ─────────────────────────────────────────────────────────────────

    def quote(
        self,
        author: str | None = None,
        content: str = "",
        pid: int | None = None,
    ) -> "BBCode":
        """
        Quote block.

        Args:
            author:  Username being quoted (optional).
            content: The quoted text content.
            pid:     Post ID for the quote anchor (optional).

        Example:
            BBCode().quote("Stan", "I think this deal is sketchy").build()
            # "[quote='Stan']I think this deal is sketchy[/quote]"

            BBCode().quote("Stan", "original msg", pid=59852445).build()
            # "[quote='Stan' pid='59852445']original msg[/quote]"

            BBCode().quote(content="anonymous quote").build()
            # "[quote]anonymous quote[/quote]"
        """
        if author and pid:
            tag = f"[quote='{author}' pid='{pid}']"
        elif author:
            tag = f"[quote='{author}']"
        else:
            tag = "[quote]"
        self._parts.append(f"{tag}{content}[/quote]")
        return self

    # ── Code ───────────────────────────────────────────────────────────────────

    def code(self, language: str | None = None, content: str = "") -> "BBCode":
        """
        Code block.

        Args:
            language: Syntax highlighting language (optional, e.g. "python", "php").
            content:  Code content.

        Example:
            BBCode().code("python", "print('hello')").build()
            # "[code=python]print('hello')[/code]"

            BBCode().code(content="no-syntax code block").build()
            # "[code]no-syntax code block[/code]"
        """
        if language:
            self._parts.append(f"[code={language}]{content}[/code]")
        else:
            self._parts.append(f"[code]{content}[/code]")
        return self

    def php(self, content: str) -> "BBCode":
        """PHP code block. → [php]content[/php]"""
        self._parts.append(f"[php]{content}[/php]")
        return self

    # ── Spoiler / hide ─────────────────────────────────────────────────────────

    def spoiler(self, label: str | None = None, content: str = "") -> "BBCode":
        """
        Spoiler block.

        Args:
            label:   Spoiler button text (optional).
            content: Hidden content.

        Example:
            BBCode().spoiler("Click to reveal", "Secret content!").build()
            # "[spoiler=Click to reveal]Secret content![/spoiler]"
        """
        if label:
            self._parts.append(f"[spoiler={label}]{content}[/spoiler]")
        else:
            self._parts.append(f"[spoiler]{content}[/spoiler]")
        return self

    def hide(self, content: str) -> "BBCode":
        """
        Hide block (requires reply to view).

        Example:
            BBCode().hide("Reply to see this content!").build()
            # "[hide]Reply to see this content![/hide]"
        """
        self._parts.append(f"[hide]{content}[/hide]")
        return self

    # ── Lists ──────────────────────────────────────────────────────────────────

    def list_items(self, items: list[str]) -> "BBCode":
        """
        Unordered list.

        Args:
            items: List of item strings (can contain BBCode).

        Example:
            BBCode().list_items(["First", "Second", "Third"]).build()
            # "[list][*]First\n[*]Second\n[*]Third\n[/list]"
        """
        inner = "".join(f"[*]{item}\n" for item in items)
        self._parts.append(f"[list]{inner}[/list]")
        return self

    def ordered_list(self, items: list[str]) -> "BBCode":
        """
        Numbered (ordered) list.

        Args:
            items: List of item strings (can contain BBCode).

        Example:
            BBCode().ordered_list(["Step one", "Step two", "Step three"]).build()
            # "[list=1][*]Step one\n[*]Step two\n[*]Step three\n[/list]"
        """
        inner = "".join(f"[*]{item}\n" for item in items)
        self._parts.append(f"[list=1]{inner}[/list]")
        return self

    # ── Mentions ───────────────────────────────────────────────────────────────

    def mention(self, username: str) -> "BBCode":
        """
        Mention a user (HF [mention] tag — sends them a notification).

        Args:
            username: HF username (exact, case-sensitive).

        Example:
            BBCode().text("Hey ").mention("AuJusDemon").text(", check this!").build()
            # "Hey [mention]AuJusDemon[/mention], check this!"
        """
        self._parts.append(f"[mention]{username}[/mention]")
        return self

    # ── Structure ──────────────────────────────────────────────────────────────

    def hr(self) -> "BBCode":
        """
        Horizontal rule separator.

        Example:
            BBCode().text("Above").hr().text("Below").build()
            # "Above[hr]Below"
        """
        self._parts.append("[hr]")
        return self

    def br(self) -> "BBCode":
        """Explicit line break tag. Usually you want newline() instead."""
        self._parts.append("[br]")
        return self

    # ── Convenience combinations ───────────────────────────────────────────────

    def header(self, text: str, color: str | None = None) -> "BBCode":
        """
        Bold, large, optionally colored header text followed by a newline.

        Args:
            text:  Header text.
            color: Optional color (name or hex).

        Example:
            BBCode().header("My Thread Title", color="#5865F2").build()
        """
        inner = f"[b][size=5]{text}[/size][/b]"
        if color:
            inner = f"[color={color}]{inner}[/color]"
        self._parts.append(inner)
        self._parts.append("\n")
        return self

    def section(self, title: str, content: str, title_color: str | None = None) -> "BBCode":
        """
        Bold section title + body content block.

        Args:
            title:       Section header text.
            content:     Body content (can be BBCode).
            title_color: Optional title color.

        Example:
            post = (
                BBCode()
                .section("Requirements", BBCode().list_items(["18+", "US only"]).build())
                .build()
            )
        """
        title_part = f"[b]{title}[/b]"
        if title_color:
            title_part = f"[color={title_color}]{title_part}[/color]"
        self._parts.append(f"{title_part}\n{content}\n")
        return self

    def price_tag(self, amount: int | float | str, currency: str = "bytes") -> "BBCode":
        """
        Formatted price display.

        Args:
            amount:   Numeric price.
            currency: Currency label (default "bytes").

        Example:
            BBCode().price_tag(500, "bytes").build()
            # "[b]500 bytes[/b]"
        """
        self._parts.append(f"[b]{amount} {currency}[/b]")
        return self

    def separator(self, char: str = "─", length: int = 40) -> "BBCode":
        """
        Text separator line.

        Args:
            char:   Character to repeat.
            length: Number of characters.

        Example:
            BBCode().separator().build()
            # "────────────────────────────────────────"
        """
        self._parts.append(char * length + "\n")
        return self

    # ── Class-level shortcuts ──────────────────────────────────────────────────

    @classmethod
    def from_parts(cls, *parts: str) -> "BBCode":
        """
        Create a BBCode builder pre-populated with multiple raw parts.

        Example:
            BBCode.from_parts("[b]hello[/b]", " ", "[i]world[/i]").build()
        """
        b = cls()
        for part in parts:
            b._parts.append(part)
        return b

    @classmethod
    def make_quote(cls, author: str, content: str, pid: int | None = None) -> str:
        """Shortcut — produce a quote string without chaining."""
        return cls().quote(author, content, pid).build()

    @classmethod
    def make_url(cls, href: str, label: str | None = None) -> str:
        """Shortcut — produce a URL string without chaining."""
        return cls().url(href, label).build()

    @classmethod
    def make_mention(cls, username: str) -> str:
        """Shortcut — produce a mention string without chaining."""
        return cls().mention(username).build()

    @classmethod
    def make_code(cls, content: str, language: str | None = None) -> str:
        """Shortcut — produce a code block string without chaining."""
        return cls().code(language, content).build()
