#
# GPOA - GPO Applier for Linux
#
# Copyright (C) 2021 BaseALT Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import pwd
import signal
import subprocess

from .logging import log


def set_privileges(username, uid, gid, groups, home):
    '''
    Set current process privileges
    '''

    os.environ.clear()
    os.environ['HOME'] = home
    os.environ['USER'] = username
    os.environ['USERNAME'] = username
#    os.environ['XDG_RUNTIME_DIR'] = os.path.join(home, '.gpupdate_runtime_dir')
#    os.environ['TMP'] = os.path.join(home, '.gpupdate_runtime_dir')
#    os.environ['TMPDIR'] = os.path.join(home, '.gpupdate_runtime_dir')
#    os.environ['XDG_SESSION_CLASS'] = 'user'
#    os.environ['XDG_SESSION_TYPE'] = 'tty'

    try:
        os.setgid(gid)
    except Exception as exc:
        raise Exception('Error setgid() for drop privileges: {}'.format(str(exc)))

    try:
        os.setgroups(groups)
    except Exception as exc:
        raise Exception('Error setgroups() for drop privileges: {}'.format(str(exc)))

    try:
        os.setuid(uid)
    except Exception as exc:
        raise Exception('Error setuid() for drop privileges: {}'.format(str(exc)))

    os.chdir(home)

    logdata = dict()
    logdata['uid'] = uid
    logdata['gid'] = gid
    logdata['username'] = username
    log('D37', logdata)


def with_privileges(username, func):
    '''
    Run supplied function with privileges for specified username.
    '''
    if not os.getuid() == 0:
        raise Exception('Not enough permissions to drop privileges')

    user_pw = pwd.getpwnam(username)
    user_uid = user_pw.pw_uid
    user_gid = user_pw.pw_gid
    user_groups = os.getgrouplist(username, user_gid)
    user_home = user_pw.pw_dir

    if not os.path.isdir(user_home):
        raise Exception('User home directory not exists')

    pid = os.fork()
    if pid > 0:
        log('D54', {'pid': pid})
        waitpid, status = os.waitpid(pid, 0)

        if status != 0:
            raise Exception('Error in forked process ({})'.format(status))

        return

    # We need to return child error code to parent
    result = 0
    dbus_pid = -1
    try:

        # Drop privileges
        set_privileges(username, user_uid, user_gid, user_groups, user_home)

        # Run the D-Bus session daemon in order D-Bus calls to work
        proc = subprocess.Popen(
            'dbus-launch',
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        for var in proc.stdout:
            sp = var.decode('utf-8').split('=', 1)
            os.environ[sp[0]] = sp[1][:-1]

        dbus_pid = int(os.environ['DBUS_SESSION_BUS_PID'])

        # Run user appliers
        func()

    except Exception as exc:
        logdata = dict()
        logdata['msg'] = str(exc)
        log('E99', logdata)
        result = 1;
    finally:
        if dbus_pid > 0:
            os.kill(dbus_pid, signal.SIGHUP)

    sys.exit(result)

