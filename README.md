# org-toggl-py

Create [Toggl time tracking](https://www.toggl.com) entries from Emacs
org-mode CLOCK entries, by assigning `TOGGL_PID` and `TOGGL_TID` properties to
your org headings.

See below for how to use the `org-toggl.sh` script. The command runs Emacs from
the CLI and exports your org data as a JSON file to `$original_path.org.json`. It
then processes the JSON in Python and uploads the relevant data to the Toggl
API. I've implemented it like this beacuse it's easy to develop and automate / run
as a cron job.


## Installation

- `pip install -r requirements.txt` to install the Python dependencies.

- Emacs should have the `json.el` library installed. This is part of GNU Emacs
  since 23.1 (2008).


## Usage

- The main command is `org_toggl.sh <config_path> <org_file_path> [<extra_emacs_files_to_load> ...]`.

  - `config_path`: Path to an org-toggl configuration file, described below.

  - `org_file_path`: The org file to be processed for Toggl entries.

  - `extra_emacs_files_to_load`: Before exporting the org file, optionally load
    these files in Emacs, in the given order. You can use this to eg. load some
    custom org-mode setup so your files are exported with the correct keywords.

- Toggl takes priority over org-mode: a CLOCK entry is not pushed to Toggl if
  there is already a Toggl entry that *starts* within the CLOCK time period.

  - Except: CLOCK entries that start in the same minute that a Toggl entry ends
    *are* allowed, because that can naturally occur in org-mode.


## Configuration

```
[org-toggl-py]

# Your Toggl API token
toggl_api_token = <token>

# Your Toggl workspace ID
toggl_wsid = <id>

# CLOCK entries that have a closed time older than this are skipped
skip_clocks_older_than_days = 7
```


## Org-mode headline properties

- `TOGGL_PID` - If this value is a Toggl project ID, the entry will be assigned
  to that project. If this value is `t`, the entry will be pushed to Toggl
  without a project. CLOCK entries are only uploaded if `TOGGL_PID` has one of
  these values.

  - Property values are inherited: you can set this on a parent
    headline representing a project on Toggl, and all child headlines will have
    their CLOCK values uploaded.

- `TOGGL_TID` - Task ID support is partially implemented, I haven't tested it
  yet.

- `TOGGL_IGNORE` - If a parent headline has a `TOGGL_PID` or `TOGGL_TID` set,
  you can assign `TOGGL_IGNORE` to any value to ignore processing for a
  headline and its children.


## JSON

The `org-export-json` function in `org-export-json.el` can be used to export an
org-mode buffer from Emacs to a JSON file. This is adapted from a post on the
org-mode mailing list by Brett Viren:
https://lists.gnu.org/archive/html/emacs-orgmode/2014-01/msg00338.html.

Run the function `org-export-json` to export the current org-mode buffer to
`$file.org.json`. You can then run `org-toggl.py <config_path> <json_path>`
manually.
