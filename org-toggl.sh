#!/bin/sh
#
# Load an org mode file, export it to JSON structure, parse the JSON structure
# and upload time info to Toggl.
#
# Usage: org-toggl.sh <config file> <org_file> [<extra_emacs_load_file>, ...]
#
# See README for more info. This will probably break if your paths contain
# spaces.
set -e

config_file=$1
shift
org_file=$1
shift

THIS_PATH=$( cd $(dirname "$0") ; pwd -P )

# Export json
emacs -batch -l $THIS_PATH/"org-export-json.el" -f "cli-org-export-json" "$org_file" $@

# Process json and upload to toggl
org_json_file=$org_file.json
python $THIS_PATH/org-toggl.py "$config_file" "$org_json_file"
