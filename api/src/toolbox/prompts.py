"""System prompts for LLM-backed tools.

Each prompt is rigid and enforces exact output format.
Keep prompts SHORT — inputs are truncated to fit small context windows.
"""

DESCRIBE = (
    "Describe this image concisely. Report: "
    "1) Page structure (layout, sections, navigation) "
    "2) Key content (text, data, status indicators) "
    "3) State (errors, empty areas, loading, auth walls). "
    "Be specific about what IS and ISN'T showing. Plain text, no markdown."
)

SUMMARIZE = (
    "Condense to approximately {words} words. "
    "Preserve: version numbers, commands, URLs, config syntax, and technical specifics. "
    "Drop: filler, opinions, repetition. "
    "Return summary only. No preamble."
)

EXTRACT = (
    "Extract data from the text below. Return ONLY valid JSON matching this schema:\n\n"
    "{schema}\n\n"
    "Rules:\n"
    "- Missing string: null. Missing list: []. Missing number: null.\n"
    "- No explanation, no markdown fences, just raw JSON.\n"
    "- Output must be valid parseable JSON."
)
