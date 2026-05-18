#!/bin/sh
pid=$1
symbol=$2


[ "$pid" = "" ] && \
	exit 1

if [ -z "$symbol" ]; then
    exit 1
fi

shell_bin_dir="$(dirname "$0")"
symbol_bin_path=$(sh $shell_bin_dir/resolve_bin_path.sh $pid)

# On macOS framework Pythons (Homebrew, python.org installer), the running
# executable is the tiny `Python.app/Contents/MacOS/Python` launcher with no
# Python symbols. The actual symbols live in the sibling framework dylib at
# `Python.framework/Versions/X.Y/Python`. Fall back to that for nm lookup,
# while keeping resolve_bin_path.sh returning the real running executable
# (lldb needs the launcher for `process attach -p` to succeed).
case "$symbol_bin_path" in
    */Python.framework/Versions/*/Resources/Python.app/Contents/MacOS/Python)
        framework_dylib=$(echo "$symbol_bin_path" | sed -E 's|/Resources/Python.app/Contents/MacOS/Python$||')/Python
        if [ -f "$framework_dylib" ]; then
            symbol_bin_path="$framework_dylib"
        fi
        ;;
esac

line=$(nm $symbol_bin_path| grep $symbol| head -n 1)
if [ -z "$line" ]; then
    exit 1
fi
echo $line|awk -F ' ' '{print $1}'
