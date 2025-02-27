#
# GPOA - GPO Applier for Linux
#
# Copyright (C) 2025 BaseALT Ltd.
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

from .applier_frontend import (
      applier_frontend
    , check_enabled
    , check_windows_mapping_enabled
)
import struct
from datetime import datetime, timedelta
import dpapi_ng
from util.util import remove_prefix_from_keys
from util.sid import WellKnown21RID
import subprocess
import ldb
import string
import secrets
import os
import psutil

class laps_applier(applier_frontend):
    __epoch_timestamp = 11644473600
    __hundreds_of_nanoseconds = 10000000
    __day_float = 8.64e11
    __module_name = 'LapsApplier'
    __module_experimental = True
    __module_enabled = False
    __all_win_registry = 'SOFTWARE/Microsoft/Windows/CurrentVersion/Policies/LAPS/'
    __registry_branch = 'Software/BaseALT/Policies/Laps/'
    __attr_EncryptedPassword = 'msLAPS-EncryptedPassword'
    __attr_PasswordExpirationTime = 'msLAPS-PasswordExpirationTime'
    __key_passwordLastModified = '/Software/BaseALT/Policies/Laps/PasswordLastModified/'


    def __init__(self, storage):
        self.storage = storage
        all_alt_keys = remove_prefix_from_keys(storage.filter_entries(self.__registry_branch), self.__registry_branch)
        self.all_keys = remove_prefix_from_keys(storage.filter_entries(self.__all_win_registry), self.__all_win_registry)
        self.all_keys.update(all_alt_keys)

        self.backup_directory = self.all_keys.get('BackupDirectory', None)
        encryption_enabled = self.all_keys.get('ADPasswordEncryptionEnabled', 1)
        if self.backup_directory != 2 and encryption_enabled == 1:
            self.__module_enabled = False
            print('backup_directory', self.backup_directory, encryption_enabled)
            return
        self.password_expiration_protection = self.all_keys.get('PasswordExpirationProtectionEnabled', 1)
        self.samdb = storage.get_info('samdb')
        domain_sid = self.samdb.get_domain_sid()
        self.domain_dn = self.samdb.domain_dn()
        self.computer_dn = self.get_computer_dn()
        self.admin_group_sid = f'{domain_sid}-{WellKnown21RID.DOMAIN_ADMINS.value}'
        self.password_age_days = self.all_keys.get('PasswordAgeDays', 30)
        self.expiration_date = self.get_expiration_date()
        self.expiration_date_int = self.get_int_time(self.expiration_date)
        self.dt_now_int = self.get_int_time(datetime.now())
        self.expiration_time_attr = self.get_expiration_time_attr()
        self.pass_last_mod_int = self.read_dconf_pass_last_mod()
        self.post_authentication_actions = self.all_keys.get('PostAuthenticationActions', 2)
        self.post_authentication_reset_delay = self.all_keys.get('PostAuthenticationResetDelay', 24)
        self.target_user = self.get_target_user()
        self.encryption_principal = self.get_encryption_principal()
        self.last_login_hours_ago = self.get_last_login_hours_ago(self.target_user)


        self.__module_enabled = check_enabled(
              self.storage
            , self.__module_name
            , self.__module_experimental
        )
    def get_target_user(self):
        return self.all_keys.get('AdministratorAccountName', 'root')


    def wbinfo_check_encryption_principal(self, encryption_principal):
        try:
            domain = self.storage.get_info('domain')
            username = f'{domain}\\{encryption_principal}'
            wbinfo_cmd = ['wbinfo', '-n', username]
            output = subprocess.check_output(wbinfo_cmd)
            sid = output.split()[0].decode('utf-8')
            return sid
        except subprocess.CalledProcessError:
            wbinfo_cmd = ['wbinfo', '-s', encryption_principal]
        try:
            output = subprocess.check_output(wbinfo_cmd)
            return encryption_principal
        except:
            return self.admin_group_sid


    def get_password(self):
        password_length = self.all_keys.get('PasswordLength', 14)
        if not isinstance(password_length, int) or not (8 <= password_length <= 64):
            password_length = 14

        password_complexity = self.all_keys.get('PasswordComplexity', 4)
        if not isinstance(password_complexity, int) or not (1 <= password_complexity <= 4):
            password_complexity = 4

        char_sets = {
            1: string.ascii_uppercase,
            2: string.ascii_letters,
            3: string.ascii_letters + string.digits,
            4: string.ascii_letters + string.digits + string.punctuation
        }

        char_set = char_sets.get(password_complexity, char_sets[4])

        password = self.generate_password(char_set, password_length)

        if password_complexity >= 3 and not any(c.isdigit() for c in password):
            digit = secrets.choice(string.digits)
            position = secrets.randbelow(len(password))
            password = password[:position] + digit + password[position:]

        if password_complexity == 4 and not any(c in string.punctuation for c in password):
            special_char = secrets.choice(string.punctuation)
            position = secrets.randbelow(len(password))
            password = password[:position] + special_char + password[position:]
        return password


    def generate_password(self, char_set, length):
        password = ''.join(secrets.choice(char_set) for _ in range(length))
        return password

    def get_last_login_hours_ago(self, username):
        try:
            output = subprocess.check_output(["last", "-n", "1", username], env={'LANG':'C'}, text=True).split("\n")[0]
            parts = output.split()

            if len(parts) < 7:
                return 0

            login_str = f"{parts[4]} {parts[5]} {parts[6]}"
            last_login_time = datetime.strptime(login_str, "%b %d %H:%M")
            last_login_time = last_login_time.replace(year=datetime.now().year)
            time_diff = datetime.now() - last_login_time
            return int(time_diff.total_seconds() // 3600)

        except Exception as e:
            print('Dlog', e)
            return 0

    def get_changed_password_hours_ago(self):
        try:
            diff_time =  self.dt_now_int - self.pass_last_mod_int
            hours_difference = diff_time // 3.6e10
            return int(hours_difference)
        except:
            return 0

    def __change_root_password(self, new_password):
        try:
            process = subprocess.Popen(
                ["chpasswd"], stdin=subprocess.PIPE, text=True
            )
            process.communicate(f"{self.target_user}:{new_password}")
            self.write_dconf_pass_last_mod()
            print("Dlog")
        except Exception as e:
            print(f"Dlog {e}")

    def get_encryption_principal(self):
        encryption_principal = self.all_keys.get('ADPasswordEncryptionPrincipal', None)
        sid = (self.wbinfo_check_encryption_principal(encryption_principal)
               if encryption_principal
               else self.admin_group_sid)
        return sid

    def get_json_pass(self, psw):
        return f'{{"n":"{self.target_user}","t":"{self.expiration_date_int}","p":"{psw}"}}'

    def get_expiration_date(self, dt = None):
        if not dt:
            return (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                    + timedelta(days=int(self.password_age_days)))
        else:
            return(dt.replace(hour=0, minute=0, second=0, microsecond=0)
                    + timedelta(days=int(self.password_age_days)))

    def get_int_time(self, datetime):
        epoch_timedelta = timedelta(seconds=self.__epoch_timestamp)
        new_dt = datetime + epoch_timedelta
        return int(new_dt.timestamp() * self.__hundreds_of_nanoseconds)

    def get_full_blob(self, dpapi_ng_blob):
        left,right = struct.unpack('<LL',struct.pack('Q', self.dt_now_int))
        packed = struct.pack('<LL',right,left)
        prefix = packed + struct.pack('<i', len(dpapi_ng_blob)) + b'\x00\x00\x00\x00'
        full_blob = prefix + dpapi_ng_blob
        return full_blob

    def get_computer_dn(self):
        machine_name = self.storage.get_info('machine_name')
        search_filter = f'(sAMAccountName={machine_name})'
        results = self.samdb.search(base=self.domain_dn, expression=search_filter, attrs=['dn'])
        return results[0]['dn']

    def get_expiration_time_attr(self):
        try:
            res = self.samdb.search(base=self.computer_dn,
                        scope=ldb.SCOPE_BASE,
                        expression="(objectClass=*)",
                        attrs=[self.__attr_PasswordExpirationTime])

            int_data = int(res[0].get(self.__attr_PasswordExpirationTime, 0)[0])

        except Exception as e:
            int_data = 0
        return int_data


    def write_dconf_pass_last_mod(self):
        try:
            dbus_address = os.getenv("DBUS_SESSION_BUS_ADDRESS")
            if not dbus_address:
                result = subprocess.run(["dbus-daemon", "--fork", "--session", "--print-address"], capture_output=True, text=True)
                dbus_address = result.stdout.strip()
                os.environ["DBUS_SESSION_BUS_ADDRESS"] = dbus_address
            LastModified = f'"{self.dt_now_int}"'
            subprocess.check_output(['dconf', 'write', self.__key_passwordLastModified+self.target_user, LastModified])
        except Exception as exc:
            print('Dlog', exc)

    def read_dconf_pass_last_mod(self):
        try:
            last_modified = subprocess.check_output(['dconf', 'read', self.__key_passwordLastModified+self.target_user], text=True).split("\n")[0]
            last_modified = int(last_modified.strip("'\""))
        except Exception as exc:
            last_modified = self.dt_now_int
        return last_modified


    def terminate_user_sessions(self):
        """
        Terminates all processes associated with the active sessions of the specified user.
        Sessions are retrieved using psutil.users().
        """
        # Get a list of active sessions for the given user
        user_sessions = [user for user in psutil.users() if user.name == self.target_user]

        if not user_sessions:
            return

        for session in user_sessions:
            session_pid = session.pid  # Get the PID of the session process
            try:
                proc = psutil.Process(session_pid)
                proc.kill()  # Send SIGKILL (kill -9)
                print(f"Dlog Process {session_pid} ({ self.target_user}) terminated.")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass  # Skip processes that are already terminated or inaccessible


    def update_laps_password(self):
        password_rotten = True
        action = False
        if not self.password_expiration_protection and self.expiration_time_attr > self.dt_now_int:
            password_rotten = False
        elif self.password_expiration_protection:
            if self.pass_last_mod_int + (self.password_age_days * int(self.__day_float)) > self.dt_now_int:
                if self.expiration_time_attr > self.dt_now_int:
                    password_rotten = False

        if not password_rotten:
            if self.get_changed_password_hours_ago() < self.last_login_hours_ago:
                return
            else:
                if self.last_login_hours_ago < self.post_authentication_reset_delay:
                    return
                elif self.post_authentication_actions == 0:
                    return
                else:
                    action = True if self.post_authentication_actions > 1 else False


        try:
            psw = self.get_password()
            psw_json = self.get_json_pass(psw)
            password = psw_json.encode("utf-16-le") + b"\x00\x00"
            dpapi_ng_blob = dpapi_ng.ncrypt_protect_secret(password, self.encryption_principal, auth_protocol='kerberos')
            full_blob = self.get_full_blob(dpapi_ng_blob)
            mod_msg = ldb.Message()
            mod_msg.dn = self.computer_dn
            mod_msg[self.__attr_EncryptedPassword] = (ldb.MessageElement
                                            (full_blob, ldb.FLAG_MOD_REPLACE, self.__attr_EncryptedPassword))
            mod_msg[self.__attr_PasswordExpirationTime] = (ldb.MessageElement
                                            (str(self.expiration_date_int), ldb.FLAG_MOD_REPLACE, self.__attr_PasswordExpirationTime))

            self.samdb.modify(mod_msg)
            self.__change_root_password(psw)
            print(f"Пароль успешно обновлен")

        except Exception as e:
            print(f"Ошибка при работе с LDAP: {str(e)}")
        if action:
            self.run_action()

    def run_action(self):
        if self.post_authentication_actions == 2:
            self.terminate_user_sessions()
        elif self.post_authentication_actions == 3:
            subprocess.run(["reboot"])

    def apply(self):
        if self.__module_enabled:
            self.update_laps_password()
            print('Dlog')
        else:
            print('Dlog')
