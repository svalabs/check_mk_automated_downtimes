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


from typing import Dict, Optional, Any

from cmk.gui.i18n import _
from cmk.gui.plugins.wato import rulespec_registry


try:
    # V2.2 API
    from cmk.gui.plugins.wato.active_checks.common import (
        RulespecGroupActiveChecks,
    )
except:
    # V2.1 API
    from cmk.gui.plugins.wato.active_checks import (
        RulespecGroupActiveChecks,
    )


from cmk.gui.valuespec import (
    Alternative,
    Checkbox,
    Dictionary,
    FixedValue,
    Integer,
    ListOf,
    Hostname,
    TextAscii,
    Transform,
    RegExp,
    Tuple,
)

from cmk.gui.watolib.rulespecs import (
    HostRulespec,
)

try:
    from cmk.utils.version import get_general_version_infos

    v = get_general_version_infos().get("version").startswith("2.3")
    IS_23PRE = v.startswith("2.2") or v.startswith("2.1")
except:
    IS_23PRE = True


def CB(
    title: str, default_value: Optional[Any], help: Optional[str] = None
) -> Checkbox:
    if IS_23PRE:
        return Checkbox(
            title=title, label="Enable", default_value=default_value, help=help
        )
    else:
        return Checkbox(label=title, title=None, default_value=default_value, help=help)


_valuespec_react_on = Dictionary(
    title="React on",
    elements=[
        (
            "monitor_dts",
            CB(
                title="downtimes + output-matches",
                default_value=True,
            ),
        ),
        (
            "monitor_state_1",
            CB(title="state WARN/DOWN", default_value=False),
        ),
        (
            "monitor_state_2",
            CB(title="state CRIT/UNREACH", default_value=False),
        ),
        (
            "monitor_state_3",
            CB(title="state UNKNOWN", default_value=False),
        ),
    ],
    optional_keys=[],
)


_valuespec_search_opts = Dictionary(
    title="Search options",
    help="These options influence the behavior while searching for dependencies",
    elements=[
        (
            "case_insensitive",
            CB(
                title=_("Case-insensitive host search"),
                default_value=False,
                help=_("Normally searching for dependencies is case-sensitive"),
            ),
        ),
        (
            "hostname_boundary_match",
            CB(
                title=_("Limit host search on word boundaries"),
                default_value=True,
                help=_(
                    "When unchecked for a given host 'demo2'  similar hosts like 'demo21' and 'demo2-idrac' would be selected. Otherwise only hosts like 'demo2-idrac' are selected"
                ),
            ),
        ),
        (
            "strip_fqdn",
            CB(
                title=_("Strip FQDN on host search"),
                help=_(
                    "The domain-part of a hostname can be ignored, e.g. when searching for a host in service names"
                ),
                default_value=False,
            ),
        ),
    ],
    optional_keys=[],
)


_valuespec_maintenance_elements = [
    (
        "display_service_name",
        TextAscii(
            title=_("Display service name"),
            help=_("Name of the service to create"),
            allow_empty=False,
        ),
    ),
    # Start Monitor section
    (
        "monitor",
        Alternative(
            elements=[
                TextAscii(
                    title=_("Monitor a host"),
                    label="Hostname",
                    help=(
                        "Name of the host to monitor. Macros like $HOSTNAME$ can be used"
                    ),
                    size=40,
                ),
                # FixedValue(
                #     title=_("Monitor host=THISHOST"),
                #     help="Monitor equals $HOSTNAME (the name of host-object executing the check)",
                #     totext="THISHOST",
                #     value=100,  # Use int, won't break existing rules
                # ),
                Tuple(
                    show_titles=True,
                    title=_("Monitor a service"),
                    help=_("For sth. like ESX-Maintance-Status-serivce"),
                    orientation="vertical",
                    elements=[
                        TextAscii(
                            title=_("Host of the service"),
                            size=40,
                        ),
                        TextAscii(
                            title=_("Servicename"),
                            size=40,
                        ),
                        RegExp(
                            title=_("Set downtime on service output (optional)"),
                            mode="infix",
                            help="Instead of using service-downtime: Specify the service output which should trigger a downtime. E.g. <tt>System is running Maintenance mode</tt><br>"
                            + "Capturing start/enddates for downtime in plugin output like this: <tt>End (?P<END>.+), start at (?P<START>.+).</tt>. Times must be in ISO-Format.",
                            maxlen=80,
                        ),
                        Dictionary(
                            title=_("Read times from perfdata (-> inline-help!)"),
                            help=_(
                                "This feature currently only works, when '<tt>Set downtime on service output</tt>' is also enabled!<br>This feautre will set downtimes when the actual time is in the range of the timestamps specified in the perfdata +/- 10 minutes.<br>This feature disables the capturing-by-regex from plugin output' feature above."
                            ),
                            elements=[
                                (
                                    "timerange",
                                    Tuple(
                                        show_titles=True,
                                        title=_("Name of timerange perfvalues"),
                                        help=_(
                                            "Perfdata must contains unix-timestamps"
                                        ),
                                        orientation="horizontal",
                                        elements=[
                                            TextAscii(
                                                title=_("Name of start value"),
                                                size=40,
                                            ),
                                            TextAscii(
                                                title=_("Name of end value"),
                                                size=40,
                                            ),
                                        ],
                                    ),
                                ),
                                (
                                    "set_dt_flag",
                                    TextAscii(
                                        title=_(
                                            "Name of value containing flag for setting downtimes"
                                        ),
                                        help="Allows optionally to suppres setting a downtime, even when the timerange above suggests setting a downtime",
                                    ),
                                ),
                            ],
                            optional_keys=["timerange", "set_dt_flag"],
                        ),
                    ],
                ),
            ],
            style="dropdown",
            title=_("Automated downtime monitor"),
            help=_(
                "The auto_downtime monitor decides if a host (and its dependencies) has to enter downtime."
            ),
        ),
    ),
    (
        "react_on",
        _valuespec_react_on,
    ),
    # End of Monitor-section
    # Start Dependency detection-section
    (
        "dependency_detection",
        Alternative(
            elements=[
                Tuple(
                    title=_("Fully automated"),
                    elements=[
                        FixedValue(
                            value="fully_automated",
                            title=_("Mode:"),
                            totext="Fully automated",
                            # totext="",
                            help=_(
                                """THISHOST=host running this check<br>
                           Set host-downtimes on:<br>
                           &nbsp;&nbsp;- child-hosts of THISHOST.<br>
                           &nbsp;&nbsp;- hosts having name of THISHOST in their name<br>
                           &nbsp;&nbsp;- THISHOST if 'monitor by service' is specified<br>
                           Set service-downtimes on:<br>
                           &nbsp;&nbsp;- service having name of THISHOST or the optional_identifier in their name"""
                            ),
                        ),
                        TextAscii(
                            title=_("Additional services to include (RegEx)"),
                            allow_empty=True,
                            help=_(
                                "Specify an additional identifier. Regex in non-anchored. Matching service names are included in the set of dependencies for setting into downtimes."
                            ),
                        ),
                    ],
                ),
                # Tuple(
                #     title=_("Search for parent-services and child hosts"),
                #     elements=[
                #         FixedValue(
                #             value="search_parent_child",
                #             # title = _( "Scope" ),
                #             totext="Search for parent services and child hosts",
                #             help=_(
                #                 """THISHOST=host running this check.<br>
                #            &nbsp;&nbsp;- Set host-downtimes on child hosts of THISHOST.<br>
                #            &nbsp;&nbsp;- Set Service-downtimes on services running on <br>
                #            &nbsp;&nbsp;&nbsp;&nbsp;the parents of THISHOST matching the name of THISHOST <br>
                #            &nbsp;&nbsp;&nbsp;&nbsp;or the optional_identifier below"""
                #             ),
                #         ),
                #         TextAscii(
                #             title=_("Optional identifier"),
                #             allow_empty=True,
                #             help=_(
                #                 "Specify an optional additional identifier for searching dependencies via service descriptions"
                #             ),
                #         ),
                #     ],
                # ),
                # Tuple(
                #     title=_("Search for child hosts"),
                #     elements=[
                #         FixedValue(
                #             value="search_child",
                #             # title = _( "Scope" ),
                #             totext=_("Search for child hosts"),
                #             help=_(
                #                 "Set host-downtimes on the host running this check and its child hosts"
                #             ),
                #         ),
                #     ],
                # ),
                Tuple(
                    title=_("Manual selection"),
                    elements=[
                        FixedValue(
                            value="specify_targets",
                            title=_("Mode:"),
                            totext=_("Manual selections"),
                            help=_("Specify dependencies manually"),
                        ),
                        ListOf(
                            Tuple(
                                help=_(
                                    "Manually specify dependencies. Regexes are non-anchored"
                                ),
                                show_titles=True,
                                orientation="vertical",
                                elements=[
                                    TextAscii(
                                        title=_("Target name"),
                                        help=_("Just a name/info for the user"),
                                        forbidden_chars=",",
                                        size=40,
                                    ),
                                    Transform(
                                        Tuple(
                                            show_titles=True,
                                            orientation="vertical",
                                            elements=[
                                                TextAscii(
                                                    title=_("Host(s) RegEx"),
                                                    size=40,
                                                    forbidden_chars=",",
                                                ),
                                                TextAscii(
                                                    title=_("Service(s) RegEx"),
                                                    size=40,
                                                    forbidden_chars=",",
                                                ),
                                            ],
                                        ),
                                        # This converts a str to a tuple (str, ''), when params is a str only
                                        forth=lambda params: type(params) == str
                                        and (params, "")
                                        or params,
                                    ),
                                ],
                            ),
                            title=_("Downtimes target(s)"),
                            movable=False,
                            add_label=_("Add target"),
                        ),
                    ],
                ),
            ],
            style="dropdown",
            title=_("Dependency detection"),
            help=_(
                "How to find dependencies (hosts and/or services) which require a downtime, for example switch ports."
            ),
        ),
        # End Dependency detection-section
    ),
    (
        "search_opts",
        _valuespec_search_opts,
    ),
    (
        "dt_end_gracetime_s",
        Integer(
            title=_("Grace time in seconds before downtime removal"),
            help=_(
                "If prequisite for a downtimes are not met anymore, the downtime will be removed after this time (instead of immediately)."
            ),
            default_value=0,
            minvalue=0,
            maxvalue=3600,
            unit=_("s"),
        ),
    ),
    (
        "default_downtime",
        Transform(
            Integer(
                title=_("Default downtime in minutes"),
                help=_(
                    "Set host / services for X minutes in downtime, should be min. 2.5x normal check interval"
                ),
                default_value=30,
                minvalue=3,
                maxvalue=1440,
                unit=_("min"),
            ),
            back=lambda x: int(x),
            forth=lambda x: int(x),
        ),
    ),
    (
        "connect_to",
        Tuple(
            title=_("Connect to this central-site"),
            help=_(
                "In distributed/multi-site environments the host/instance to connect to must be manually specified. "
                + "By default localhost, $OMD_SITE, 4443 are used",
            ),
            elements=[
                TextAscii(
                    title=_("Host"),
                    help=_("Host or IP"),
                ),
                Integer(
                    title=_("Port"),
                    help=_(
                        "Note: When connecting to the instance-ports in the 5xxx-port range SSL is automatically disabled."
                    ),
                    default_value=443,
                ),
                TextAscii(
                    title=_("Site"),
                    help=_("Site/Instance name"),
                ),
                Checkbox(
                    title=_("Enable SSL verifications"),
                    default_value=False,
                    help=_("Enable verification of the provided certificate."),
                ),
                Checkbox(
                    title=_("Disable use of system-proxies"),
                    default_value=False,
                    help=_("Do not use proxies defined e.g. via proxy-env-vars"),
                ),
            ],
        ),
    ),
    (
        "automation_user",
        TextAscii(
            title=_("Automation user"),
            help=_("Automation user for API calls"),
            allow_empty=False,
        ),
    ),
    (
        "debug_log",
        Checkbox(
            title=_("Enable debugging"),
            help=_(
                "Enable debugging to ~/tmp/auto_downtimes.log. Only enable on problems, may fill up your filesystem and eat performance!"
            ),
            default_value=False,
        ),
    ),
]


def _upg_maintenance_config(dct: Dict) -> Dict:
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
        if type(m) == tuple and len(m) == 3:
            dct["monitor"] = (m[0], m[1], m[2], {})

        # Update/set defaults on other stuff

        dct.setdefault("debug_log", False),

        if tup := dct.get("connect_to"):
            if len(tup) < 5:
                dct["connect_to"] = tup + (False,)

        fa = dct.get("dependency_detection", ())
        if len(fa) == 3 and fa[0] == "fully_automated":
            dct["dependency_detection"] = (fa[0], fa[2])
    return dct


def _valuespec_activecheck_auto_downtimes():
    return Transform(
        Dictionary(
            title=_("Automated downtimes"),
            help=_(
                """
Enable/disable downtimes when maintenance state has been changed! \n\n<br>
Most test-input fields (hostnames, servicenames, display_name) support macros! 
You can also apply regexes in those fields like \n\n<br>
'Tunnel {{$HOSTNAME$~~([0-9]).*~~\\1}}' \n\n<br>
(Format: 'Text~~Regex~~Result \\1 \\2... specifying capture groups')
"""
            ),
            elements=_valuespec_maintenance_elements,
            hidden_keys=[],
            optional_keys=[
                "reference",
                "warning",
                "critical",
                "connect_to",
                "dt_end_gracetime_s",
            ],
        ),
        forth=_upg_maintenance_config,
    )


rulespec_registry.register(
    HostRulespec(
        match_type="all",
        group=RulespecGroupActiveChecks,
        name="active_checks:maintenance",
        valuespec=_valuespec_activecheck_auto_downtimes,
    )
)
