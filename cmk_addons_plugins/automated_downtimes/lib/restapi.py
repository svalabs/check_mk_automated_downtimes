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
import os
import requests

from typing import Dict, Iterable, Optional, Tuple, Union

from urllib3.exceptions import InsecureRequestWarning

from .common import (
    MAX_QUERY_BATCH_SIZE,
    dbg,
    chunks,
    Downtime,
    HostId,
    HostInfo,
    SvcInfo,
)


class RestAPI:

    def __init__(
        self,
        host: str,
        site: str,
        autouser: str,
        passwd: str,
        port: int = 443,
        use_ssl=False,
        verify_ssl=False,
        no_proxy=False,
    ):

        self._hostfields_to_check = ["name", "display_name"]

        scheme = "http" if not use_ssl else "https"

        if not verify_ssl:
            requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

        self.api_url = f"{scheme}://{host}:{port}/{site}/check_mk/api/1.0"
        self._session = requests.session()
        self._session.verify = verify_ssl
        self._session.headers["Authorization"] = f"Bearer {autouser} {passwd}"
        self._session.headers["Accept"] = "application/json"
        if no_proxy:
            for p in "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY":
                if p in os.environ:
                    del os.environ[p]
            self._session.proxies = {"http": None, "https": None}

    def _get(self, url: str, params: Dict):
        resp = self._session.get(
            f"{self.api_url}/{url}", params=params, verify=self._session.verify  # Clown
        )

        return resp

    def _post(self, url: str, dct: Dict) -> requests.Response:
        # jt = json.dumps(obj)
        # print(jt)

        resp = self._session.post(
            f"{self.api_url}/{url}",
            headers={
                "Content-Type": "application/json",
            },
            json=dct,
            verify=self._session.verify,  # Clown
        )

        return resp

    def _raise_error(self, req_name: str, resp: Union[requests.Response, int]):
        try:
            code = resp.status_code
            if code >= 300:
                msg = bytes.decode(resp.content, "utf-8")
            else:
                msg = ""
        except:
            # is only status code
            code = resp
            msg = ""
        raise Exception(f"Error while '{req_name}: {code} ({msg})")

    #
    # Downtime
    #

    def delete_downtime(self, id: str, no_throw=False) -> bool:

        resp = self._post(
            "domain-types/downtime/actions/delete/invoke",
            {"delete_type": "by_id", "downtime_id": id},
        )

        if resp.status_code != 204 and resp.status_code != 200:
            if no_throw:
                return False
            else:
                self._raise_error("delete_downtime", resp)

        return True

    def delete_downtimes(self, ids: Iterable[str], no_throw=False) -> bool:

        for c in chunks(ids, MAX_QUERY_BATCH_SIZE):
            q = '{"op": "or", "expr": ['
            dlm = ""
            for id in c:
                q = q + dlm + '{"op": "=", "left": "id", "right": "' + id + '" }'
                dlm = ","

            q = q + "]}"

            resp = self._post(
                "domain-types/downtime/actions/delete/invoke",
                {
                    "delete_type": "query",
                    "query": q,
                },
            )

            if resp.status_code != 204 and resp.status_code != 200:
                if no_throw:
                    return False
                else:
                    self._raise_error("delete_downtime_by_ids", resp)

        return True

    def delete_downtimes_by_keyword(
        self,
        kw: str,
        until_start_time: Optional[datetime.datetime] = None,
        no_throw=False,
    ) -> bool:

        q = '{"op": "and", "expr": ['
        q += '{"op": "~", "left": "comment", "right": ".*' + kw + '"}'
        if until_start_time:
            q += (
                ', {"op": "<=", "left": "start_time", "right": "'
                + str(int(until_start_time.timestamp()))
                + '"}'
            )
        q += "]}"

        resp = self._post(
            "domain-types/downtime/actions/delete/invoke",
            {
                "delete_type": "query",
                "query": q,
            },
        )

        if resp.status_code != 204 and resp.status_code != 200:
            if no_throw:
                return False
            else:
                self._raise_error("delete_downtime_by_keyword", resp)

        return True

    def get_downtimes(
        self,
        host_name: Optional[str] = None,
        service_name: Optional[str] = None,
        filter_comment: Optional[str] = None,
    ) -> Iterable[Downtime]:
        """- if host_name is set but not a svc_name, only host-dt  are returned
        - if neighter host_name no servce_name is set all dt are returned
        """

        # Was LqlCheckMaintenanceState = "GET hosts\nFilter: host_name ~ ^" + monitor_host + "$\nFilter: host_scheduled_downtime_depth != 0\nColumns: host_name\n"

        # if self._lq:
        # return self._lq.get_downtimes(host_name, service_name, filter_comment)

        # We can either filter by service or hostname
        # (or could use a complex query)
        dct = {}
        if service_name:
            dct["service_description"] = service_name
        elif host_name:
            dct["host_name"] = host_name

        resp = self._get("domain-types/downtime/collections/all", dct)

        res: Iterable[Downtime] = []
        if resp.status_code == 200:
            data = resp.json()
            if "value" in data:
                for e in data["value"]:
                    ne = Downtime(
                        id=e["id"],
                        title=e["title"],
                        host_name=e["extensions"]["host_name"],
                        svc_name=service_name,
                        start_time=datetime.datetime.fromisoformat(
                            e["extensions"]["start_time"]
                        ),
                        end_time=datetime.datetime.fromisoformat(
                            e["extensions"]["end_time"]
                        ),
                        comment=e["extensions"]["comment"],
                        author=e["extensions"]["author"],
                        is_svc_dt=e["extensions"].get("is_service") == "yes",
                    )

                    if ne.is_svc_dt and not ne.svc_name:
                        # Work around brain-dead API or am I
                        ne.svc_name = f"{ne.title}".replace(
                            "Downtime for service:", ""
                        ).strip()

                    if filter_comment:
                        if not ne.comment or ne.comment.find(filter_comment) < 0:
                            continue

                    if host_name and not service_name and ne.is_svc_dt:
                        continue

                    if not host_name or ne.host_name == host_name:
                        res.append(ne)

        elif resp.status_code == 204:
            pass
        else:
            self._raise_error("get_downtimes", resp)

        # dbg(f"**REST get_downtimes: {res}")
        return res

    def set_downtime(
        self,
        comment: str,
        start: datetime.datetime,
        end: datetime.datetime,
        host_name: str,
        serivce_names: Optional[Iterable[str]] = None,
        #  on_fail: Optional[Callable[[requests.Response],any]] = None
    ) -> None:

        dt_type = "host" if not serivce_names else "service"
        dct = {
            "start_time": start.astimezone().isoformat(),
            "end_time": end.astimezone().isoformat(),
            "comment": comment,
            "host_name": host_name,
            "downtime_type": dt_type,
        }
        if serivce_names:
            dct["service_descriptions"] = serivce_names

        resp = self._post(f"domain-types/downtime/collections/{dt_type}", dct)

        if resp.status_code != 204:
            self._raise_error("set_downtime", resp)

    def set_downtimes(
        self,
        comment: str,
        start: datetime.datetime,
        end: datetime.datetime,
        targets: Iterable[Tuple[str, Optional[Iterable[str]]]],
        #  on_fail: Optional[Callable[[requests.Response],any]] = None
    ) -> None:

        host_targets = []
        svc_targets = []
        for t in targets:
            if len(t) == 1 or not t[1]:
                host_targets.append((t[0], None))
            else:
                for s in t[1]:
                    svc_targets.append((t[0], s))

        for dt_type in ["host", "service"]:
            dt_typ = "Host" if dt_type == "host" else "Svc"
            dct = {
                "start_time": start.astimezone().isoformat(),
                "end_time": end.astimezone().isoformat(),
                "comment": comment.replace("$TYP$", dt_typ),
                "downtime_type": (
                    "host_by_query" if dt_type == "host" else "service_by_query"
                ),
            }

            tgt = host_targets if dt_type == "host" else svc_targets
            if not tgt:
                continue

            for ch in chunks(tgt, MAX_QUERY_BATCH_SIZE):
                q = '{"op": "or", "expr": ['
                dlm = ""
                for t in ch:
                    if dt_type == "host":
                        sop = '{"op": "=", "left": "name", "right": "' + t[0] + '"}'
                    else:
                        # print(t)
                        sop = '{"op": "and", "expr": ['
                        sop += (
                            '{"op": "=", "left": "host_name", "right": "' + t[0] + '"},'
                        )
                        sop += (
                            '{"op": "=", "left": "display_name", "right": "'
                            + t[1]
                            + '"}'
                        )
                        sop += "]}"
                    q = q + dlm + sop
                    dlm = ","
                q = q + "]}"
                # endfor

                # print(q, ch)
                dct["query"] = q
                resp = self._post(f"domain-types/downtime/collections/{dt_type}", dct)

                if resp.status_code == 422:
                    if resp.text.find("not match any") >= 0:
                        dbg(f"No matches on setting downtimes: {ch}!")
                        continue

                if resp.status_code != 204:
                    self._raise_error("set_downtimes", resp)

        # endfor
        return True

    #
    # Host seaech
    #

    def find_childs_of_host(
        self, host_name: str, recursive: bool, case_insensitive: bool
    ) -> Iterable[str]:

        # Was: (recursive!)
        # query = f"GET hosts\nFilter: {k} {op} ^{parent_host}$\nFilter: childs != \nColumns: childs\n"

        op = "~" if not case_insensitive else "~~"
        res = set()

        for hf in self._hostfields_to_check:
            dct = {}
            dct["columns"] = ["childs"]
            dct["query"] = (
                '{"op": "and", "expr": ['
                + f'{{ "op": "{op}", "left": "{hf}", "right": "^{host_name}$" }}, '
                + f'{{ "op": "!=", "left": "childs", "right": "" }}'
                + "]}"
            )
            resp = self._get("domain-types/host/collections/all", dct)

            if resp.status_code == 200:
                data = resp.json()
                if "value" in data:
                    for dct in data["value"]:
                        for h in dct.get("extensions", {}).get("childs", []):
                            res.add(h)
                            if recursive:
                                for sub_h in self.find_childs_of_host(
                                    h, True, case_insensitive
                                ):
                                    res.add(sub_h)
                else:
                    self._raise_error("get_childs_from_parent invalid response", resp)
            else:
                self._raise_error("get_childs_from_parent", resp)

        # dbg(f***REST Child {parent_host} / {res}")
        return list(res)


    def _parse_perfdata(s: str) -> Dict:
        res = {}
        if s:
            parts = s.split(" ")
            for p in parts:
                kv = p.split("=", maxsplit=2)
                if len(kv) < 2:
                    continue
                k, v = kv
                v = v.split(";")[0]
                try:                    
                    v = int(v)
                except:
                    pass
                res[k] = v
        return res


    def find_hosts_having_a_service(
        self, host_name: str, svc_name: str, svc_plugin_output_regex: str, include_perfdata: bool = False
    ) -> Iterable[Tuple[str, str, str]]:
        # Was:
        # LqlCheckMaintenanceState = "GET services\nFilter: host_name ~ ^" + monitor_host + "$\nFilter: display_name ~ ^" + monitor_service + "$\nFilter: plugin_output ~ " + monitor_service_regex + "\nColumns: host_name\n"

        res = []
        dct = {}
        dct["columns"] = ["host_name", "plugin_output"]
        if include_perfdata:
            dct["columns"].append("perf_data") # 2.3+: field 'performance_data' returns a dict!

        pr = svc_plugin_output_regex.replace('\\', '\\\\') # old CMK 2.2-Python does not allow this in f-string
        dct["query"] = (
            '{"op": "and", "expr": ['
            + f'{{ "op": "~", "left": "host_name", "right": "^{host_name}$" }}, '
            + f'{{ "op": "~", "left": "display_name", "right": "^{svc_name}$" }}, '
            + f'{{ "op": "~", "left": "plugin_output", "right": "{pr}" }} '
            + "]}"
        )
        resp = self._get("domain-types/service/collections/all", dct)

        res = {}
        fail = None
        if resp.status_code == 200:
            data = resp.json()
            if "value" in data:
                for e in data["value"]:
                    hn = e.get("extensions", {}).get("host_name", None)
                    plugin_output = e.get("extensions", {}).get("plugin_output", None)
                    perfdata = e.get("extensions", {}).get("perf_data", None) if include_perfdata else None # field 'performance_data' returns a dict!
                    perfdata = RestAPI._parse_perfdata(perfdata)
                    #print(perfdata)
                    if hn is None:
                        fail = "No data in response"
                        break                                            
                    res[hn] = (plugin_output, perfdata)
            else:
                fail = "No 'value' in response"
        else:
            fail = "Bad HTTP statuscode"

        if fail:
            self._raise_error(
                f"find_hosts_having_a_service invalid response: {fail}", resp
            )

        # dbg(f"**REST find_hosts_having_a_service {list(res)}")
        fres = []
        for k, v in res.items():
            fres.append((k, v[0], v[1]))
        return list(fres)

    def find_parents_of_host(
        self, host_name: str, case_insensitive: bool
    ) -> Iterable[str]:
        # Was:
        # LqlGetParentHosts = "GET hosts\nFilter: display_name ~~ ^" + host_name + "$\nFilter: parents != \nColumns: parents\n"

        op = "~" if not case_insensitive else "~~"
        res = []

        for hf in self._hostfields_to_check:
            dct = {}
            dct["columns"] = ["parents"]
            dct["query"] = (
                '{"op": "and", "expr": ['
                + f'{{ "op": "{op}", "left": "{hf}", "right": "^{host_name}$" }}, '
                + f'{{ "op": "!=", "left": "parents", "right": "" }}'
                + "]}"
            )
            resp = self._get("domain-types/host/collections/all", dct)

            if resp.status_code == 200:
                data = resp.json()
                if "value" in data:
                    for dct in data["value"]:
                        for e in dct.get("extensions", {}).get("parents", []):
                            res.append(e)
                else:
                    self._raise_error("get_parents_of_host invalid response", resp)
            else:
                self._raise_error("get_parents_of_host", resp)

        # dbg(f"*****REST OParent {host_name} / {res}")
        return res

    def find_similar_hosts(
        self, host_name: str, case_insensitive: bool
    ) -> Iterable[str]:

        # Was:
        # query = f"GET hosts\nFilter: {k} {op} ^.*{host_name}.*$\nFilter: host_name != {host_name}\nColumns: host_name\n"

        op = "~" if not case_insensitive else "~~"

        dct = {}
        dct["columns"] = ["name"]
        dct["query"] = (
            "{" + f'"op": "{op}", "left": "name", "right": "{host_name}"' + "}"
        )
        # dct["query"] = {"op": "and", "expr":[{"op": "=", "left": "host_name", "right":host_name}, {"op": "=", "left": "host_name", "right":host_name}]}
        resp = self._get("domain-types/host/collections/all", dct)

        if resp.status_code == 200:
            data = resp.json()
            if "value" in data:
                res = []
                for e in data["value"]:
                    if h := e.get("id"):
                        if h != host_name:
                            res.append(h)
                return res

        self._raise_error("get_similar_hosts", resp)

    def get_hosts(self) -> Iterable[HostInfo]:

        # Was: (recursive!)
        # query = f"GET hosts\nColumns: name display_name childs labels""

        res = []

        dct = {}
        dct["columns"] = ["name", "display_name", "parents", "childs", "labels"]
        resp = self._get("domain-types/host/collections/all", dct)

        if resp.status_code == 200:
            data = resp.json()
            print("XXXX", data)
            if "value" in data:
                for dct in data["value"]:
                    nam = dct.get("extensions", {}).get("name")
                    dnam = dct.get("extensions", {}).get("display_name")
                    childs = dct.get("extensions", {}).get("childs", [])
                    parents = dct.get("extensions", {}).get("parents", [])
                    site = (
                        dct.get("extensions", {}).get("labels", {}).get("cmk/site", "")
                    )
                    if nam and dnam and site:
                        hid = HostId(nam, dnam, site)
                        res.append(HostInfo(hid, parents, [], childs))
            else:
                self._raise_error("get_hosts invalid response", resp)
        else:
            self._raise_error("get_hosts", resp)

        # dbg(f"***REST Hosts {res}")
        return res

    def get_host_state(self, host_name: str) -> Optional[int]:
        """No alias search!"""

        dct = {}
        dct["columns"] = ["state"]
        dct["query"] = (
            '{"op": "or", "expr": ['
            + f'{{ "op": "=", "left": "name", "right": "{host_name}" }} '
            # + f', {{ "op": "eq", "left": "display_name", "right": "{host_name}" }}, '
            + "]}"
        )
        resp = self._get("domain-types/host/collections/all", dct)

        res = None
        fail = None
        if resp.status_code == 200:
            data = resp.json()
            # print("xxx", data)
            if "value" in data:
                for e in data["value"]:
                    res = e.get("extensions", {}).get("state", None)
                    if res is None:
                        fail = "No data in response"
                    else:
                        res = int(res)
            else:
                fail = "No 'value' in response"
        else:
            fail = "Bad HTTP statuscode"

        if fail:
            self._raise_error(
                f"find_hosts_having_a_service invalid response: {fail}", resp
            )

        return res

    #
    # Service search
    #

    def _parse_svc_result(self, resp: requests.Response):
        res = set()
        fail = None
        if resp.status_code == 200:
            data = resp.json()
            if "value" in data:
                for e in data["value"]:
                    dct = e.get("extensions", {})
                    h = dct.get("host_name")
                    s = dct.get("display_name")
                    if h and s:
                        res.add((h, s))
                    else:
                        fail = "Missing keys in reponse"
                        break
            else:
                fail = "No value in response"
        else:
            fail = "Bad HTTP statuscode"

        if fail:
            self._raise_error(f"get_services invalid response: {fail}", resp)

        return list(res)

    def find_services(
        self,
        name_regex: str,
        optional_identifier: Optional[str],
        case_insensitive: bool,
    ) -> Iterable[Tuple[str, str]]:
        """Find service with names containing contains_str or matching
        an optional identifier.
        Return list of tuples (host_name, service_name)
        """

        # Was :
        # LqlGetDependentHostsServices_OptionalIdentifier = "Filter: display_name ~~ " + optional_identifier + "\nOr: 2\n"
        # and
        # LqlGetDependentHostsServices = "GET services\nFilter: display_name ~~ " + host_name + "\n" + LqlGetDependentHostsServices_OptionalIdentifier + "Columns: host_name display_name\n"

        op = "~" if not case_insensitive else "~~"

        if optional_identifier:
            opt_id_query = f', {{ "op": "{op}", "left": "display_name", "right": "{optional_identifier}" }}'
        else:
            opt_id_query = ""

        res = []
        dct = {}
        dct["columns"] = ["display_name", "host_name"]
        dct["query"] = (
            '{"op": "or", "expr": ['
            + f'{{ "op": "{op}", "left": "display_name", "right": "{name_regex}" }} '
            + opt_id_query
            + "]}"
        )
        resp = self._get("domain-types/service/collections/all", dct)

        res = self._parse_svc_result(resp)
        # dbg(f**REST Services by keyword {name_regex} / {res}")
        return res

    def find_services_by_host(
        self, host_name_regex: str, optional_identifier: Optional[str]
    ) -> Iterable[Tuple[str, str]]:
        """Find services on hosts containing the host_name or having
        its name matching an optional identifier.
        Return list of tuples (host_name, service_name)
        """
        # Was :
        # LqlGetDependentServicesOnParent_OptionalIdentifier = "Filter: display_name ~ " + optional_identifier + "\nOr: 2\n"
        # and
        # LqlGetDependentServicesOnParent = "GET services\nFilter: host_name ~ " + parent_host + "\nFilter: display_name ~ " + host_name + "\n" + LqlGetDependentServicesOnParent_OptionalIdentifier + "Columns: host_name display_name\n"

        op = "~"  # if not case_insensitive else "~~"
        res = []

        if optional_identifier:
            opt_id_query = f', {{ "op": "{op}", "left": "display_name", "right": "{optional_identifier}" }}'
        else:
            opt_id_query = ""

        dct = {}
        dct["columns"] = ["display_name", "host_name"]
        dct["query"] = (
            '{"op": "or", "expr": ['
            + f'{{ "op": "{op}", "left": "host_name", "right": "{host_name_regex}" }} '
            + opt_id_query
            + "]}"
        )
        resp = self._get("domain-types/service/collections/all", dct)

        res = self._parse_svc_result(resp)
        # dbg(f"**REST Services by hostname filter {host_name_regex} / {res}")
        return res

    def get_services(self) -> Iterable[Tuple[str, str]]:
        res = []
        dct = {}
        dct["columns"] = ["display_name", "host_name", "host_alias", "host_labels"]
        resp = self._get("domain-types/service/collections/all", dct)

        if resp.status_code == 200:
            data = resp.json()
            if "value" in data:
                for e in data["value"]:
                    nam = e.get("extensions", {}).get("display_name")
                    hnam = e.get("extensions", {}).get("host_name")
                    halias = e.get("extensions", {}).get("host_alias")
                    site = (
                        e.get("extensions", {})
                        .get("host_labels", {})
                        .get("cmk/site", "")
                    )
                    if nam and hnam and site:
                        hid = HostId(hnam, halias, site)
                        res.append(SvcInfo(nam, hid))
        else:
            self._raise_error("get_services", resp)

        # dbg(f"**REST Services {res} {resp}")
        return res

    def get_service_check_interval(
        self, host_name: str, svc_name: str
    ) -> Optional[int]:
        """Return normal check interval in minutes"""

        # Was :
        # LqlGetNormalCheckIntervalMaintenance = "GET services\nFilter: host_name ~ ^" + host_name + "$\nFilter: display_name ~ ^" + display_service_name + "$\nColumns: check_interval\n"

        res = []
        dct = {}
        dct["columns"] = ["check_interval"]
        # both eq was "~" in previous versions an hostname-right "^{hostname}$"
        dct["query"] = (
            '{"op": "and", "expr": ['
            + f'{{ "op": "=", "left": "host_name", "right": "{host_name}" }}, '
            + f'{{ "op": "=", "left": "display_name", "right": "{svc_name}" }} '
            + "]}"
        )
        resp = self._get("domain-types/service/collections/all", dct)
        # dbg(f"**** {resp}")
        res = None
        fail = None
        if resp.status_code == 200:
            data = resp.json()
            # dbg(f"**** {data}, {host_name} {svc_name}")
            if "value" in data:
                if len(data["value"]) > 0:
                    res = (
                        data["value"][0]
                        .get("extensions", {})
                        .get("check_interval", None)
                    )
                    if res is None:
                        fail = "No data in response"
                    else:
                        res = int(res)
            else:
                fail = "No value in response"
        else:
            fail = "Bad HTTP statuscode"

        if fail:
            self._raise_error(f"get_services invalid response: {fail}", resp)

        # dbg(f"**REST CheckInterval {res}")
        return res

    def get_service_state(self, host_name: str, svc_name: str) -> Optional[int]:
        """Return state of service"""
        res = []
        dct = {}
        dct["columns"] = ["state"]
        # both eq was "~" in previous versions an hostname-right "^{hostname}$"
        dct["query"] = (
            '{"op": "and", "expr": ['
            + f'{{ "op": "=", "left": "host_name", "right": "{host_name}" }}, '
            + f'{{ "op": "=", "left": "display_name", "right": "{svc_name}" }} '
            + "]}"
        )
        resp = self._get("domain-types/service/collections/all", dct)
        # dbg(f"**** {resp}")
        res = None
        fail = None
        if resp.status_code == 200:
            data = resp.json()
            # dbg(f"**** {data}, {host_name} {svc_name}")
            if "value" in data:
                if len(data["value"]) > 0:
                    res = data["value"][0].get("extensions", {}).get("state", None)
                    if res is None:
                        fail = "No data in response"
                    else:
                        res = int(res)

            else:
                fail = "No value in response"
        else:
            fail = "Bad HTTP statuscode"

        if fail:
            self._raise_error(f"get_services invalid response: {fail}", resp)

        # dbg(f"**REST CheckInterval {res}")
        return res
