# Copyright 2021 The Pigweed Authors
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
"""Banned words presubmit check."""

import collections
from pathlib import Path
import re
from typing import Dict, List

from . import presubmit

# List borrowed from Android:
# https://source.android.com/setup/contribute/respectful-code
# banned-words: disable
BANNED_WORDS = [
    r'master',
    r'slave',
    r'(white|gr[ae]y|black)\s*(list|hat)',
    r'craz(y|ie)',
    r'insane',
    r'crip+led?',
    r'sanity',
    r'sane',
    r'dummy',
    r'grandfather',
    r's?he',
    r'his',
    r'her',
    r'm[ae]n[-\s]*in[-\s]*the[-\s]*middle',
    r'mitm',
]
# banned-words: enable

# Test: master  # banned-words: ignore
# Test: master


def _process_banned_words(*words):
    """Turn banned-words list into one big regex with common inflections."""

    if not words:
        words = tuple(BANNED_WORDS)

    all_words = []
    for entry in words:
        if isinstance(entry, str):
            all_words.append(entry)
        elif isinstance(entry, (list, tuple)):
            all_words.extend(entry)
        all_words.extend(x for x in words)
    all_words = tuple(all_words)

    # Confirm each individual word compiles as a valid regex.
    for word in all_words:
        _ = re.compile(word)

    return re.compile(
        r"\b({})(\b|e?[sd]\b)".format('|'.join(all_words)),
        re.IGNORECASE,
    )


BANNED_WORDS_REGEX = _process_banned_words()

# If seen, ignore this line and the next.
_IGNORE = 'banned-words: ignore'

# Ignore a whole section. Please do not change the order of these lines.
_DISABLE = 'banned-words: disable'
_ENABLE = 'banned-words: enable'


def banned_words(
    ctx: presubmit.PresubmitContext,
    words_regex=BANNED_WORDS_REGEX,
):
    """Presubmit check that ensures files do not contain banned words."""

    Match = collections.namedtuple('Match', 'line word')
    found_words: Dict[Path, List[Match]] = {}

    for path in ctx.paths:
        try:
            with open(path, 'r') as ins:
                enabled = True
                prev = ''
                for i, line in enumerate(ins, start=1):
                    if _DISABLE in line:
                        enabled = False
                    if _ENABLE in line:
                        enabled = True

                    # If we see the ignore line on this or the previous line we
                    # ignore any bad words on this line.
                    ignored = _IGNORE in prev or _IGNORE in line

                    if enabled and not ignored:
                        match = words_regex.search(line)

                        if match:
                            found_words.setdefault(path, [])
                            found_words[path].append(Match(i, match.group(0)))

                    # Not using 'continue' so this line always executes.
                    prev = line

        except UnicodeDecodeError:
            # File is not text, like a gif.
            pass

    for path, matches in found_words.items():
        print('=' * 40)
        print(path)
        for match in matches:
            print(f'Found banned word "{match.word}" on line {match.line}')

    if found_words:
        raise presubmit.PresubmitFailure


def banned_words_checker(*words):
    """Create banned words checker for the given list of banned words."""

    regex = _process_banned_words(*words)

    def banned_words(  # pylint: disable=redefined-outer-name
        ctx: presubmit.PresubmitContext):
        globals()['banned_words'](ctx, regex)

    return banned_words
