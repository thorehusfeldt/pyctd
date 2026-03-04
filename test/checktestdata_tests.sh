#!/bin/bash
set -euo pipefail
shopt -s nullglob
cd "$(dirname "$0")"

checksucc() {
    if python3 ../checktestdata/ "$prog" < "$data" > /dev/null 2>&1; then
        status=0
    else
        status=$?
    fi

    if [[ $status -ne 0 ]]; then
        echo "ERROR: Expected exit code 0 but got $status"
        echo "  Program: $prog"
        echo "  Data:    $data"
        exit 1
    fi
}

checkfail() {
    if python3 ../checktestdata/ "$prog" < "$data" > /dev/null 2>&1; then
        status=0
    else
        status=$?
    fi

    if [[ $status -eq 0 ]]; then
        echo "ERROR: Expected exit code != 0 but got $status"
        echo "  Program: $prog"
        echo "  Data:    $data"
        exit 1
    fi
}

for prog in checktestdata/test_*_prog.in; do
    base="${prog%_prog.*}"
    echo "${base}"

    # Successful cases
    for data in "${base}"_data.in*; do
        checksucc
    done

    # Expected failure cases (.err data)
    for data in "${base}"_data.err*; do
        checkfail
    done

    # Program error cases
    data="${base}_data.in"
    for prog in "${base}"_prog.err*; do
        checkfail
    done
done
