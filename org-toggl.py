#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import json
from datetime import datetime, timedelta
from configparser import ConfigParser
import logging
import urllib

import requests
from tzlocal import get_localzone


CONFIG = None

# Toggl requires ISO-conforming timestamps that include a timezone, but
# datetime doesn't include any concrete tzinfo classes. We use
# tzlocal to get the system local timezone, assuming that this is the timezone
# used by (1) your Org-mode timestamps and (2) your Toggl profile.
#
# NOTE: tzlocal uses pytz, which (for timezones with daylight saving
# transitions) doesn't work if you pass the timezone as a `tzinfo` kwarg to
# `datetime()`. You must use the pytz `localize()` method instead.
TIMEZONE = get_localzone()

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)
h = logging.StreamHandler(sys.stdout)
h.setLevel(logging.DEBUG)
fo = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
h.setFormatter(fo)
LOG.addHandler(h)


def setup_config(config_obj, config_path):
    config_obj.read(config_path)
    assert config_obj.has_option('org-toggl-py', 'toggl_api_token')
    assert config_obj.has_option('org-toggl-py', 'toggl_wsid')
    assert config_obj.has_option('org-toggl-py', 'skip_clocks_older_than_days')

    days = int(config_obj.get('org-toggl-py', 'skip_clocks_older_than_days'))
    if days < 1:
        days = 30
    config_obj.set('org-toggl-py', 'skip_clocks_older_than_days', str(days))
    return None


class OrgNode(object):

    def __init__(self, org_json, parent_node=None):
        """
        Expose a more convenient API for accessing a JSON-exported org
        node.

        In Emacs, a node is represented as a single list of [type, properties,
        *content], where content extends the list to an arbitrary length.
        """
        self.org_type = org_json[0]
        self.properties = org_json[1]
        self.parent = parent_node

        # Build recursive node tree
        content = []
        if len(org_json) > 2:
            contents_sublist = org_json[2:]
            for child_json in contents_sublist:
                childIsNode = (type(child_json) == list)
                if childIsNode:
                    content.append(OrgNode(child_json, parent_node=self))
                else:
                    # The object is probably a string
                    content.append(child_json)
        self.content = content
        # Used for log
        self.clocks_skipped = 0
        return

    def get_useable_toggl_entries(
            self, given_node=None, results_list=None, log=True):
        """
        Return list of TogglTimeEntry objects, each created from a valid
        CLOCK entry under this node.
        """
        if not given_node:
            given_node = self
        if results_list is None:
            results_list = []

        if log:
            LOG.debug('Searching node for useable CLOCK entries...')
            self.clocks_skipped = 0

        for thing in given_node.content:

            # "content" doesn't only contain nodes - I know it can contain raw
            # strings, there might be other data.
            if type(thing) != OrgNode:
                continue
            node = thing

            # User flag
            if node.org_type == 'headline' and node.properties.get('TOGGL_IGNORE'):
                continue

            # Recursive
            if node.content:
                self.get_useable_toggl_entries(
                    given_node=node, results_list=results_list, log=False)

            if node.org_type != 'clock':
                continue
            clock = node

            # Ignore open clocks, they will be pushed when closed
            if clock.properties['status'] != 'closed':
                self.clocks_skipped += 1
                continue

            # Ignore entries of 1 minute or less - these are likely
            # insignificant, and they add complexity to handling existing
            # Toggl entries.
            if clock.properties['duration'] in ("0:00", "0:01"):
                continue

            # Some nodes exist as property values and weren't parsed during
            # __init__.
            date = OrgNode(clock.properties['value'])
            end_datetime = datetime(
                date.properties['year-end'],
                date.properties['month-end'],
                date.properties['day-end'],
                date.properties['hour-end'],
                date.properties['minute-end'],
            )
            end_datetime = TIMEZONE.localize(end_datetime)

            # Skip clocks that the user has decided are too old, to limit API
            # requests.
            days = int(CONFIG.get(
                'org-toggl-py', 'skip_clocks_older_than_days'))
            now = TIMEZONE.localize(datetime.now())
            if end_datetime < now - timedelta(days=days):
                self.clocks_skipped += 1
                continue

            # Get CLOCK data and make Toggl object
            headlines = []
            toggl_pid = ''
            toggl_tid = ''
            parent = clock.parent
            while parent:
                if parent.org_type == 'headline':
                    this_headline = parent.properties['raw-value']
                    if this_headline.lower() != "archive":
                        headlines.append(this_headline)
                    if ('TOGGL_TID' in parent.properties) and (not toggl_tid):
                        toggl_tid = parent.properties['TOGGL_TID']

                    if ('TOGGL_PID' in parent.properties) and (not toggl_pid):
                        toggl_pid = parent.properties['TOGGL_PID']
                        # Once you hit the PID, there's no need to share
                        # further parent info.
                        break

                # This will eventually hit the root node, which has no parents
                parent = parent.parent

            # For now, only push items that have a toggl PID - so setting
            # TOGGL_PID in org acts as whitelisting, rather than setting
            # TOGGL_IGNORE to blacklist.
            if not toggl_pid:
                self.clocks_skipped += 1
                continue

            start_datetime = datetime(
                date.properties['year-start'],
                date.properties['month-start'],
                date.properties['day-start'],
                date.properties['hour-start'],
                date.properties['minute-start'],
            )
            start_datetime = TIMEZONE.localize(start_datetime)

            toggl_entry = TogglTimeEntry(
                raw_value=date.properties['raw-value'],
                pid=toggl_pid,
                tid=toggl_tid,
                description=' << '.join(headlines),
                start_datetime=start_datetime,
                end_datetime=end_datetime,
            )
            results_list.append(toggl_entry)

        if log:
            LOG.debug(
                '...search done. %d CLOCK entries were found, %d skipped',
                len(results_list), self.clocks_skipped)
        return results_list


class TogglTimeEntry(object):

    def __init__(self, raw_value, pid, tid, description, start_datetime,
                 end_datetime):
        self.raw_value = raw_value
        self.pid = pid
        self.tid = tid
        self.description = description
        self.start_datetime = start_datetime
        self.end_datetime = end_datetime

    def params_for_create_request(self):
        params = {
            'description': self.description,
            'start': self.start_datetime.isoformat(),
            'stop': self.end_datetime.isoformat(),
        }
        if self.tid:
            params['tid'] = self.tid
        if self.pid and self.pid not in ("t", True, "True", "true"):
            params['pid'] = self.pid

        delta = self.end_datetime - self.start_datetime
        params['duration'] = delta.total_seconds()
        LOG.debug('Entry params for create request: %s' % params)
        return params

    def params_for_get_request(self):
        # Allow a one-minute overlap in Toggl entries, so that if an entry
        # starts in the same minute that another one ends, the new entry is
        # still uploaded.
        start = self.start_datetime
        end = self.end_datetime - timedelta(minutes=1)
        return {
            'start_date': start.isoformat(),
            'end_date': end.isoformat(),
        }


class TogglServerError(Exception):
    pass


class TogglTimeEntryAPI(object):

    BASE_URL = 'https://www.toggl.com/api/v8/'

    def __init__(self, wsid=None, api_token=None):
        self.api_token = api_token or CONFIG.get(
            'org-toggl-py', 'toggl_api_token')
        self.wsid = wsid or CONFIG.get('org-toggl-py', 'toggl_wsid')

    def _raise_if_error(self, r, resp_data):
        if r.status_code != 200:
            msg = '%d. ' % r.status_code
            if 'error' in resp_data:
                msg += '. '.join([resp_data['error']['message'],
                                  resp_data['error']['tip']])
            else:
                msg += r.reason
            LOG.error(msg)
            raise TogglServerError(msg)

    def post(self, url, payload):
        headers = {'content-type': 'application/json'}
        auth = (self.api_token, 'api_token')
        payload.update({
            'wid': self.wsid,
            'created_with': 'org-toggl-py',
        })
        payload = json.dumps({'time_entry': payload})
        LOG.debug('Sending POST request: %s', url)
        r = requests.post(url, data=payload, headers=headers, auth=auth)
        resp_data = r.json()
        self._raise_if_error(r, resp_data)
        return resp_data

    def get(self, url, params):
        headers = {'content-type': 'application/json'}
        auth = (self.api_token, 'api_token')
        url = url + '?' + urllib.parse.urlencode(params)
        LOG.debug('Sending GET request: %s', url)
        r = requests.get(url, headers=headers, auth=auth)
        resp_data = r.json()
        self._raise_if_error(r, resp_data)
        return resp_data

    def create_time_entry(self, time_entry):
        LOG.info('Attempting to create Toggl entry: %s', time_entry.raw_value)
        existing_entries = self.get_time_entries_in_range(time_entry)
        if existing_entries:
            LOG.info("Won't create Toggl time entry, entry already "
                     "exists in this range")
            return
        url = self.BASE_URL + 'time_entries'
        return self.post(url, time_entry.params_for_create_request())

    def get_time_entries_in_range(self, time_entry):
        url = self.BASE_URL + 'time_entries'
        return self.get(url, time_entry.params_for_get_request())


def main(argv):
    global CONFIG

    CONFIG = ConfigParser()
    config_path = argv[0]
    setup_config(CONFIG, config_path)

    # For now org-toggl-py handles one org JSON file
    org_json_file = os.path.abspath(argv[1])

    LOG.info('Processing org JSON file: %s ...', org_json_file)

    org_json = json.loads(open(org_json_file).read())
    document = OrgNode(org_json)
    org_toggl_entries = document.get_useable_toggl_entries()
    toggl_api = TogglTimeEntryAPI()
    for entry in org_toggl_entries:
        toggl_api.create_time_entry(entry)

    LOG.info('...File processed: %s', org_json_file)
    return


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
