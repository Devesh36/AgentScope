"""Small terminal renderer; piped sessions stay plain and dependency-free."""

import os
import re
import shutil
import textwrap


def plain(value):
    # Repository names and server text must never become terminal control codes.
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", str(value))


class Terminal:
    def __init__(self, stream):
        self.stream = stream
        self.interactive = bool(getattr(stream, "isatty", lambda: False)())
        self.color = (
            self.interactive
            and "NO_COLOR" not in os.environ
            and os.environ.get("TERM", "") != "dumb"
        )

    @property
    def width(self):
        return max(24, min(96, shutil.get_terminal_size((80, 24)).columns))

    def style(self, value, tone="amber", prompt=False):
        value = plain(value)
        if not self.color:
            return value
        codes = {"amber": "33", "muted": "90", "strong": "1", "error": "31"}
        start, end = f"\033[{codes[tone]}m", "\033[0m"
        # Readline excludes these markers when calculating the editable prompt.
        if prompt:
            start, end = f"\001{start}\002", f"\001{end}\002"
        return start + value + end

    def write(self, value=""):
        print(value, file=self.stream)

    def text(self, value, tone=None):
        for line in textwrap.wrap(plain(value), self.width) or [""]:
            self.write(self.style(line, tone) if tone else line)

    def heading(self, title, detail=None):
        self.write()
        self.write(self.style(plain(title).upper(), "amber"))
        if detail:
            self.text(detail, "muted")

    def pairs(self, items):
        size = min(24, max((len(plain(key)) for key, _ in items), default=0))
        for key, value in items:
            prefix = f"  {plain(key):<{size}}  "
            available = self.width - len(prefix)
            if available < 12:
                self.text(key, "strong")
                self.text(value)
                continue
            lines = textwrap.wrap(plain(value), available) or [""]
            self.write(self.style(prefix, "strong") + lines[0])
            for line in lines[1:]:
                self.write(" " * len(prefix) + line)

    def record(self, title, detail, identifier):
        self.text(title, "strong")
        self.text(detail, "muted")
        self.text(f"ID: {identifier}")
        self.write()

    def banner(self, version, directory, endpoint):
        self.write()
        self.write(self.style("+" + "-" * (self.width - 2) + "+"))
        self.text(f"  AGENTSCOPE / {version}", "strong")
        self.text("  Observe. Investigate. Understand.", "amber")
        self.write(self.style("+" + "-" * (self.width - 2) + "+"))
        self.pairs([("Directory", directory), ("API target", endpoint)])
        self.text(
            "API target is configured; connectivity has not been checked.", "muted"
        )
        self.heading("Start here")
        self.pairs(
            [
                ("configure", "Choose AgentScope's chat model before asking questions"),
                ("Who are you?", "Meet AgentScope through your configured model"),
                ("watch", "Start monitoring this repository"),
                ("guide", "Walk through your first monitoring session"),
                ("help", "Browse commands and examples"),
            ]
        )
        self.write()
        self.text(
            "Tip: /help also works. Tab completes commands. Ctrl-D exits.", "muted"
        )
        self.text(
            "Watch captures metadata. Factual accuracy needs a grounding evaluation.",
            "muted",
        )
        self.write()
