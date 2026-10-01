#!/bin/sh
# Run a Homebrew LilyPond python script under a Python whose pyexpat works.
#
# Homebrew's python@3.14 bottle ships pyexpat linked against /usr/lib/libexpat.1.dylib
# (macOS's system expat), but built against a newer expat's headers. The system
# library has no XML_SetAllocTrackerActivationThreshold, so `import pyexpat` dies:
#
#   ImportError: dlopen(.../pyexpat.cpython-314-darwin.so): Symbol not found:
#     _XML_SetAllocTrackerActivationThreshold
#     Expected in: /usr/lib/libexpat.1.dylib
#
# That kills every XML-reading LilyPond tool -- musicxml2ly above all. The scripts
# themselves are pure Python and hardcode LilyPond's own module path, so any
# working Python 3 runs them unchanged.
#
# Install: copy (or symlink) this to a directory that precedes /opt/homebrew/bin
# on PATH, named after the tool it should shadow:
#
#   install -m 755 musicxml2ly-shim.sh ~/.local/bin/musicxml2ly
#
# It dispatches on its own basename, so the same file also fixes abc2ly, midi2ly,
# convert-ly, lilypond-book and etf2ly if you name copies after them.
#
# Remove it once Homebrew ships a python@3.14 whose pyexpat links correctly:
#   /opt/homebrew/opt/python@3.14/libexec/bin/python -c 'import pyexpat'
set -eu

tool=$(basename "$0")
real="/opt/homebrew/bin/$tool"

if [ ! -f "$real" ]; then
    echo "$tool: $real not found — is LilyPond installed via Homebrew?" >&2
    exit 127
fi

# Try the interpreter the script was installed with FIRST, so this shim becomes a
# transparent passthrough the moment Homebrew ships a working pyexpat -- it
# retires itself instead of pinning you to an older Python forever. Apple's
# python3 is the fallback: always present, and LilyPond 2.26 supports 3.8+.
shebang=$(sed -n '1s/^#![[:space:]]*//p' "$real" | awk '{print $1}')
for py in "$shebang" /usr/bin/python3 /opt/homebrew/bin/python3 python3; do
    [ -n "$py" ] || continue
    command -v "$py" >/dev/null 2>&1 || continue
    if "$py" -c 'import pyexpat' >/dev/null 2>&1; then
        exec "$py" "$real" "$@"
    fi
done

echo "$tool: found no python3 with a working pyexpat; tried /usr/bin/python3," \
     "/opt/homebrew/bin/python3, python3" >&2
exit 1
