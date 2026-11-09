"""Public error descriptions are fixed strings; request bodies are never echoed."""


class Problem(Exception):
    def __init__(self, status: int, code: str, title: str, detail: str | None = None):
        self.status, self.code, self.title, self.detail = (
            status,
            code,
            title,
            detail or title,
        )
        super().__init__(code)
