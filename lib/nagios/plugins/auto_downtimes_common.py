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


import argparse
import os
import sys
import datetime
import hashlib

from typing import Iterable, Optional
from dataclasses import dataclass

#
# Basic global vars
#

omd_root = os.getenv("OMD_ROOT")
omd_site = os.getenv("OMD_SITE")


#
# Global flags
#


FORCE_DEBUG_LOG = False

MAX_QUERY_BATCH_SIZE = 50

CACHE_LOCK = f"{omd_root}/tmp/check_mk/auto_downtimes_cache.lock"
MAX_CACHE_AGE_MINUTES = 60

#
# Global consts
#

NAGRES_OK = 0
NAGRES_CRIT = 2  # Crit
NAGRES_CRASH = 3  # Unknwon
WORD_BOUND = "(\\b|_| |$)"

#
# Debugging stuff
#

debug = False
debug_log = False


def dbg(Message):
    if debug_log or FORCE_DEBUG_LOG:
        f = open(f"{omd_root}/tmp/auto_downtimes.log", "a")
        pid = f"{os.getpid():5d}"
        f.write(
            f"[%s] [{pid}] %s\n"
            % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"), Message)
        )
        f.close()

    if debug:
        sys.stderr.write(
            "[%s] %s\n"
            % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"), Message)
        )


def set_dbg(console: bool, log: bool):
    global debug
    global debug_log
    debug = console
    debug_log = log


#
# (data) classes
#


@dataclass
class Downtime:
    id: str = None
    title: str = None
    host_name: str = None
    svc_name: Optional[str] = None
    is_svc_dt: bool = False
    start_time: datetime.datetime = None
    end_time: datetime.datetime = None
    author: str = None
    comment: str = None


@dataclass
class HostId:
    name: str
    alias: str
    site: str


@dataclass
class HostInfo:
    id: HostId
    parents: Iterable[str]
    svcs: Iterable[str]
    childs: Iterable[str]


@dataclass
class SvcInfo:
    name: str
    host: HostId


#
# Utility-functions
#


def chunks(lst: Iterable, n: int) -> Iterable[Iterable]:
    res = [lst[i * n : (i + 1) * n] for i in range((len(lst) + n - 1) // n)]
    return res


def try_strip_fqdn(fqdn: str) -> str:

    parts = fqdn.split(".")
    if len(parts) == 4:
        try:
            for p in parts:
                _ = int(p)
            # Looks like an ip
            return fqdn
        except:
            # Not an IP
            pass

    return parts[0]


#
# Argument-Parsing/Env-building
#


@dataclass
class Env:
    version = ""
    case_insensitive = False
    strip_fqdn = False
    hostname_boundary_match = True

    default_downtime = 30

    dependency_detection = None
    manual_targets = tuple()
    optional_identifier = ""

    my_host_name = None
    my_svc_name = None

    monitor_host = (None,)
    monitor_svc = (None,)
    monitor_svc_regex = (None,)
    monitor_dts = True
    monitor_states = ()

    omd_host = "localhost"
    omd_site = os.getenv("OMD_SITE")
    omd_port = 443
    no_proxy = False
    verify_ssl = False
    automation_user = "automation"
    automation_secret = None
    no_match_msg_tag = "***"  # "(!)"

    cmd_line_hash = "NONE"

    def get_my_name(self) -> str:
        return f"{self.my_host_name}--{self.my_svc_name}"


def _read_automation_secret(env: Env) -> str:

    try:
        with open(
            omd_root
            + "/var/check_mk/web/"
            + env.automation_user
            + "/automation.secret",
            "r",
        ) as automation_secret_file:
            return automation_secret_file.read().strip()
    except Exception as e:
        print(
            "! Cannot read automation secret from user %s: %s"
            % (env.automation_user, e)
        )
        sys.exit(NAGRES_CRASH)


def show_config_dump(env: Env):
    dbg("Config dump:")
    dbg("  Version/Build: %s" % (env.version))
    dbg("  OMD Host: %s" % (env.omd_host))
    dbg("  OMD Port: %s" % (env.omd_port))
    dbg("  OMD Site: %s" % (env.omd_site))
    dbg("  No Proxy SSL: %s" % (env.no_proxy))
    dbg("  Verify SSL: %s" % (env.verify_ssl))
    dbg("  Automation user: %s" % (env.automation_user))
    dbg("  Automation secret: %s" % (env.automation_secret))
    dbg("  Default downtime: %s" % (env.default_downtime))
    dbg("  My Hostname: %s" % (env.my_host_name))
    dbg("  My Service (service display name): %s" % (env.my_svc_name))
    dbg("  Dependency detection: %s" % (env.dependency_detection))
    dbg("  Case-insensitive host search: %s" % (env.case_insensitive))
    dbg("  Hostname boundary match: %s" % (env.hostname_boundary_match))
    dbg("  Strip FQDN when useful: %s" % (env.strip_fqdn))
    dbg("  Monitor host: %s" % (env.monitor_host))
    dbg("  Monitor service: %s" % (env.monitor_svc))
    dbg("  Monitor service RegEx: %s" % (env.monitor_svc_regex))
    dbg("  Monitor act on downtime: %s" % (env.monitor_dts))
    dbg(f"  Monitor act on states: {env.monitor_states}")
    dbg("  Optional identifier: %s" % (env.optional_identifier))
    dbg("  Manual targest: %s" % (str(env.manual_targets)))
    dbg(f"  CmdLine-Hash: {env.cmd_line_hash}")


def parse_args(version: str = "") -> Env:

    parser = argparse.ArgumentParser(
        prog=f"check_auto_downtimes {version}",
        description="Automated downtimes for CMK",
        exit_on_error=False,
    )

    env = Env()
    env.version = version
    parser.add_argument("--automation_user", type=str, default=env.automation_user)
    parser.add_argument(
        "--debug", action="store_true", default=False, help="Enable debug-out to stderr"
    )
    parser.add_argument(
        "--debug_log",
        action="store_true",
        default=False,
        help="Enable debug-out to log",
    )
    parser.add_argument(
        "--default_downtime",
        type=int,
        default=env.default_downtime,
        help="Set downtime-length in minutes. If downtime is nearing expiry, it will be renewed",
    )
    parser.add_argument(
        "--display_service_name",
        type=str,
        required=True,
        help="Name of the active service to be created",
    )
    parser.add_argument(
        "--host_name",
        type=str,
        required=True,
        help="Name of the host to bind our service to",
    )
    parser.add_argument(
        "--monitor_host", type=str, required=True, help="Host to monitor"
    )
    parser.add_argument(
        "--monitor_service", type=str, default=None, help="Service to monitor"
    )
    parser.add_argument(
        "--monitor_service_regex",
        type=str,
        default=None,
        help="Regex of services to monitor",
    )
    parser.add_argument(
        "--monitor_state_1",
        action="store_true",
        default=False,
        help="Act on state WARN/DOWN",
    )
    parser.add_argument(
        "--monitor_state_2",
        action="store_true",
        default=False,
        help="Act on state CRIT/UNREACH",
    )
    parser.add_argument(
        "--monitor_state_3",
        action="store_true",
        default=False,
        help="Act on state CRIT",
    )
    parser.add_argument(
        "--monitor_downtimes",
        action="store_true",
        default=True,
        help="Act on downtimes",
    )
    parser.add_argument(
        "--monitor_no_downtimes",
        action="store_true",
        default=False,
        help="Don't act on downtimes",
    )
    parser.add_argument(
        "--dependency_detection",
        type=str,
        default=None,
        choices=[
            "fully_automated",
            "search_parent_child",
            "search_child",
            "specify_targets",
        ],
        help="Also include host/svc containing this id when searching for downtime-targets",
    )
    parser.add_argument(
        "--optional_identifier",
        type=str,
        default=None,
        help="Also include host/svc containing this id when searching for downtime-targets",
    )
    parser.add_argument(
        "--target",
        type=str,
        nargs="*",
        action="append",
        help="Manual target to add for 'specify_targets'",
    )
    parser.add_argument(
        "--case_insensitive",
        action="store_true",
        default=env.case_insensitive,
        help="Do some searches case-insenstive",
    )
    parser.add_argument(
        "--no_hostname_boundary_match",
        action="store_true",
        default=False,
        help="When searching for hostname, limit search on word-boundaries",
    )
    parser.add_argument(
        "--strip_fqdn",
        default=False,
        action="store_true",
        help="Strip FQDN when searching for hosts",
    )
    parser.add_argument(
        "--omd_host",
        type=str,
        default=env.omd_host,
        help="OMD Host",
    )
    parser.add_argument(
        "--omd_site",
        type=str,
        default=env.omd_site,
        help="OMD Site",
    )
    parser.add_argument(
        "--omd_port",
        type=int,
        default=env.omd_port,
        help="OMD Port",
    )
    parser.add_argument(
        "--verify_ssl",
        default=env.verify_ssl,
        action="store_true",
        help="Verify SSL",
    )
    parser.add_argument(
        "--no_proxy",
        action="store_true",
        default=env.no_proxy,
        help="Ignore proxies",
    )

    try:
        args = parser.parse_args()
    except argparse.ArgumentError as ex:
        print(f"Invalid args: {ex}")
        sys.exit(NAGRES_CRASH)

    set_dbg(args.debug, args.debug_log)

    env.automation_user = args.automation_user
    env.hostname_boundary_match = not args.no_hostname_boundary_match
    env.case_insensitive = args.case_insensitive
    env.default_downtime = args.default_downtime
    env.my_svc_name = args.display_service_name
    env.my_host_name = args.host_name
    env.monitor_host = args.monitor_host
    env.monitor_svc = args.monitor_service
    env.monitor_svc_regex = args.monitor_service_regex
    env.monitor_dts = args.monitor_downtimes

    if args.monitor_no_downtimes:
        env.monitor_dts = False

    sts = []
    if args.monitor_state_1:
        sts.append(1)
    if args.monitor_state_2:
        sts.append(2)
    if args.monitor_state_3:
        sts.append(3)
    env.monitor_states = tuple(sts)
    env.dependency_detection = args.dependency_detection
    env.optional_identifier = args.optional_identifier
    if args.target:
        # print(args.target)
        for t in args.target:
            t = t[0]
            env.manual_targets += ((t.split(",")[0], t.split(",")[1], t.split(",")[2]),)
    env.strip_fqdn = args.strip_fqdn
    env.omd_host = args.omd_host
    env.omd_site = args.omd_site
    env.omd_port = args.omd_port
    env.verify_ssl = args.verify_ssl
    env.no_proxy = args.no_proxy
    env.automation_secret = _read_automation_secret(env)
    env.cmd_line_hash = hashlib.sha224(f"{args}".encode("utf-8")).hexdigest()

    return env
