"""Atlas — a hands-free voice bridge to the Cursor IDE agent.

Pipeline:  microphone -> transcribe -> Claude (format) -> Cursor -> Claude (summarize) -> macOS `say`.
"""

__version__ = "0.1.0"
