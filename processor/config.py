"""Runtime configuration from environment variables."""

import os


class Config:
    """Everything one conversion run needs.

    SITE picks the reader that knows a source's quirks. Everything downstream
    of it is the same for every site, which is the point of the interchange
    format: one writer, many extractors.
    """

    INPUT_DIR: str
    OUTPUT_DIR: str
    SITE: str
    DUPLICATE_RULE: str
    JSON_BODIES: bool
    SOURCE_PREFIX: str

    def __init__(self) -> None:
        self.INPUT_DIR = os.getenv("INPUT_DIR", "/data/input")
        self.OUTPUT_DIR = os.getenv("OUTPUT_DIR", "/data/output")
        self.SITE = os.getenv("SITE", "ieeg").lower()
        # How repeated imports of one mark are collapsed. exact keeps every
        # copy that differs, so nothing is lost; first, last and widest each
        # pick one copy and can drop channels the others named.
        self.DUPLICATE_RULE = os.getenv("DUPLICATE_RULE", "exact").lower()
        self.JSON_BODIES = os.getenv("JSON_BODIES", "false").lower() == "true"
        # Prepended to every channel id. Ids must be unique across a workflow
        # run or the branch merge fails on a filename collision.
        self.SOURCE_PREFIX = os.getenv("SOURCE_PREFIX", "")
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)
