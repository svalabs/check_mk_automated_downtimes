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
import fcntl
import os
import re
import pickle
import time
import urllib.parse

from typing import Dict, Iterable, List, Optional, Tuple
from dataclasses import dataclass

from auto_downtimes_restapi import RestAPI
from auto_downtimes_common import (
    dbg,
    omd_root,
    CACHE_LOCK,
    MAX_CACHE_AGE_MINUTES,
    WORD_BOUND,
    HostInfo,
    SvcInfo,
)


# Lock helper


class FLockException(Exception):
    pass


class FLock:

    def __init__(self, lock_fn):
        self.lockf = None
        self.lock_fn = lock_fn

    def __enter__(self):
        self.acquire()

    def __exit__(self, *prms):
        self.release()

    def acquire(self):
        dbg(f"Acquiring lock {self.lock_fn}")

        if not os.path.exists(self.lock_fn):
            with open(self.lock_fn, "w") as f:
                f.write("")

        f = open(self.lock_fn, "r")
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            dbg(f"Acquired lock {self.lock_fn}")
            self.lockf = f
        except Exception:
            self.lockf = None
            raise FLockException("Can't acquire lock")

    def release(self):
        if self.lockf != None:
            dbg(f"Releasing lock {self.lock_fn}")
            try:
                fcntl.flock(self.lockf.fileno(), fcntl.LOCK_UN)
            except:
                raise
            else:
                self.lockf.close()
            finally:
                self.lockf = None


# Helper functions


@dataclass
class CacheData:
    hosts_by_id: Dict[str, HostInfo]
    hosts_by_alias: Dict[str, HostInfo]
    hosts_by_id_insens: Dict[str, Iterable[str]]
    hosts_by_alias_insens: Dict[str, Iterable[str]]
    svcs: Iterable[SvcInfo]
    filetime: Optional[datetime.datetime]


class InfoCache:

    path = f"{omd_root}/tmp/check_mk/auto_downtimes/auto_downtimes_cache.pkl"

    _api: RestAPI
    _sites: Iterable[str]
    _cache: CacheData

    def __init__(self, api: RestAPI):
        self._api = api
        # self._sites = sites

    def _find_hosts(self, host_name: str, case_insensitive: bool) -> Iterable[HostInfo]:
        res: List[HostInfo] = []
        if case_insensitive:
            hns = list(self._cache.hosts_by_id_insens.get(host_name, []))
            has = list(self._cache.hosts_by_alias_insens.get(host_name, []))
            for h in hns + has:
                if ahost := self._cache.hosts_by_id.get(h):
                    res.append(ahost)
        else:
            if ahost := self._cache.hosts_by_id.get(host_name):
                res.append(ahost)
            if ahost := self._cache.hosts_by_alias.get(host_name):
                res.append(ahost)

        return res

    def find_hosts(
        self,
        name_regex: str,
        case_insensitive: bool,
    ) -> Iterable[str]:

        # Simulate LQ-behavor
        if not name_regex.startswith("^"):
            name_regex = ".*" + name_regex

        flags = 0
        if case_insensitive:
            flags = re.IGNORECASE

        re1 = re.compile(name_regex, flags)
        res = set()

        for k, v in self._cache.hosts_by_id.items():
            if re1.match(k):
                res.add(k)

        res = list(res)
        # print("XX", res, name_regex, case_insensitive)
        return res

    def find_childs_of_host(
        self, host_name: str, recursive: bool, case_insensitive: bool
    ) -> Iterable[str]:

        hosts_to_check: List[HostInfo] = self._find_hosts(host_name, case_insensitive)

        res = set()
        for ahost in hosts_to_check:
            ah: HostInfo = ahost
            for c in ah.childs:
                res.add(c)

        if recursive:
            more = set()
            for mhost in res:
                if mhost == host_name:
                    dbg("Would loop on {mhost}, skipping")
                    continue
                for e in self.find_childs_of_host(mhost, True, False):
                    more.add(e)

            for e in more:
                res.add(e)

        res = list(res)
        return res

    # def find_hosts_having_a_service(
    #     self, host_name: str, svc_name: str, svc_plugin_output_regex
    # ) -> Iterable[str]:
    #     raise Exception(
    #         "Not implemented, use REST-API, should not be required for dependency detection!!!"
    #     )

    def find_parents_of_host(
        self, host_name: str, case_insensitive: bool
    ) -> Iterable[str]:
        hosts_to_check: List[HostInfo] = self._find_hosts(host_name, case_insensitive)
        res = set()
        for h in hosts_to_check:
            for p in h.parents:
                res.add(p)

        res = list(res)
        return res

    def find_similar_hosts(
        self, hostname: str, case_insensitive: bool, boundary_match: bool
    ) -> Iterable[str]:
        kw = hostname
        res = []

        if not boundary_match:

            if not case_insensitive:
                for h in self._cache.hosts_by_id.values():
                    if h.id.name.find(kw) >= 0 or h.id.alias.find(kw) >= 0:
                        if h.id.name != kw:
                            res.append(h.id.name)
            else:
                hn = kw.lower()
                for h in self._cache.hosts_by_id.values():
                    if (
                        h.id.name.lower().find(hn) >= 0
                        or h.id.alias.lower().find(hn) >= 0
                    ):
                        if h.id.name != hn:
                            res.append(h.id.name)
        else:
            # Simulate LQ-compat
            if not kw.startswith("^"):
                kw = ".*" + kw

            flags = 0
            if case_insensitive:
                flags = re.IGNORECASE

            name_regex = WORD_BOUND + kw + WORD_BOUND
            re1 = re.compile(name_regex, flags)
            for h in self._cache.hosts_by_id.values():
                if re1.match(h.id.name) or re1.match(h.id.alias):
                    if h.id.name != hostname:
                        res.append(h.id.name)

        return res

    def find_services(
        self,
        name_regex: str,
        optional_identifier: Optional[str],
        case_insensitive: bool,
        boundary_match: bool,
        host_name_regex: Optional[str] = None,
    ) -> Iterable[Tuple[str, str]]:
        """boundary_match: Only applied to name_regex"""

        # Simulate LQ-behavor
        if not name_regex.startswith("^"):
            name_regex = ".*" + name_regex
        if host_name_regex != None:
            if not host_name_regex.startswith("^"):
                host_name_regex = ".*" + host_name_regex
        
        if boundary_match:                        
            name_regex = WORD_BOUND + name_regex + WORD_BOUND

        flags = 0
        if case_insensitive:            
            flags = re.IGNORECASE

        re1 = re.compile(name_regex, flags)
        re2 = re.compile(optional_identifier, flags) if optional_identifier else None
        re_host = re.compile(host_name_regex, flags) if host_name_regex else None
        res = set()

        for s in self._cache.svcs:
            if re1.match(s.name) or (re2 and re2.match(s.name)):
                if (not re_host) or (re_host.match(s.host.name)):
                    res.add((s.host.name, s.name))

        res = list(res)
        # print("XX", res, name_regex, host_name_regex, case_insensitive)
        return res

    def find_services_by_host(
        self, host_name_regex: str, optional_identifier: Optional[str]
    ) -> Iterable[Tuple[str, str]]:
        raise Exception("This code ist not implemented/not required!!!")
        return []

    @staticmethod
    def get_cache_file_time() -> Tuple[Optional[datetime.datetime], Optional[int]]:
        try:
            ft = datetime.datetime.utcfromtimestamp(os.path.getmtime(InfoCache.path))
            age = (datetime.datetime.utcnow() - ft).total_seconds()
            expired = age >= 60 * MAX_CACHE_AGE_MINUTES
            # expired = True
            return ft, age, expired
        except:
            return None, None, True

    def load(self) -> bool:
        fn = self.path
        try:
            if os.path.exists(fn):
                cache_file_time = datetime.datetime.utcfromtimestamp(
                    os.path.getmtime(fn)
                )
                age = (datetime.datetime.utcnow() - cache_file_time).total_seconds()
                if age < 60 * MAX_CACHE_AGE_MINUTES:
                    try:
                        with open(fn, "rb") as f:
                            dbg(f"Using global-cache. Age {age}s")
                            data = pickle.load(f)
                            self._cache = data
                            self._cache.filetime = cache_file_time
                        dbg("Global-cache loaded")
                    except Exception as ex:
                        dbg(f"Global-Cache load failed {ex}")
                    else:
                        return True
                else:
                    dbg("Global-Cache too old")

        except Exception as ex:
            dbg(f"Err while loading global-cache: {ex}")
            # pass

        # No valid cache, try to create
        if self._update():
            return True
        else:
            return False

    def _update(self) -> bool:
        dbg("Updating global-cache")
        try:
            with FLock(CACHE_LOCK) as lock:
                hosts = self._api.get_hosts()
                svcs = self._api.get_services()
                # print("X", svcs)
                h_by_name = {h.id.name: h for h in hosts}
                h_by_alias = {h.id.alias: h for h in hosts}

                h_by_name_insens = {}
                h_by_alias_insens = {}
                for h in hosts:
                    nam = h.id.name.lower()
                    ali = h.id.alias.lower()
                    h_by_name_insens.setdefault(nam, set()).add(h.id.name)
                    h_by_alias_insens.setdefault(ali, set()).add(h.id.name)

                self._cache = CacheData(
                    hosts_by_id=h_by_name,
                    hosts_by_alias=h_by_alias,
                    hosts_by_id_insens=h_by_name_insens,
                    hosts_by_alias_insens=h_by_alias_insens,
                    svcs=svcs,
                    filetime=datetime.datetime.utcnow(),
                )

                fn = self.path
                os.makedirs(os.path.dirname(fn), exist_ok=True)
                time.sleep(
                    5
                )  # Paranoia too reduce races, by instances started before us
                with open(fn, "wb") as f:
                    pickle.dump(self._cache, f)

                dbg("Updating global-cache done")
                return True
        except FLockException as oex:
            dbg("Cannot acquire lock. Locked by other process?")
            return False
        except Exception as ex:
            raise


#
#
#
#


@dataclass
class LocalState:
    tgt_list: Optional[Tuple[Tuple[str]]]
    no_active_maint: Optional[bool]
    normal_check_interval: Optional[int] = None
    _short_lived_refresh: Optional[datetime.datetime] = None
    _cfg_hash: Optional[str] = None
    _last_update_ts: Optional[int] = None


class LocalStateCache:

    path_templ = f"{omd_root}/tmp/check_mk/auto_downtimes/_$MYNAME$.cache.pkl"

    @staticmethod
    def _get_path(my_name: str) -> str:
        return LocalStateCache.path_templ.replace(
            "$MYNAME$", urllib.parse.quote(my_name)
        )

    @staticmethod
    def load(
        my_name: str,
        info_cache_file_time: Optional[datetime.datetime],
        dt_dur_mins: int,
        cfg_hash: str,
    ) -> Tuple[Optional[LocalState], Optional[int]]:
        path = LocalStateCache._get_path(my_name)

        try:
            if os.path.exists(path) or not info_cache_file_time:
                cache_file_time = datetime.datetime.utcfromtimestamp(
                    os.path.getmtime(path)
                )
                age = (datetime.datetime.utcnow() - cache_file_time).total_seconds()
                # Force refresh every x minutes, must be newer than info-cache
                # This age is only a rough estimate, since the
                # cache usually gets updated on each run with
                # state date.
                # Also our cache may be invalid if global-cache-file-time
                # is None. In this case the global cache was deleted or is expired
                # In this case we won't use the local cache data, which
                # triggers a global-cache-load, which then should trigger
                # a global cache refresh. Not nice...
                if (age < 60 * MAX_CACHE_AGE_MINUTES) and (
                    info_cache_file_time is not None
                    and cache_file_time >= info_cache_file_time
                ):
                    try:
                        with open(path, "rb") as f:
                            dbg("Using state-cache")
                            data: LocalState = pickle.load(f)
                            dbg("State-cache loaded")

                        if data._cfg_hash != cfg_hash:
                            dbg("Cfg-hash does not match. State-cache no longer valid")
                            return None, None
                        else:
                            dbg("Cfg-hash matches")

                        # Short-lived-data may be cached for 1/3 of downtime-durations
                        if not data._short_lived_refresh or (
                            (
                                datetime.datetime.utcnow() - data._short_lived_refresh
                            ).total_seconds()
                            > (dt_dur_mins / 3) * 60
                        ):
                            dbg("State-cache cleared short-lived-data")
                            data._short_lived_refresh = datetime.datetime.utcnow()
                            data.normal_check_interval = None

                        if data._last_update_ts is not None:
                            # Recalc real age now
                            age = (
                                datetime.datetime.utcnow().timestamp()
                                - data._last_update_ts
                            )
                            if age > (60 * MAX_CACHE_AGE_MINUTES):
                                dbg("State-cache: Data indicates too old, discarding")
                                return None, None
                            else:
                                pass
                                # dbg(f"State-cache: data is {age}s old")
                        else:
                            dbg("State-cache: - no ts in data found, assuming good")

                        return data, age
                    except Exception as ex:
                        dbg(f"State-cache load failed {ex}")
                else:
                    dbg("State-cache to old or older than info-cache")
            else:
                dbg(
                    "State-cache not vaild or nor Info-Cache-Reference-Timestamp (not yet avail?)"
                )

        except Exception as ex:
            dbg(f"Err while loading state-cache: {ex}")
            pass

        return None, None

    @staticmethod
    def write(my_name, local_state: LocalState, cfg_hash: str):
        if local_state._cfg_hash is not None and cfg_hash != local_state._cfg_hash:
            raise Exception("Trying to update cfg_hash with another one in localstate")
        if local_state._cfg_hash is None:
            dbg("Adding _cfg_hash to localstate")
            local_state._cfg_hash = cfg_hash
        if local_state._last_update_ts is None:
            local_state._last_update_ts = datetime.datetime.utcnow().timestamp()

        fn = LocalStateCache._get_path(my_name)
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        with open(fn, "wb") as f:
            pickle.dump(local_state, f)
        dbg("State-cache written to disk")
