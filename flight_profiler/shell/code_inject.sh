#!/bin/sh

# Default values
IS_DARWIN=false
SHARED_LIB_SUFFIX="so"
DEBUGGER=$(which gdb)
DEBUG_MODE=false

# Check for debug flag
if [ "$1" = "--debug" ]; then
    DEBUG_MODE=true
    shift
elif [ "$5" = "--debug" ]; then
    DEBUG_MODE=true
    set -- "$1" "$2" "$3" "$4"
fi

if [ "$(uname -s)" = "Darwin" ]; then
    IS_DARWIN=true
    SHARED_LIB_SUFFIX="dylib"
    DEBUGGER=lldb
fi

client_py_pid=$1
pid=$2
result_file=$3
port_found=$4

shell_bin_dir="$(dirname "$0")"

if [[ "$client_py_pid" = "" || "$pid" = "" || "$result_file" = "" ]]; then
	echo "usage: $0 [--debug] <client_py_pid> <target_py_pid> <tmp_file> <port>"
	exit 1
fi

# Debug print function that only prints in debug mode
debug_print() {
    if [ "$DEBUG_MODE" = true ]; then
        echo "$1"
    fi
}

py_bin_path=$(sh $shell_bin_dir/resolve_bin_path.sh $pid)

if [ -z "$py_bin_path" ]; then
    debug_print "Target process_id $pid not exists!"
	exit 1
fi

client_py_bin_path=$(sh $shell_bin_dir/resolve_bin_path.sh $client_py_pid)

if [ -z "$client_py_bin_path" ]; then
    debug_print "client_py_pid $client_py_pid not exists"
    exit 1
fi

if [ "$py_bin_path" != "$client_py_bin_path" ]; then
    debug_print "target process does not use same python, profile client use $client_py_bin_path but target process use $py_bin_path"
    exit 1
fi

nm_addr_hex=$(sh $shell_bin_dir/resolve_symbol.sh $pid take_gil)
if [ -z "$nm_addr_hex" ]; then
	debug_print "invalid python process $pid, test find take_gil function failed"
    exit 1
fi
nm_addr=$(printf "%d" 0x${nm_addr_hex})
debug_print "test python take_gil nm addr: 0x${nm_addr_hex} (${nm_addr})"

cd "$(dirname "$0")/.."
parentdir="$(pwd)"

dylib="$parentdir/lib/flight_profiler_agent.${SHARED_LIB_SUFFIX}"
[ \! -e "$dylib" ] && \
	echo "flight_profiler_agent.${SHARED_LIB_SUFFIX} not found." >&2 && \
	echo "compile the library first." >&2 && exit 1

pycode="$parentdir/profiler_agent.py"

if [ "$IS_DARWIN" = "false" ]; then
    tmp_file=$(mktemp -p /tmp "$(basename $0).XXXXXX")
else
    tmp_file=$(mktemp "/tmp/$(basename $0).XXXXXX")
fi
debug_print "use ${DEBUGGER} result temp file: $tmp_file"

debug_print "${DEBUGGER} attached to pid:$pid, bin:$py_bin_path, lib path:$dylib"


if [ "$IS_DARWIN" = "false" ]; then
	debug_print "using gdb:$DEBUGGER"
	gdb_version=`$DEBUGGER --version|grep "GNU gdb" |grep  -Eo "[0-9]+\.[0-9\.a-zA-Z\-]+"|head -n 1 |grep -Eo "^[0-9]+"`
	gdb_logging_set_prefix="set logging enabled"
	if [ $gdb_version -le 8 ]; then
		gdb_logging_set_prefix="set logging"
	fi
	{
		echo "set auto-solib-add off"
		echo "attach ${pid}"
		echo "sharedlibrary libdl"
		echo "$gdb_logging_set_prefix off"
		echo "set \$m = (void*)dlopen(\"$dylib\", 9)"
		echo "set \$take_gil_addr = (void *)take_gil"
		echo "set \$f = (int (*)(char *, int, unsigned long))dlsym(\$m, \"inject\")"
		echo "set \$used_port = \$f(\"$pycode\", $port_found, (unsigned long)\$take_gil_addr - $nm_addr)"
		echo "set logging overwrite on"
		echo "set logging file $tmp_file"
		echo "$gdb_logging_set_prefix on"
		echo "print \$used_port"
		echo "$gdb_logging_set_prefix off"
		echo "set confirm off"
		echo "quit"
	} | $DEBUGGER
else
	{
		echo "process attach -p ${pid}"
		echo "expr void (* \$take_gil_addr)(void*) =(void (*)(void*))take_gil"
		echo "expr void* \$handle = (void*)dlopen(\"$dylib\", 9)"
		echo "expr int (* \$func)(char*, int, unsigned long) = (int (*)(char*, int, unsigned long))dlsym(\$handle, \"inject\")"
		echo "expr int \$used_port = \$func(\"$pycode\", $port_found, (unsigned long)\$take_gil_addr - $nm_addr)"
		echo "print \$used_port"
		echo "c"
		echo "detach"
		echo "quit"
	} | $DEBUGGER $py_bin_path
fi

exit_code=$?

if [ -n "$result_file" ]; then
  if [ "$IS_DARWIN" = "false" ]; then
	    cat $tmp_file| grep -Eo "= [0-9]+" |grep -Eo "[0-9]+" > $result_file
  else
      echo $port_found  > $result_file
  fi
fi

debug_print "Exit code: $exit_code"
exit $exit_code
