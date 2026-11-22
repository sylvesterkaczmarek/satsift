"""Version of the maintained Python case-statistics implementation.

Matching, covered exposure, uncertainty, ranking or gate semantics require a
new version and a new reviewed fingerprint in evaluation_version_test.py.
Retain earlier version pins and historical artefacts. This identifier describes
case statistics and event construction, not training or browser detector maths.
It is emitted only in newly produced reports; frozen reports are not rewritten.
"""

EVALUATION_VERSION = 'case-statistics-v3'
