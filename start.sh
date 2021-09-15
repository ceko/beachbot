#!/usr/bin/env bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
export PYTHONPATH="${DIR}/src/:$PYTHONPATH"
python -c "from beach_bot import api; api.configure(); api.start_bot()"