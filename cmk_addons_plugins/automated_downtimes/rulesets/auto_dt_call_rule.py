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
#                      by michael.hoess@sva.de


from typing import Dict

from cmk.rulesets.v1 import Help, Label, Title
from cmk.rulesets.v1.form_specs import (
    DictGroup,
    DictElement,
    Dictionary,
    BooleanChoice,
    RegularExpression,
    MatchingScope,
    Integer,
    ServiceState,
    CascadingSingleChoice,
    CascadingSingleChoiceElement,
    List,
    String,
    DefaultValue,
    Password,
)
from cmk.rulesets.v1.rule_specs import ActiveCheck, Topic

from cmk.rulesets.v1.form_specs.validators import NumberInRange

import logging

MONITOR_GROUP = DictGroup(title=Title("Monitor"))
TARGET_GROUP = DictGroup(title=Title("Dependency/Target selection"))
API_GROUP = DictGroup(title=Title("API access"))


def _migrate(dct: Dict) -> Dict:

    #logging.critical(f"   IN {dct}")
    
    monitor = dct.get("monitor")    
    if isinstance(monitor, str):
        dct["monitor"] = ("host", monitor)
        
    elif isinstance(monitor, tuple) and len(monitor) >= 4:        
        new_vals = {
            "host_name": monitor[0],
            "service_name": monitor[1],
            "service_output_regex": monitor[2],                       
        }        
        if len(monitor[3]) > 0:
             use_perfdata = monitor[3]
             if "timerange" in use_perfdata:
                new_vals["use_perfadata"] =  {
                    "timerange_start": use_perfdata["timerange"][0],
                    "timerange_end": use_perfdata["timerange"][1],
                    "set_dt_flag": use_perfdata.get("set_dt_flag"),
                }
        dct["monitor"] = ("service", new_vals)

    dep_detect = dct.get("dependency_detection")        
    if isinstance(dep_detect, tuple) and len(dep_detect) > 1:
        if dep_detect[0] == "fully_automated" and isinstance(dep_detect[1], str):
            # Convert old format to new format
            dct["dependency_detection"] = (
                "fully_automated", {
                    "optional_identifier": dep_detect[1] if len(dep_detect) > 1 else "",
                }
            )
        elif dep_detect[0] == "specify_targets" and isinstance(dep_detect[1], list):            
            new_vals = {
                "targets": [
                    {
                        "target_id": target[0],
                        "host_name_regex": target[1][0],
                        "service_name_regex": target[1][1] if len(target[1]) >= 2 else None,                        
                    }
                    for target in dep_detect[1]
                ]
            }
            dct["dependency_detection"] = ("specify_targets", new_vals)

    connect_to = dct.get("connect_to")
    if isinstance(connect_to, tuple) and len(connect_to > 0):
        new_vals = {
            "host": connect_to[0],
            "port": connect_to[1],
            "site": connect_to[2],
            "ssl_verify": connect_to[3],
            "disable_proxies": connect_to[4],
        }
        dct["connect_to"] = new_vals


    # ealier updates form reference
    """
    if dct:        
        # Update react on stuff
        # dct.setdefault("monitor_dts", True),
        # dct.setdefault("monitor_state_1", False),
        # dct.setdefault("monitor_state_2", False),
        # dct.setdefault("monitor_state_3", False),
        dct.setdefault(
            "react_on",
            {
                "monitor_dts": dct.get("monitor_dts", True),
                "monitor_state_1": dct.get("monitor_state_1", False),
                "monitor_state_2": dct.get("monitor_state_2", False),
                "monitor_state_3": dct.get("monitor_state_3", False),
            },
        )
        for k in [
            "monitor_dts",
            "monitor_state_1",
            "monitor_state_2",
            "monitor_state_3",
        ]:
            if k in dct:
                del dct[k]

        # Update search-option-stuff:

        # dct.setdefault("strip_fqdn", False),
        # dct.setdefault("case_insensitive", False)
        # dct.setdefault("hostname_boundary_match", True)

        dct.setdefault(
            "search_opts",
            {
                "case_insensitive": dct.get("case_insensitive", False),
                "hostname_boundary_match": dct.get("hostname_boundary_match", True),
                "strip_fqdn": dct.get("strip_fqdn", False),
            },
        )

        for k in [
            "case_insensitive",
            "hostname_boundary_match",
            "strip_fqdn",
        ]:
            if k in dct:
                del dct[k]

        # Update THISHOST
        if dct.get("monitor") == 100:
            dct["monitor"] = "$HOSTNAME$"

        # Update monitor by service
        m = dct.get("monitor")
        if type(m) == str:
            dct["monitor"] = {"host": m}
        elif type(m) == tuple:
            new_dct = {
                "host_name": m[0],
                "service_name": m[1],
                "serivce_output_regex": m[2] if len(m) > 2 else None,
                "use_perfadata": {
                    "timerange_start": m[3] if len(m) > 3 else None,
                    "timerange_end": m[4] if len(m) > 4 else None,
                    "set_dt_flag": m[5] if len(m) > 5 else None,
                },
            }

            if len(m) > 3 and isinstance(m[3], dict):
                # If the 4th element is a dict, we assume it contains the timerange and set_dt_flag
                new_dct["use_perfadata"] = {
                    "timerange_start": (
                        m[3].get("timerange")[0] if "timerange" in m[3] else None
                    ),
                    "timerange_end": (
                        m[3].get("timerange")[1] if "timerange" in m[3] else None
                    ),
                    "set_dt_flag": m[3].get("set_dt_flag"),
                }
            dct["monitor"] = new_dct

        # Update/set defaults on other stuff

        dct.setdefault("debug_log", False),

        if tup := dct.get("connect_to"):
            if len(tup) < 5:
                dct["connect_to"] = tup + (False,)

        fa = dct.get("dependency_detection", ())
        if len(fa) == 3 and fa[0] == "fully_automated":
            dct["dependency_detection"] = (fa[0], fa[2])
    """
    
    #logging.critical(f"OUT {dct}")
    return dct


def _monitor_host_sub_form() -> CascadingSingleChoiceElement[str]:
    return CascadingSingleChoiceElement(
        name="host",
        title=Title("Host"),
        parameter_form=String(
            title=Title("Host Name"),
            help_text=Help(
                "Name of the host to monitor. "
                "Name of the host to monitor. Macros like $HOSTNAME$ can be used"
            ),
        ),
    )


def _monitor_service_sub_form() -> CascadingSingleChoiceElement[str]:
    return CascadingSingleChoiceElement(
        name="service",
        title=Title("Monitor a service"),
        parameter_form=Dictionary(
            elements={
                "host_name": DictElement(
                    parameter_form=String(
                        title=Title("Host of the service"),
                    ),
                    required=True,
                ),
                "service_name": DictElement(
                    parameter_form=String(
                        title=Title("Name of the service"),
                    ),
                    required=True,
                ),
                "service_output_regex": DictElement(
                    parameter_form=RegularExpression(
                        predefined_help_text=MatchingScope.INFIX,
                        title=Title("Trigger on specific service output (optional)"),
                        help_text=Help(
                            "Specify service output text that should trigger a downtime, e.g. <tt>System is running Maintenance mode</tt>.<br>"
                            "To capture start/end dates from the output, use a regex like: <tt>End (?P<END>.+), start at (?P<START>.+).</tt> (times must be in ISO format).<br>"
                        ),
                    ),
                    required=False,
                ),
                "use_perfadata": DictElement(
                    required=False,
                    parameter_form=Dictionary(
                        title=Title("Read times from perfdata (-> inline-help!)"),
                        help_text=Help(
                            "This feature only works if '<tt>Set downtime on service output</tt>' is enabled.<br> Downtimes are set when the current time is within the perfdata timestamps (±10 minutes).<br> Note: This disables regex-based star/end-time capturing from the plugin output above."
                        ),
                        elements={
                            "timerange_start": DictElement(
                                parameter_form=String(
                                    title=Title("Start time perfdata name"),
                                    help_text=Help(
                                        "Perfdata must contains unix-timestamps",
                                    ),
                                ),
                                required=True,
                            ),
                            "timerange_end": DictElement(
                                parameter_form=String(
                                    title=Title("End time perfdata name"),
                                    help_text=Help(
                                        "Perfdata must contains unix-timestamps",
                                    ),
                                ),
                                required=True,
                            ),
                            "set_dt_flag": DictElement(
                                parameter_form=String(
                                    title=Title(
                                        "Name of value containing flag for setting downtimes"
                                    ),
                                    help_text=Help(
                                        "Allows optionally to suppres setting a downtime, even when the timerange above suggests setting a downtime.",
                                    ),
                                ),
                                required=False,
                            ),
                        },
                    ),
                ),
            },
        ),
    )


def _react_on_sub_form() -> Dictionary:
    return Dictionary(
        title=Title("Trigger on status/event"),
        help_text=Help(
            "By default, downtimes are set when the monitored host or service is in downtime. Here you can define alternative conditions or triggers for setting downtimes."
        ),
        elements={
            "monitor_dts": DictElement(
                parameter_form=BooleanChoice(
                    title=Title("downtimes + output matches"),
                    label=Label("Enable"),
                    prefill=DefaultValue(True),
                ),
            ),
            "monitor_state_1": DictElement(
                parameter_form=BooleanChoice(
                    title=Title("state WARN/DOWN"),
                    label=Label("Enable"),
                    prefill=DefaultValue(False),
                ),
            ),
            "monitor_state_2": DictElement(
                parameter_form=BooleanChoice(
                    title=Title("state CRIT/UNREACH"),
                    label=Label("Enable"),
                    prefill=DefaultValue(False),
                ),
            ),
            "monitor_state_3": DictElement(
                parameter_form=BooleanChoice(
                    title=Title("state UNKNOWN"),
                    label=Label("Enable"),
                    prefill=DefaultValue(False),
                ),
            ),
        },
    )  #


def _detection_mode_fully_automated_sub_form() -> CascadingSingleChoiceElement[str]:
    return CascadingSingleChoiceElement(
        name="fully_automated",
        title=Title("Fully automated"),
        parameter_form=Dictionary(
            help_text=Help(
                """In this mode the following host/services are selected for setting downtimes<br>($HOSTNAME$==host running this check)<br>
        Set host-downtimes on:<br>
        &nbsp;&nbsp;- child-hosts of $HOSTNAME$.<br>
        &nbsp;&nbsp;- hosts having name of $HOSTNAME$ in their name<br>
        &nbsp;&nbsp;- $HOSTNAME$ if 'monitor by service' is specified<br>
        Set service-downtimes on:<br>
        &nbsp;&nbsp;- service having name of $HOSTNAME$ or the optional_identifier in their name"""
            ),
            elements={
                "optional_identifier": DictElement(
                    parameter_form=String(
                        title=Title("Optional identifier"),
                        help_text=Help(
                            "Specify an additional identifier. Regex in non-anchored. Matching service names are included in the set of dependencies for setting into downtimes."
                        ),
                    ),
                    required=True,
                ),
            },
        ),
    )


def _detection_mode_manual_sub_form() -> CascadingSingleChoiceElement[str]:
    return CascadingSingleChoiceElement(
        name="specify_targets",
        title=Title("Manual selection"),
        # help_text=Help("Specify dependencies/targets manually"),
        parameter_form=Dictionary(
            elements={
                "targets": DictElement(
                    parameter_form=List(
                        title=Title("Target hosts/services"),
                        help_text=Help("specify dependencies/targets manually. "),
                        element_template=Dictionary(
                            elements={
                                "target_id": DictElement(
                                    parameter_form=String(
                                        title=Title("Target id"),
                                        help_text=Help("Just a name/info for the user"),
                                    ),
                                    required=True,
                                ),
                                "host_name_regex": DictElement(
                                    parameter_form=RegularExpression(
                                        predefined_help_text=MatchingScope.INFIX,
                                        title=Title("Host name regex"),
                                    ),
                                    required=True,
                                ),
                                "service_name_regex": DictElement(
                                    parameter_form=RegularExpression(
                                        predefined_help_text=MatchingScope.INFIX,
                                        title=Title("Service name regex"),
                                    ),
                                    required=True,
                                ),
                            }
                        ),
                    ),
                ),
            },
        ),
    )


def _search_opts_sub_form() -> Dictionary:
    return Dictionary(
        title=Title("Search Options"),
        help_text=Help(
            "These options influence the behavior while searching for dependencies"
        ),
        elements={
            "case_insensitive": DictElement(
                parameter_form=BooleanChoice(
                    title=Title("Case-insensitive host search"),
                    help_text=Help(
                        "Normally searches for dependencies are case-sensitive. "
                    ),
                    label=Label("Enable"),
                    prefill=DefaultValue(False),
                ),
                required=True,
            ),
            "hostname_boundary_match": DictElement(
                parameter_form=BooleanChoice(
                    title=Title("Match hostname boundaries"),  #
                    help_text=Help(
                        "When unchecked for a given host 'demo2'  similar hosts like 'demo21' and 'demo2-idrac' would be selected. Otherwise only hosts like 'demo2-idrac' are selected"
                    ),
                    label=Label("Enable"),
                    prefill=DefaultValue(True),
                ),
                required=True,
            ),
            "strip_fqdn": DictElement(
                parameter_form=BooleanChoice(
                    title=Title("Strip FQDN from hostnames"),
                    label=Label("Enable"),
                    help_text=Help(
                        "The domain-part of a hostname can be ignored, e.g. when searching for a host in service names"
                    ),
                    prefill=DefaultValue(False),
                ),
                required=True,
            ),
        },
    )


def _api_access_sub_form() -> Dictionary:
    return Dictionary(
        title=Title("API Access to central site"),
        help_text=Help(
            "In distributed/multi-site environments the host/instance to connect to must be manually specified. "
            + "By default localhost, $OMD_SITE, 443 are used",
        ),
        elements={
            "host": DictElement(
                parameter_form=String(
                    title=Title("Host to connect to"),
                    help_text=Help(
                        "Hostname or IP address of the host to connect to. "
                        "This is usually the central site in a distributed setup. "
                    ),
                ),
                required=True,
            ),
            "port": DictElement(
                parameter_form=Integer(
                    title=Title("Port to connect to"),
                    help_text=Help(
                        "Port of the host to connect to. "
                        "When using ports in range 5xxx-5999, TLS is automatcally disabled (works only on localhost)"
                    ),
                    prefill=DefaultValue(443),
                    custom_validate=[NumberInRange(
                        min_value=1,
                        max_value=65535,
                        error_msg="Port must be between 1 and 65535",
                    )],
                ),
                required=True,
            ),
            "site": DictElement(
                parameter_form=String(
                    title=Title("Site to connect to"),
                    help_text=Help("Name of the site to connect to. "),
                ),
                required=True,
            ),
            "ssl_verify": DictElement(
                parameter_form=BooleanChoice(
                    title=Title("Verify SSL certificate"),
                    help_text=Help(
                        "If enabled, the SSL certificate of the host is verified. "
                        "This is recommended for production environments. "
                    ),
                    prefill=DefaultValue(False),
                )
            ),
            "disable_proxies": DictElement(
                parameter_form=BooleanChoice(
                    title=Title("Disable use of system proxies"),
                    help_text=Help(
                        "Do not use proxies defined e.g. via proxy-env-vars"
                    ),
                    prefill=DefaultValue(False),
                ),
            ),
        },
    )


def _form_auto_downtimes() -> Dictionary:
    return Dictionary(
        migrate=_migrate,
        title=Title("Automated Downtimes"),
        help_text=Help(
            """
    Automatically set downtimes on hosts/services based on the downtime, state, or output of other hosts/services.<br><br>
    Most input fields (hostnames, service names, display names) support macros.<br><br>
    You can also use regex replacements in these fields, e.g.:<br>
    'Tunnel {{$HOSTNAME$~~([0-9]).*~~\\1}}'<br>
    Format: 'Text~~Regex w/ capture-groups~~Result \\1 \\2 ...' (\\1, \\2, etc. contain contents of capture groups).
    <br><br>
    Enable inline help for more information on the individual fields!
"""
        ),
        elements={
            "display_service_name": DictElement(
                parameter_form=String(
                    title=Title("Name of service"),
                    help_text=Help(
                        "Name of the service to create",
                    ),
                ),
                required=True,
            ),
            "monitor": DictElement(
                parameter_form=CascadingSingleChoice(
                    title=Title("Host/services to monitor"),
                    elements=[_monitor_host_sub_form(), _monitor_service_sub_form()],
                ),
                required=True,
                group=MONITOR_GROUP,
            ),
            "react_on": DictElement(
                parameter_form=_react_on_sub_form(),
                group=MONITOR_GROUP,
            ),
            "dependency_detection": DictElement(
                parameter_form=CascadingSingleChoice(
                    title=Title("Mode for finding downtime targets"),
                    elements=[
                        _detection_mode_fully_automated_sub_form(),
                        _detection_mode_manual_sub_form(),
                    ],
                ),
                required=True,
                group=TARGET_GROUP,
            ),
            "search_opts": DictElement(
                parameter_form=_search_opts_sub_form(),
                group=TARGET_GROUP,
            ),
            "dt_end_gracetime_s": DictElement(
                parameter_form=Integer(
                    title=Title("Grace time in seconds before downtime removal"),
                    help_text=Help(
                        "If prequisite for a downtimes are not met anymore, the downtime will be removed after this time (instead of immediately)."
                    ),
                    custom_validate=[NumberInRange(
                        min_value=0,
                        max_value=3600,
                        error_msg="Grace time must be between 0 and 3600 seconds",
                    )],
                    prefill=DefaultValue(0),
                    unit_symbol="s",
                ),
                group=TARGET_GROUP,
            ),
            "default_downtime": DictElement(
                parameter_form=Integer(
                    title=Title("Default downtime in minutes"),
                    help_text=Help(
                        "Normal length of downtime, should be min. 2.5x normal check interval. Downtimes are removed earlier, if the prequisite for a downtime are not met anymore and renewed if still required. Something between 30-90 minutes is recommended to redunce the number of downtime-prolongations. This is bascially a failsafe if the plugin gets disabled for some reasons, so the downtimes will expires by themselves after this time. "
                    ),
                    custom_validate=[NumberInRange(
                        min_value=3,
                        max_value=1440,
                        error_msg="Downtime must be between 0 and 1440 minutes",
                    )],
                    prefill=DefaultValue(0),
                    unit_symbol="min",
                ),
                group=TARGET_GROUP,
            ),
            "connect_to": DictElement(
                parameter_form=_api_access_sub_form(),
                group=API_GROUP,
                required=False,
            ),
            "automation_user": DictElement(
                parameter_form=String(
                    title=Title("Automation user"),
                    help_text=Help(
                        "User to use for API access. This user must have the Read-All+Adding/Removing Downtime permission on the central site."
                    ),
                    prefill=DefaultValue("automation"),
                ),
                group=API_GROUP,
                required=True,
            ),
            "automation_password": DictElement(
                parameter_form=Password(
                    title=Title("Automation user password"),
                    help_text=Help(
                        "If unspecified, user must have the 'automation.secret'-file as in CMK < 2.4.0 was by  default."
                    ),
                ),
                group=API_GROUP,
                required=False,
            ),
            "debug_log": DictElement(
                parameter_form=BooleanChoice(
                    title=Title("Enable debug logging"),
                    help_text=Help(
                        "Enable debugging to ~/tmp/auto_downtimes.log. Only enable on problems, may fill up your filesystem and eat performance!"
                    ),
                    label=Label("Enable"),
                    prefill=DefaultValue(False),
                ),
                group=API_GROUP,
            ),
        },
    )


rule_spec_auto_downtimes = ActiveCheck(
    name="maintenance",
    title=Title("Automated Downtimes"),
    help_text=Help(
        """
    Automatically set downtimes on hosts/services based on the downtime, state, or output of other hosts/services.<br><br>
"""
    ),
    topic=Topic.GENERAL,
    parameter_form=_form_auto_downtimes,
)
