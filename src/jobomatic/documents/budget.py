"""The skim budget in one place: the limits ``documents.skim`` checks and the schema quotes.

Kept apart from both so the field descriptions a model reads and the checks that refuse its
content cannot say different numbers. Words unless the name says otherwise.
"""

TAGLINE_WORDS = 14
TAGLINE_CHARS = 100  # one centered line at 10pt
SUMMARY_WORDS = 60  # three lines
SKILL_LINES = 7
SKILL_LINE_WORDS = 28
JOB_BULLETS = 4
BULLET_WORDS = 35
PROJECTS = 3  # the Selected Projects section: at most this many projects ...
PROJECT_BULLETS = 2  # ... of at most this many bullets each
PROJECT_SUBTITLE_ITEMS = 4  # stack items shown beside a project's name ...
PROJECT_SUBTITLE_CHARS = (
    45  # ... as many as fit this many characters, so the link stays on the line
)

HOOK_WORDS = 40
HOOK_SENTENCES = 2
BRING_ITEMS = 4
BRING_LABEL_CHARS = 40
BRING_BODY_WORDS = 20
HIGHLIGHT_LABEL_WORDS = 8
HIGHLIGHT_BODY_WORDS = 30
CLOSING_WORDS = 35
CLOSING_SENTENCES = 2
LETTER_WORDS = 200  # the whole body: what fits in a glance at one page
