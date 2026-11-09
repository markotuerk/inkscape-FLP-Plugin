"""Core functionality for the FLP plugin."""

from __future__ import annotations


class FLPExporter:
    """Placeholder exporter for FLP-based project assets."""

    def __init__(self, source: str | None = None):
        self.source = source

    def export(self) -> dict:
        """Return a minimal export payload for the current document."""
        return {
            "source": self.source,
            "status": "ready",
            "format": "flp",
        }


class FLPConfig:
    """Basic configuration container for the plugin."""

    def __init__(self, output_path: str = "output.flp", mode: str = "export"):
        self.output_path = output_path
        self.mode = mode
