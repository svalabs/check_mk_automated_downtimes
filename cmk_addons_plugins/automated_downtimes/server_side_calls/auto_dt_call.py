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


# def _get_dummy_ip_lookup(*hostname: str) -> Optional[str]:
#     print(hostname)
#     return hostaddress.HostAddress("127.0.0.2")


# def _get_ip_lookup_from_addr(addr: str) -> "IPLookup":
#     if not addr:
#         return None

#     return lambda *x: hostaddress.HostAddress(addr)


# def collect_macros(hostname: str, ip_lookup: "IPLookup") -> Mapping[str, str]:

#     macros = {}

#     try:
#         import cmk.base.config as _config

#         # OldStyle macro collection
#         # TODO: can this be fully replaced by host_config.macros ?
#         #

#         # try:
#         try:
#             ha = _config.get_config_cache().get_host_attributes(hostname, ip_lookup)
#         except:
#             # Hacky CMK-2.3-fallback
#             ha = _config.get_config_cache().get_host_attributes(hostname)

#         hc = _config.get_config_cache().get_host_macros_from_attributes(hostname, ha)
#         macros = hc
#     except:
#         traceback.print_exc()
#         print("Error fetching host-attributes")

#     print(macros)
#     return macros


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

    macros = host_config.macros
    # print(macros)

    # # Oldstyle macro collections, is there a difference two the host_host.macros?
    # # New macros should include macros nagios.cfg
    # try:
    #     try:
    #         addr = host_config.primary_ip_config.address
    #     except ValueError:
    #         addr = None

    #     n_macros = collect_macros(
    #         host_config.name,
    #         _get_ip_lookup_from_addr(addr),
    #     )
    #     macros.update(n_macros)
    # except Exception as e:
    #     print("Error fetching macros: " + traceback.format_exc())

    args += ["--host_name", host_config.name]

    try:
        # Temporayy add support for old params, remove after CMK 2.5
        from cmk_addons.plugins.automated_downtimes.rulesets.auto_dt_call_rule import _migrate
        params = _migrate(params)    # type: ignore
    except Exception as e:
        pass

    if "display_service_name" in params:
        args += [
            "--display_service_name",
            replace_macros(macros, params["display_service_name"]),
        ]
    
    if connect_section := params.get("connect_section"):
        if connect_to := connect_section.get("connect_to"): # type: ignore

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

        if automation_user := connect_section.get("automation_user"): # type: ignore
            args += ["--automation_user", automation_user]

        if automation_password := connect_section.get("automation_password"): # type: ignore
            args += ["--automation_password", automation_password]

        if default_downtime := connect_section.get("default_downtime"): # type: ignore
            args += ["--default_downtime", str(default_downtime)]

        if dt_end_gracetime_s := connect_section.get("dt_end_gracetime_s"): # type: ignore
            args += ["--dt_end_gracetime_s", str(dt_end_gracetime_s)]

    if params.get("debug_log"):
        args += ["--debug_log"]

    if monitor_section := params.get("monitor_section"):
        if monitor := monitor_section.get("monitor"): # type: ignore
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

                if monitor_service_regex := dct.get("service_output_regex"):
                    args += [
                        "--monitor_service_regex",
                        replace_macros(macros, monitor_service_regex),
                    ]
                
                if use_perfdata := dct.get("use_perfadata"):                
                    if perf_name_start := use_perfdata.get("timerange_start"):
                        args += ["--perfname_start", perf_name_start]

                    if perf_name_end := use_perfdata.get("timerange_end"):
                        args += ["--perfname_end", perf_name_end]

                    if perf_name_set_dt := use_perfdata.get("set_dt_flag"):
                        args += ["--perfname_set_dt", perf_name_set_dt]

        if react_on := monitor_section.get("react_on"): # type: ignore
            # If unset legacy rule assume we react on downtimes!
            if react_on.get("monitor_dts", True) == False:
                args += ["--monitor_no_downtimes"]

            if react_on.get("monitor_state_1", False):
                args += ["--monitor_state_1"]

            if react_on.get("monitor_state_2", False):
                args += ["--monitor_state_2"]

            if react_on.get("monitor_state_3", False):
                args += ["--monitor_state_3"]


    if target_section := params.get("target_section"):
        if "dependency_detection" in target_section:
            dtup = target_section["dependency_detection"] # type: ignore
            detect_mode = dtup[0]
            detect_prm = dtup[1] if len(dtup) > 1 else None

            # Pass main mode
            args += ["--dependency_detection", detect_mode]

            # Pass extra params depending on main mode
            if detect_mode == "fully_automated":
                if isinstance(detect_prm, str):  # Legacy definition, remove in 2026
                    prm = detect_prm
                else:
                    prm = detect_prm.get("optional_identifier") # type: ignore

                if prm:
                    args += ["--optional_identifier", replace_macros(macros, prm)]

            # elif detect_mode == "search_parent_child":
            #     if detect_prm:
            #         args += ["--optional_identifier", replace_macros(macros, detect_prm)]

            elif detect_mode == "specify_targets":
                for scope in detect_prm.get("targets", []): # type: ignore
                    target_name = replace_macros(macros, scope.get("target_id"))
                    target_host = replace_macros(macros, scope.get("host_name_regex"))
                    target_service = replace_macros(macros, scope.get("service_name_regex"))

                    # Fix bad spec
                    target_host = "" if target_host == "None" else target_host

                    args += [
                        "--target",
                        "%s,%s,%s" % (target_name, target_host, target_service),
                    ]
                    # if target_service.strip().startswith("sl:"):
                    #     # Touch the flag file, experimental
                    #     from cmk_addons.plugins.automated_downtimes.lib.common import svclb_flag_file, tmp_path
                    #     import os
                    #     os.makedirs(tmp_path, exist_ok=True)
                    #     with open(svclb_flag_file, "w") as f:
                    #         f.write("1")

                        
            nf_state = target_section.get("mt_state_no_targets_found") # type: ignore
            if nf_state is not None:                
                args += ["--no_target_found_state", str(nf_state)]

            search_opts = target_section.get("search_opts", {}) # type: ignore
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
    commands_function=commands_function, # type: ignore
)

# def main():
#     for a in commands_function({}, HostConfig(name="localhost")):
#         print(a)


# if __name__ == "__main__":
#     main()
