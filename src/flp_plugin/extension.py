"""Inkscape extension entry point."""

from __future__ import annotations

import inkex

from .core import FLPConfig, FLPExporter


class FLPEffect(inkex.EffectExtension):
    """Base plugin effect for Inkscape."""

    def add_arguments(self, pars):
        pars.add_argument("--output", type=str, default="output.flp")
        pars.add_argument("--mode", type=str, default="export")

    def effect(self):
        config = FLPConfig(output_path=self.options.output, mode=self.options.mode)
        exporter = FLPExporter(source="current-document")
        result = exporter.export()

        inkex.utils.debug(f"FLP plugin executed: {result}")
        self.msg(f"FLP plugin ready. Output: {config.output_path} ({config.mode})")


if __name__ == "__main__":
    FLPEffect().run()
