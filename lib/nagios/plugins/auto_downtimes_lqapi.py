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
import socket

from typing import Iterable, Optional
from auto_downtimes_common import Downtime, omd_root

#
# Not all LQ-Calls are used anymore, and thus aren't tested well
#


class LqAPI:

    def __init__(self):
        self._hostfields_to_check = ["host_name", "host_display_name"]

    def _exec(self, lq: str):
        ls = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        ls.connect("%s/tmp/run/live" % omd_root)
        ls.send(lq.encode())
        ls.shutdown(socket.SHUT_WR)

        res = [ln for ln in ls.recv(100000000).decode().split("\n")[:-1]]
        # FUNC_Debug(f"~LQ~ Result {res}")

        return res

    def find_hosts(self, regex: str) -> Iterable[str]:
        # Original
        # LqlGetHostname = "GET hosts\nFilter: display_name ~ " + target_host + "\nColumns: display_name\n"

        res = set()
        for k in self._hostfields_to_check:
            query = f"GET hosts\nFilter: {k} ~ {regex}\nColumns: host_name\n"
            for entry in self._exec(query):
                res.add(entry)

        return list(res)

    def get_childs_from_parent(
        self, parent_host: str, case_insensitive: bool
    ) -> Iterable[str]:
        op = "~" if not case_insensitive else "~~"
        res = set()
        for k in self._hostfields_to_check:
            query = f"GET hosts\nFilter: {k} {op} ^{parent_host}$\nFilter: childs != \nColumns: childs\n"
            for childs in self._exec(query):
                for child in childs.split(","):
                    res.add(child)
                    for sub_child in self.get_childs_from_parent(
                        child, case_insensitive
                    ):
                        res.add(sub_child)

        return list(res)

    def get_host_state(self, name: str) -> Optional[int]:
        for k in self._hostfields_to_check:
            query = f"GET hosts\nFilter: {k} = {name}\nColumns: state\n"
            for entry in self._exec(query):
                return int(entry)

        return None

    def get_services(self, host_name: str, svc_name: str) -> Iterable[str]:
        res = set()
        query = f"GET services\nFilter: host_name = {host_name}\nFilter: display_name = {svc_name}\nColumns: host_name display_name\n"
        for entry in self._exec(query):
            res.add(entry)

        return list(res)

    def get_service_check_interval(
        self, host_name: str, svc_name: str
    ) -> Optional[float]:
        query = f"GET services\nFilter: host_name = {host_name}\nFilter: display_name = {svc_name}\nColumns: check_interval\n"
        for entry in self._exec(query):
            return float(entry)

        return None

    def get_service_state(self, host_name: str, svc_name: str) -> Optional[int]:
        query = f"GET services\nFilter: host_name = {host_name}\nFilter: display_name = {svc_name}\nColumns: state\n"
        # print(query)
        for entry in self._exec(query):
            return int(entry)

        return None

    def get_similar_hosts(
        self, host_name: str, case_insensitive: bool
    ) -> Iterable[str]:
        op = "~" if not case_insensitive else "~~"
        res = set()
        for k in self._hostfields_to_check:
            query = f"GET hosts\nFilter: {k} {op} ^.*{host_name}.*$\nFilter: host_name != {host_name}\nColumns: host_name\n"
            for entry in self._exec(query):
                # FUNC_Debug(f"In field {k} -> {entry}")
                res.add(entry)

        return list(res)

    def get_downtime_id_list(
        self, host_name: str, comment_keyword: str
    ) -> Iterable[str]:
        query = f"GET downtimes\nFilter: host_name = {host_name}\nFilter: service_display_name ~ {filter}\nFilter: comment ~ ^{comment_keyword}\nColumns: id\n"
        return self._exec(query)

    def get_downtimes(
        self,
        host_name: str,
        service_name: Optional[str] = None,
        filter_comment: Optional[str] = None,
    ) -> Iterable[Downtime]:

        query = (
            f"GET downtimes\n"
            f"Filter: host_name = {host_name}\n"
            f"Columns: id host_name service_display_name start_time end_time comment author is_service\n"
        )

        data = self._exec(query)

        res: Iterable[Downtime] = []
        for entry in data:
            e = entry.split(";")
            ne = Downtime(
                id=e[0],
                title="Downtime",  # Not supported in LQ
                host_name=e[1],
                svc_name=e[2],
                start_time=datetime.datetime.fromtimestamp(int(e[3])),
                end_time=datetime.datetime.fromtimestamp(int(e[4])),
                comment=e[5],
                author=e[6],
                is_svc_dt=int(e[7]) != 0,
            )
            # FUNC_Debug(ne)
            if service_name:
                if not ne.svc_name or ne.svc_name.find(service_name) < 0:
                    continue

            if filter_comment:
                if not ne.comment or ne.comment.find(filter_comment) < 0:
                    continue

            if not service_name and ne.is_svc_dt:
                continue

            if ne.host_name == host_name:
                res.append(ne)

        # FUNC_Debug(res)
        return res
