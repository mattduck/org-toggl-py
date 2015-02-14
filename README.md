# org-toggl-py

Create [Toggl time tracking](https://www.toggl.com) entries from Emacs 
org-mode CLOCK entries.

I've implemented this (mostly) in Python because it's easy to develop / run as a
cron job. You first export the full results of org-elements-parse-buffer from
Emacs as a JSON file, then the Python script walks through the JSON tree and
sends the relevant data to the Toggl API.


# Usage

`python org-toggl.py <path_to_config>`. The configuration file is a required
argument.


## Configration

```
    [org-toggl-py]

    # Your Toggl API token
    toggl_api_token = <token>

    # Your Toggl workspace ID
    toggl_wsid = <id>

    # Path to your org.json file
    org_json_path = <path>

    # CLOCK entries that have a closed time older than this are skipped
    skip_clocks_older_than_days = 7
```


## Org-mode headline properties

- *TOGGL_PID* - Toggl project ID. Currently CLOCK entries are only uploaded if
  they have a parent headline with a project ID.

- *TOGGL_TID* support is partially implemented, I haven't tested it yet.


## JSON

The `org-export-json` function in org-export-json.el can be used to export an
org-mode buffer from Emacs to a JSON file. This is adapted from a post on the
org-mode mailing list by Brett Viren:
https://lists.gnu.org/archive/html/emacs-orgmode/2014-01/msg00338.html. 

Run the function `org-export-json` to export the current org-mode buffer to
`$file.org.json`, then you can run `org-toggl.py` on the JSON file.
