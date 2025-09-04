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
#   Copyright (C) 2025 SVA System Vertrieb Alexander GmbH
#                      by michael.hoess@sva.de + colleagues

from typing import Iterable, Optional, Tuple, Literal, Iterator, Mapping


from cmk.server_side_calls.v1 import (
    HostConfig,
    noop_parser,
    ActiveCheckCommand,
    ActiveCheckConfig,
)
from cmk.utils import hostaddress  # noqa: F401

import re, traceback


def _get_dummy_ip_lookup(*hostname: str) -> Optional[str]:
    print(hostname)
    return hostaddress.HostAddress("127.0.0.2")


def _get_ip_lookup_from_addr(addr: str) -> "IPLookup":
    if not addr:
        return None

    return lambda *x: hostaddress.HostAddress(addr)


def collect_macros(hostname: str, ip_lookup: "IPLookup") -> Mapping[str, str]:

    macros = {}

    try:
        import cmk.base.config as _config

        # try:
        try:
            ha = _config.get_config_cache().get_host_attributes(hostname, ip_lookup)
        except:
            # Hacky CMK-2.3-fallback
            ha = _config.get_config_cache().get_host_attributes(hostname)

        hc = _config.get_config_cache().get_host_macros_from_attributes(hostname, ha)
        macros = hc
    except:
        traceback.print_exc()
        print("Error fetching host-attributes")

    # print(macros)
    return macros


# replace regex macros
def process_regex(input_string: str) -> str:
    def process_single_expression(expression: str) -> str:
        # Split the expression into three parts using "~~" as the delimiter
        parts = expression.split("~~")
        if len(parts) != 3:
            print(f"Invalid regex string: {expression}")
            return f"{{{{{expression}}}}}"  # Return the original expression wrapped in {{ }}

        first_part, regex_part, third_part = parts

        # Apply the regex to the first part
        match = re.search(regex_part, first_part)
        if not match:
            return f"{{{{{expression}}}}}"  # Return the original expression wrapped in {{ }}

        # Replace \1, \2, etc., in the third part with the corresponding capture groups
        result = re.sub(r"\\(\d+)", lambda m: match.group(int(m.group(1))), third_part)
        return result

    # Find all expressions wrapped in {{ }}
    matches = re.findall(r"{{(.*?)}}", input_string)

    # Process each expression and replace it in the input string
    for match in matches:
        processed = process_single_expression(match)
        input_string = input_string.replace(f"{{{{{match}}}}}", processed)

    return input_string


# Platzhalter
def replace_macros(macros, txt):
    if not txt:
        return txt

    for k, v in macros.items():
        txt = txt.replace(k, str(v))
        txt = process_regex(txt)

    return txt


def commands_function(
    params: Mapping[str, str],
    host_config: HostConfig,
) -> Iterator[ActiveCheckCommand]:
    args = []
    try:
        try:
            addr = host_config.primary_ip_config.address
        except ValueError:
            addr = None

        macros = collect_macros(
            host_config.name,
            _get_ip_lookup_from_addr(addr),
        )
    except Exception as e:
        print("Error fetching macros: " + traceback.format_exc())
        macros = {}

    args += ["--host_name", host_config.name]

    if "display_service_name" in params:
        args += [
            "--display_service_name",
            replace_macros(macros, params["display_service_name"]),
        ]

    if connect_to := params.get("connect_to"):
        if (type(params["connect_to"]) is tuple) and (len(params["connect_to"]) == 5):
            host, port, site, verify_ssl, no_proxy = params["connect_to"]

            if host := connect_to.get("host"):
                args += ["--omd_host", host]

            if port := connect_to.get("port", 443):
                args += ["--omd_port", f"{port}"]

            if site := connect_to.get("site"):
                args += ["--omd_site", site]

            if connect_to.get("ssl_verify", False):
                args += ["--verify_ssl"]

            if connect_to.get("disable_proxies", False):
                args += ["--no_proxy"]

    if "automation_user" in params:
        args += ["--automation_user", params["automation_user"]]

    if automation_password := params.get("automation_password"):
        args += ["--automation_password", automation_password]

    if "default_downtime" in params:
        args += ["--default_downtime", str(params["default_downtime"])]

    if "dt_end_gracetime_s" in params:
        args += ["--dt_end_gracetime_s", str(params["dt_end_gracetime_s"])]

    if params.get("debug_log"):
        args += ["--debug_log"]

    if monitor := params.get("monitor"):
        if isinstance(monitor, tuple) and len(monitor) > 1 and monitor[0] == "host":
            args += [
                "--monitor_host",
                replace_macros(macros, monitor[1]),
            ]

        if isinstance(monitor, tuple) and len(monitor) > 1 and monitor[0] == "service":
            dct = monitor[1] if len(monitor) > 1 else {}

            if host_name := dct.get("host_name"):
                args += [
                    "--monitor_host",
                    replace_macros(macros, host_name),
                ]

            if service_name := dct.get("service_name"):
                args += [
                    "--monitor_service",
                    replace_macros(macros, service_name),
                ]

            if monitor_service_regex := dct.get("monitor_service_regex"):
                args += [
                    "--monitor_service_regex",
                    replace_macros(macros, monitor_service_regex),
                ]

            if use_perfdata := dct.get("use_perfdata"):
                if perf_name_start := use_perfdata.get("timerange_start"):
                    args += ["--perfname_start", perf_name_start]

                if perf_name_end := use_perfdata.get("timerange_end"):
                    args += ["--perfname_end", perf_name_end]

                if perf_name_set_dt := use_perfdata.get("set_dt_flag"):
                    args += ["--perfname_set_dt", perf_name_set_dt]

    if react_on := params.get("react_on"):
        # If unset legacy rule assume we react on downtimes!
        if react_on.get("monitor_dts", True) == False:
            args += ["--monitor_no_downtimes"]

        if react_on.get("monitor_state_1", False):
            args += ["--monitor_state_1"]

        if react_on.get("monitor_state_2", False):
            args += ["--monitor_state_2"]

        if react_on.get("monitor_state_3", False):
            args += ["--monitor_state_3"]

    if "dependency_detection" in params:
        dtup = params["dependency_detection"]
        detect_mode = dtup[0]
        detect_prm = dtup[1] if len(dtup) > 1 else None

        # Pass main mode
        args += ["--dependency_detection", detect_mode]

        # Pass extra params depending on main mode
        if detect_mode == "fully_automated":            
            if isinstance(detect_prm, str): # Legacy definition, remove in 2026
                prm = detect_prm
            else:
               prm = detect_prm.get("optional_identifier")

            if prm:
                args += ["--optional_identifier", replace_macros(macros, prm)]

        # elif detect_mode == "search_parent_child":
        #     if detect_prm:
        #         args += ["--optional_identifier", replace_macros(macros, detect_prm)]

        elif detect_mode == "specify_targets":            
            for scope in detect_prm.get("targets", []):
                target_name = replace_macros(macros, scope.get("target_id"))
                target_host = replace_macros(macros, scope.get("host_name_regex"))
                target_service = replace_macros(macros, scope.get("service_name_regex"))

                # Fix bad spec
                target_host = "" if target_host == "None" else target_host

                args += [
                    "--target",
                    "%s,%s,%s" % (target_name, target_host, target_service),
                ]

        search_opts = params.get("search_opts", {})
        if search_opts.get("hostname_boundary_match") is False:
            args += ["--no_hostname_boundary_match"]
        if search_opts.get("case_insensitive") is True:
            args += ["--case_insensitive"]
        if search_opts.get("strip_fqdn") is True:
            args += ["--strip_fqdn"]

    yield ActiveCheckCommand(
        service_description=params.get("display_service_name", "Automated Downtimes"),
        command_arguments=args,
    )


active_check_auto_downtimes = ActiveCheckConfig(
    name="maintenance",
    parameter_parser=noop_parser,
    commands_function=commands_function,
)


def main():
    for a in commands_function({}, HostConfig(name="localhost")):
        print(a)


if __name__ == "__main__":
    main()
