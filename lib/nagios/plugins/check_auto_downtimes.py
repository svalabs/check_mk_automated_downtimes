#!/usr/bin/env python3

# +------------------------------------------------------------+
# |                                                            |
# |             | |             | |            | |             |
# |          ___| |__   ___  ___| | ___ __ ___ | | __          |
# |         / __| '_ \ / _ \/ __| |/ / '_ ` _ \| |/ /          |
# |        | (__| | | |  __/ (__|   <| | | | | |   <           |
# |         \___|_| |_|\___|\___|_|\_\_| |_| |_|_|\_\          |
# |                                   custom code by SVA       |
# |                                                            |
# +------------------------------------------------------------+
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   Copyright (C) 2024  SVA System Vertrieb Alexander GmbH
#                       by michael.hoess@sva.de + colleagues


import datetime
import hashlib
import traceback
import sys
import time

from typing import Iterable, Optional, Tuple, Literal

from auto_downtimes_common import (
    dbg,
    try_strip_fqdn,
    Downtime,
    NAGRES_OK,
    NAGRES_CRASH,
    parse_args,
    show_config_dump,
    Env,
)
from auto_downtimes_lqapi import LqAPI
from auto_downtimes_restapi import RestAPI
from auto_downtimes_cache import LocalState, LocalStateCache, InfoCache

VERSION = "2.0.2-20241308-172322"
HASH_ID = "check_auto_downtimes"

#
#
#

env = Env()

#
# Targetlist building
#


class TargetListBuilder:

    def __init__(
        self,
        matches_case_insensitive: bool,
        strip_fqdn_when_useful: bool,
        hostname_boundary_match: bool,
        # rest_api: RestAPI,
        # lq_api: LqAPI,
        cache: InfoCache,
    ):

        self._case_insensitive = matches_case_insensitive
        self._allow_fqdn_strip = strip_fqdn_when_useful
        self._hostname_boundary_match = hostname_boundary_match

        self._cache = cache
        # self._rest_api = rest_api Force crash if still used here
        # self._lq_api = lq_api
        self._result: Tuple[Tuple[str]] = tuple()

        # self._def_api = self._rest_api
        self._def_api = self._cache

    def add(self, target: Tuple[str]):
        """Used for manual specified deps"""
        if not target[2]:
            for ch in self._def_api.find_hosts(
                name_regex=target[1],
                case_insensitive=self._case_insensitive,
            ):
                self._result += ((target[0], ch, ""),)

        else:
            for ch in self._def_api.find_services(
                name_regex=target[2],
                host_name_regex=target[1],
                optional_identifier=None,
                case_insensitive=self._case_insensitive,
                boundary_match=False,
            ):
                self._result += ((target[0], ch[0], ch[1]),)

            # self._result += (target,)

    def get(self) -> Tuple[Tuple[str]]:
        return self._result

    def add_childs_from_parent(self, parent_host: str) -> None:
        for ch in self._def_api.find_childs_of_host(
            host_name=parent_host,
            recursive=True,
            case_insensitive=self._case_insensitive,
        ):

            self._result += ((f"Auto-detected child host {ch}", ch, ""),)

    def add_dependant_services(self, host_name: str, optional_identifier: str):
        hns = host_name if not self._allow_fqdn_strip else try_strip_fqdn(host_name)
        for hn, svc in self._def_api.find_services(
            hns,
            optional_identifier,
            self._case_insensitive,
            self._hostname_boundary_match,
        ):
            self._result += (("Auto-detected dependent service", hn, svc),)

    def add_dependant_services_on_parent(
        self, host_name: str, optional_identifier: str
    ):
        # TODO: Obsolete, modeis no longer exposed in UI?
        """Find parents of host_name, and there find serivce by name containing the host_name"""

        hns = host_name if not self._allow_fqdn_strip else try_strip_fqdn(host_name)
        parents = self._def_api.find_parents_of_host(host_name, self._case_insensitive)
        for parent in parents:
            pns = parent if not self._allow_fqdn_strip else try_strip_fqdn(parent)
            svc_res = self._def_api.find_services_by_host(pns, optional_identifier)
            for hns, svc_name in svc_res:
                self._result += (
                    ("Auto-detected dependent service on parent", host_name, svc_name),
                )

    def add_myself(self, host_name: str) -> None:
        self._result += (("Auto-detected host itself", host_name, ""),)

    def add_similar_host_names(self, host_name: str) -> None:
        hns = host_name if not self._allow_fqdn_strip else try_strip_fqdn(host_name)
        for h in self._def_api.find_similar_hosts(
            hns, self._case_insensitive, self._hostname_boundary_match
        ):
            self._result += (("Similar hostname", h, ""),)

    @staticmethod
    def safe_create(
        env: Env,
        maintenance_by: str,
        # rest_api: RestAPI,
        info_cache: InfoCache,
    ) -> Tuple[Tuple[str]]:

        dbg("Building targetlist...")

        tgt_list = TargetListBuilder(
            env.case_insensitive,
            strip_fqdn_when_useful=env.strip_fqdn,
            hostname_boundary_match=env.hostname_boundary_match,
            cache=info_cache,
        )
        dependency_detection = env.dependency_detection

        if dependency_detection == "fully_automated":
            if maintenance_by == "service":
                tgt_list.add_myself(env.my_host_name)

            dbg("Tgt-FullyAutomated: Adding similar hosts...")
            tgt_list.add_similar_host_names(env.my_host_name)
            dbg("Tgt-FullyAutomated: Add childs from parent...")
            tgt_list.add_childs_from_parent(env.my_host_name)
            dbg("Tgt-FullyAutomated: Add dependant services...")
            tgt_list.add_dependant_services(env.my_host_name, env.optional_identifier)
            if env.my_host_name == env.monitor_host and not env.optional_identifier:
                env.no_match_msg_tag = ""

        elif dependency_detection == "search_parent_child":
            tgt_list.add_myself(env.my_host_name)
            tgt_list.add_dependant_services(env.my_host_name, env.optional_identifier)
            tgt_list.add_childs_from_parent(env.my_host_name)
            tgt_list.add_dependant_services_on_parent(
                env.my_host_name, env.optional_identifier
            )

        elif dependency_detection == "search_child":
            tgt_list.add_myself(env.my_host_name)
            tgt_list.add_childs_from_parent(env.my_host_name)
            # tgt_list.add_dependant_services(env.my_host_name, env.optional_identifier)

        elif dependency_detection == "specify_targets":
            for m in env.manual_targets:
                if len(m) < 1 or len(m) > 3:
                    result_set_summary(
                        "! Bad manual target list, invalid num of arguments"
                    )
                    do_exit(NAGRES_CRASH)

                if len(m) == 2 and m[1]:
                    # Only hostname given
                    tgt_list.add(m[0], m[1], "")
                    continue

                if len(m) == 3 and m[1]:
                    # Hostname and optionally a service
                    tgt_list.add(m)
                    continue

                result_set_summary("! Bad manual target list, host always required")
                do_exit(NAGRES_CRASH)

                # for mm in m:
                #     if not mm:
                #         result_set_summary(
                #             "! Bad manual target list, no blanks allowed!"
                #         )  # This seemd to be ignored for a long time but did no work
                #         do_exit(NAGRES_CRASH)
                # tgt_list.add(m)

            if not tgt_list.get():
                result_set_summary(
                    "! Manual target list, but no targets defined or no targets found"
                )
                do_exit(NAGRES_CRASH)

        else:
            result_set_summary("! Invalid mode for --dependency_detection")
            do_exit(NAGRES_CRASH)

        dbg("Building targetlist Done")
        dbg(f"Target list updated to: {tgt_list.get()}")
        return tgt_list.get()


#
#
#
# Downtime-Support class
#
#
#
class Downtimes:

    def _create_hash() -> Tuple[str, str]:
        """returns a tuple. 2nd element is currently NOT used"""

        myid = f"{HASH_ID}{env.my_host_name}{env.my_svc_name}"
        res_my = hashlib.sha1(myid.encode("UTF-8")).hexdigest()

        return (res_my[:12], "")

    @staticmethod
    def get_hash():
        parts = Downtimes._create_hash()
        return f"{parts[0]}{parts[1]}"

    @staticmethod
    def find(
        dts: Iterable[Downtime],
        host_name: Optional[str] = None,
        svc_name: Optional[str] = None,
        comment_find: Optional[str] = None,
        dt_type: Literal["H", "S", "*"] = "*",
    ) -> Iterable[Downtime]:
        """
        return all matching downtimes. to get only service-downtime
        """
        res = []
        for dt in dts:
            if host_name and dt.host_name != host_name:
                continue
            if svc_name and dt.svc_name != svc_name:
                continue
            if comment_find and dt.comment.find(comment_find) < 0:
                continue
            if dt_type == "H" and dt.is_svc_dt:
                continue
            if dt_type == "S" and not dt.is_svc_dt:
                continue

            res.append(dt)

        return res

    @staticmethod
    def get_all(api: RestAPI) -> Iterable[Downtime]:
        return api.get_downtimes()

    @staticmethod
    def add(
        api: RestAPI,
        host_name: str,
        service: Optional[str],
        task_info: str,
        replace_existing: bool,
        curr_dts: Optional[Iterable[Downtime]] = None,
    ) -> None:
        """!!! SINGLE Add, should be not longer used !!!"""

        dbg(f"{task_info} (host / service: %s  - %s)" % (host_name, service))
        global default_downtime

        downtime_hash = Downtimes.get_hash(host_name, service)

        typ = "Svc" if service else "Host"
        comment = f"MAINT#{downtime_hash} {typ}-DT (set by rule '{env.my_svc_name}@{env.my_host_name}')"

        to_replace = []
        # Find exisiting downtimes with id
        if replace_existing:
            if curr_dts:
                dts = Downtimes.find(curr_dts, host_name, service, downtime_hash)
            else:
                dts = api.get_downtimes(host_name, service, downtime_hash)
            for dt in dts:
                id = dt.id
                to_replace.append(id)

        if len(to_replace):
            comment = comment + f" (Replacing {'/'.join(to_replace)})"

        start = datetime.datetime.now()
        end = start + datetime.timedelta(minutes=default_downtime)

        api.set_downtimes(comment, start, end, [(host_name,)])

        if len(to_replace):
            time.sleep(
                2
            )  # CMK will cancel old DT before new is place without delay?????
            if not api.delete_downtimes(to_replace):
                outcome = "FAILED!!"
            else:
                outcome = "OK"

            dbg(
                f"After adding dt for {downtime_hash}: del pre-existing dt {to_replace} {outcome}"
            )

    @staticmethod
    def add_all(
        api: RestAPI,
        targets: Iterable[Tuple[str, Optional[Iterable[str]]]],
        task_info: str,
        remove_existing: bool,
    ) -> None:
        """!!! SINGLE Add, should be not longer used !!!"""

        dbg(f"{task_info} (targets: {len(targets)})")

        downtime_hash = Downtimes.get_hash()

        comment = f"MAINT#{downtime_hash} $TYP$-DT (set by rule '{env.my_svc_name}@{env.my_host_name}')"

        start = datetime.datetime.now()
        end = start + datetime.timedelta(minutes=env.default_downtime)

        tgts = []
        for t in targets:
            if t[1] is None:
                tgts.append(t)
            else:
                tgts.append((t[0], [t[1]]))

        api.set_downtimes(comment, start, end, tgts)

        if remove_existing:
            time.sleep(
                2
            )  # CMK will cancel old DT before new is place without delay?????

            dbg(f"Removing all downtimes with my hash: {downtime_hash}")
            before = start - datetime.timedelta(seconds=5)
            if not api.delete_downtimes_by_keyword("MAINT#" + downtime_hash, before):
                outcome = "FAILED!!"
            else:
                outcome = "OK"

            dbg(f"After adding dt for {downtime_hash}: del pre-existing dt: {outcome}")

    @staticmethod
    def remove(api: RestAPI, host_name: str, svc_name: str, task_info):
        dbg(f"{task_info} (host / service: %s  - %s)" % (host_name, svc_name))

        downtime_hash = Downtimes.get_hash(host_name, svc_name)

        for dt in api.get_downtimes(host_name, svc_name, downtime_hash):
            id = dt.id
            dbg(f"Removing downtime {id}")
            api.delete_downtime(id)

    @staticmethod
    def remove_all_own(api: RestAPI):
        my_hash = Downtimes._create_hash()[0]
        dbg("Removing all downtimes with my hash: " + my_hash)

        api.delete_downtimes_by_keyword("MAINT#" + my_hash)


#
#
#
#


#
# Result-building Helper-functions {{{
#

result_summary = ""
result_details = []


def result_set_summary(msg: str) -> None:
    global result_summary
    dbg(f"Result-Summary: {msg}")
    result_summary = msg


def result_add_detail(*msg: str) -> None:
    global result_details
    for ln in msg:
        dbg(f"Result-Details: {ln}")
        result_details.append(ln)


def do_exit(exit_code: int) -> None:
    sys.stdout.write(f"{result_summary}\n")
    for ln in result_details:
        sys.stdout.write(f"{ln}\n")

    dbg(f"Exiting with {exit_code}")
    sys.exit(exit_code)


# }}}


def _ensure_tgt_list(rest_api: RestAPI, lost: LocalState, maintenance_by: str):

    if lost.tgt_list is None:
        cache = InfoCache(rest_api)
        if not cache.load():
            result_set_summary("Can't load cache, being updated elsewhere?")
            do_exit(0)

        tgt_list = TargetListBuilder.safe_create(
            env=env,
            maintenance_by=maintenance_by,
            # rest_api=rest_api,
            info_cache=cache,
        )
        lost.tgt_list = tgt_list
    else:
        dbg("Using cached target list...")
        tgt_list = lost.tgt_list

    return tgt_list


def _get_local_state(lq_api: LqAPI):
    glob_ft, glob_age, expired = InfoCache.get_cache_file_time()
    dbg(f"Global cache age: {glob_age}, expired: {expired}")

    lost, age = LocalStateCache.load(
        env.get_my_name(),
        glob_ft if not expired else None,
        env.default_downtime,
        env.cmd_line_hash,
    )
    if lost is None:
        lost = LocalState(None, None)

    if lost.normal_check_interval is None:
        normal_check_interval = lq_api.get_service_check_interval(
            env.my_host_name, env.my_svc_name
        )
        if not normal_check_interval:
            result_set_summary(
                "! Unexpected result. Can't find myself? Check configuration. See details."
            )
            result_add_detail(f"My host: {env.my_host_name}")
            result_add_detail(f"My service name {env.my_svc_name}")
            do_exit(NAGRES_CRASH)
        else:
            normal_check_interval = normal_check_interval * 60
        lost.normal_check_interval = normal_check_interval
    else:
        dbg("Using cached 'normal-check-interval'")

    dbg(
        "Normal check interval for service '%s' is %s seconds"
        % (env.my_svc_name, lost.normal_check_interval)
    )

    return lost, glob_age, age


def _get_maint_by():
    if (
        env.monitor_host
        and (env.monitor_svc is None)
        and (env.monitor_svc_regex is None)
    ):
        _maintenance_by = "host"
    elif env.monitor_host and env.monitor_svc and env.monitor_svc_regex:
        _maintenance_by = "service"
    elif env.monitor_host and env.monitor_svc:
        # "service" now supports non-output-regex setups
        _maintenance_by = "service"
    else:
        result_set_summary(
            "Config error: 'Monitor host' and/or 'Monitor service' undefined!"
        )
        do_exit(NAGRES_CRASH)
    return _maintenance_by


def _needs_maint_by_host(
    lq_api: LqAPI, rest_api: RestAPI
) -> Tuple[bool, str, Optional[Iterable[Downtime]]]:

    curr_dts: Optional[Iterable[Downtime]] = None
    res = False
    reason = "?"

    if env.monitor_dts:
        reason = "Downtime"
        if env.monitor_host == env.my_host_name:
            dts = lq_api.get_downtimes(env.monitor_host, None, None)
            dbg(f"LQ returned DT={len(dts)} on monitored")
            res = len(dts) > 0
        else:
            curr_dts = Downtimes.get_all(rest_api)
            for dt in Downtimes.find(curr_dts, host_name=env.monitor_host):
                dbg("Rest returned DT! on monitored")
                res = True
                break

    if not res and len(env.monitor_states) > 0:
        reason = "State"
        state = None
        if env.monitor_host == env.my_host_name:
            state = lq_api.get_host_state(env.monitor_host)
            dbg(f"LQ returned state {state} on monitored")
        else:
            state = rest_api.get_host_state(env.my_host_name)
            dbg(f"Rest returned state {state} on monitored")

        if state is not None:
            res = state in env.monitor_states

    return (
        res,
        reason,
        None,
    )


def _needs_maint_by_svc(
    lq_api: LqAPI, rest_api: RestAPI
) -> Tuple[bool, str, Optional[Iterable[Downtime]]]:

    curr_dts: Optional[Iterable[Downtime]] = None
    res = False
    reason = "?"

    if env.monitor_dts and not env.monitor_svc_regex:
        reason = "Downtime"
        if env.monitor_host == env.my_host_name:
            dts = lq_api.get_downtimes(env.monitor_host, env.monitor_svc, None)
            dbg(f"LQ returned DT={len(dts)} on monitored")
            res = len(dts) > 0
        else:
            curr_dts = Downtimes.get_all(rest_api)
            for dt in Downtimes.find(
                curr_dts, host_name=env.monitor_host, svc_name=env.monitor_svc
            ):
                dbg("Rest returned DT! on monitored")
                res = True
                break

    elif env.monitor_host and env.monitor_svc_regex:
        reason = "Plugin-output"
        # LqlCheckMaintenanceState = "GET services\nFilter: host_name ~ ^" + monitor_host + "$\nFilter: display_name ~ ^" + monitor_service + "$\nFilter: plugin_output ~ " + monitor_service_regex + "\nColumns: host_name\n"
        hosts_with_active_maint = rest_api.find_hosts_having_a_service(
            env.monitor_host, env.monitor_svc, env.monitor_svc_regex
        )
        res = len(hosts_with_active_maint) != 0

    if not res and len(env.monitor_states) > 0:
        reason = "State"
        if env.monitor_host == env.my_host_name:
            state = lq_api.get_service_state(env.monitor_host, env.monitor_svc)
            dbg(f"LQ returned state {state} on monitored")

        else:
            state = rest_api.get_service_state(env.monitor_host, env.monitor_svc)
            dbg(f"Rest returned state {state} on monitored")

        if state is not None:
            res = state in env.monitor_states

    return (res, reason, curr_dts)


def _needs_maintenance(
    lq_api: LqAPI, rest_api: RestAPI, maintenance_by: str
) -> Tuple[bool, str, Optional[Iterable[Downtime]]]:
    #
    # Determine if we need to set a downtime
    #
    if maintenance_by == "host":
        return _needs_maint_by_host(lq_api, rest_api)

    elif maintenance_by == "service":
        return _needs_maint_by_svc(lq_api, rest_api)


def main():
    host_svc_list = []

    global env
    env = parse_args(VERSION)
    show_config_dump(env)

    maintenance_by = _get_maint_by()

    lq_api = LqAPI()

    rest_api = RestAPI(
        env.omd_host,
        env.omd_site,
        env.automation_user,
        env.automation_secret,
        port=env.omd_port,
        use_ssl=(env.omd_port < 5000 or env.omd_port > 5999),
        verify_ssl=env.verify_ssl,
        no_proxy=env.no_proxy,
        # lq=None,
    )

    local_state, glob_state_age, lo_state_age = _get_local_state(lq_api)
    tgt_list = _ensure_tgt_list(rest_api, local_state, maintenance_by)

    # This call checks if we need a maintenance. If it needed to load
    # Downtimes via RESTAPI it returns those as well for furhter usage (optimization)
    maintenance, maint_reason, curr_dts = _needs_maintenance(
        lq_api, rest_api, maintenance_by
    )

    #
    # Determine downtimes to set/remove as needed
    #
    if not maintenance:
        if local_state.no_active_maint is True:
            dbg(
                "Condition requires no downtimes anymore, downtimes were previously removed!"
            )

        else:
            dbg(
                "Condition requires no downtimes anymore, removing automated downtimes!"
            )
            maintenance = False
            curr_dts = curr_dts if curr_dts else Downtimes.get_all(rest_api)

            dt_hash = Downtimes.get_hash()

            for target in tgt_list:
                _ = target[0]
                target_host = target[1]
                target_service = target[2]

                dts = Downtimes.find(curr_dts, target_host, target_service, dt_hash)
                if len(dts) > 0:
                    # Now, only used for stats below
                    host_svc_list.append(
                        (
                            "batch_del",
                            target_host,
                            target_service,
                            "Batch removing downtime for finished maintenance",
                        )
                    )
            Downtimes.remove_all_own(rest_api)
            local_state.no_active_maint = True  # Mark our downtimes removed

    else:
        dbg(
            f"Condition requires downtime (reason {maint_reason}), making sure all downtimes are still running long enough."
        )
        local_state.no_active_maint = (
            False  # Reset flag, since we may add downtimes now
        )

        curr_dts = curr_dts if curr_dts else Downtimes.get_all(rest_api)
        dt_hash = Downtimes.get_hash()

        # Check if there is a extension needed. In this case
        # we "readd"-all so we can do a batchdlete
        needing_readd = False
        for target in tgt_list:
            _ = target[0]
            target_host = target[1]
            target_service = target[2]

            dts = Downtimes.find(curr_dts, target_host, target_service, dt_hash)
            if len(dts) > 1:
                # Multiple DT, something went wrong, don't try to read
                # but wait for expiry, so we won't have tons on duplicated
                # downtimes (may be delete didn't work?!)
                continue
            elif len(dts) == 1:
                dt = dts[0]
                curr_ts = int(round(time.time()))
                dt_end_ts = datetime.datetime.timestamp(dt.end_time)
                if curr_ts > dt_end_ts - (local_state.normal_check_interval * 2):
                    needing_readd = True
                    break

        for target in tgt_list:
            _ = target[0]
            target_host = target[1]
            target_service = target[2]

            # Check if downtime exists:
            # - if dt with exact hash does not exist, set own
            # - if dt with excct hash dies exists
            #   check if those dt is sufficent end-time-wise, otherwise readd
            #   in case multiple own dt exist
            dts = Downtimes.find(curr_dts, target_host, target_service, dt_hash)
            if len(dts) > 1:
                # Multiple DT, something went wrong, don't try to read
                # but wait for expiry, so we won't have tons on duplicated
                # downtimes (may be delete didn't work?!)
                continue
            elif len(dts) == 1 and needing_readd:
                host_svc_list.append(
                    (
                        "readd",
                        target_host,
                        target_service,
                        "(Removing/)Adding downtime for extension",
                    )
                )
            elif len(dts) == 0:
                host_svc_list.append(
                    ("add", target_host, target_service, "Adding downtime")
                )

    #
    # Apply remaining changes to downtimes, update stats
    #
    dt_added = 0
    dt_readded = 0
    dt_removed = 0
    if host_svc_list:
        # print(host_svc_list)

        # Batch-add all required downtimes
        add_targets = []
        remove_old = False
        for host_svc_entry in reversed(list(set(host_svc_list))):
            if host_svc_entry[0] not in ["add", "readd"]:
                continue

            s = host_svc_entry[2]
            if s:
                add_targets.append((host_svc_entry[1], s))
            else:
                add_targets.append((host_svc_entry[1], None))

            remove_old = remove_old or host_svc_entry[0] == "readd"
        if add_targets:
            Downtimes.add_all(rest_api, add_targets, "(re)add", remove_old)

        # Process other entries/update stats
        for host_svc_entry in reversed(list(set(host_svc_list))):
            if host_svc_entry[0] in ["add", "readd"]:
                # Already done in batch-op above, count only
                dt_added += 1 if host_svc_entry[0] == "add" else 0
                dt_readded += 1 if host_svc_entry[0] == "readd" else 0

            elif host_svc_entry[0] == "batch_del":
                # Only stats, was already removed via batch-request
                dt_removed += 1

            else:
                raise "Unsupported operation type: " + host_svc_entry[0]

    #
    # plugin output
    #

    # plugin summary
    deps = f"{len(tgt_list)} dependent(s) found"
    if maintenance:
        result_set_summary(f"Maintenance is active. Reason: {maint_reason}. {deps}.")
    else:
        result_set_summary(f"Maintenance is not active. {deps}.")

    # Build plugin-'affected'info
    if not maintenance:
        result_add_detail(
            "If host enters maintenance these hosts and services are also affected:"
        )
    else:
        result_add_detail("Affected hosts and services by this rule:")

    if tgt_list:
        for target in tgt_list:
            if target[2]:
                result_add_detail(
                    "- Service '%s' on host '%s' (%s)"
                    % (target[2], target[1], target[0])
                )
            else:
                result_add_detail("- Host '%s' (%s)" % (target[1], target[0]))
    else:
        result_add_detail(
            f"{env.no_match_msg_tag} NOTHING FOUND. Nobody seems to be dependant on this host {env.no_match_msg_tag}"
        )

    result_add_detail(
        f"Stats on last run: targets: {len(tgt_list)}. downtimes: {dt_removed} removed // {dt_added} added // {dt_readded} readded/extended"
    )

    if lo_state_age is None:
        lo_msg = "Just renewed"
    else:
        lo_msg = f"{int(lo_state_age/60)} minutes old"
    result_add_detail(f"Instance cache age: {lo_msg}")

    if glob_state_age is not None:
        gm = f"{int(glob_state_age/60)} minutes old"
        result_add_detail(f"Global cache age: {gm}")

    #
    # Done
    #
    LocalStateCache.write(env.get_my_name(), local_state, env.cmd_line_hash)
    do_exit(NAGRES_OK)


### End Main


try:
    main()
except Exception:
    result_set_summary("! Exception during execution. See details")
    result_add_detail(*traceback.format_exc().splitlines())
    do_exit(NAGRES_CRASH)
