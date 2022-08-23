#
# GPOA - GPO Applier for Linux
#
# Copyright (C) 2019-2020 BaseALT Ltd.
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
)

import json
import os
from util.logging import log
from util.util import is_machine_name

class chromium_applier(applier_frontend):
    __module_name = 'ChromiumApplier'
    __module_enabled = True
    __module_experimental = False
    __registry_branch = 'Software\\Policies\\Google\\Chrome'
    __managed_policies_path = '/etc/chromium/policies/managed'
    __recommended_policies_path = '/etc/chromium/policies/recommended'
    # JSON file where Chromium stores its settings (and which is
    # overwritten every exit.
    __user_settings = '.config/chromium/Default'

    def __init__(self, storage, sid, username):
        self.storage = storage
        self.sid = sid
        self.username = username
        self._is_machine_name = is_machine_name(self.username)
        chromium_filter = '{}%'.format(self.__registry_branch)
        self.chromium_keys = self.storage.filter_hklm_entries(chromium_filter)

        self.policies_json = dict()

        self.__module_enabled = check_enabled(
              self.storage
            , self.__module_name
            , self.__module_experimental
        )

    def machine_apply(self):
        '''
        Apply machine settings.
        '''

        destfile = os.path.join(self.__managed_policies_path, 'policies.json')

        try:
            recommended__json = self.policies_json.pop('Recommended')
        except:
            recommended__json = {}

        dict_item_to_list = (
            lambda target_dict :
                {key:[*val.values()] if type(val) == dict else val for key,val in target_dict.items()}
            )
        os.makedirs(self.__managed_policies_path, exist_ok=True)
        with open(destfile, 'w') as f:
            json.dump(dict_item_to_list(self.policies_json), f)
            logdata = dict()
            logdata['destfile'] = destfile
            log('D97', logdata)

        destfilerec = os.path.join(self.__recommended_policies_path, 'policies.json')
        os.makedirs(self.__recommended_policies_path, exist_ok=True)
        with open(destfilerec, 'w') as f:
            json.dump(dict_item_to_list(recommended__json), f)
            logdata = dict()
            logdata['destfilerec'] = destfilerec
            log('D97', logdata)


    def apply(self):
        '''
        All actual job done here.
        '''
        if self.__module_enabled:
            log('D95')
            self.create_dict(self.chromium_keys)
            self.machine_apply()
        else:
            log('D96')

    def get_valuename_typeint(self):
        return (['DefaultFileSystemWriteGuardSetting','DefaultInsecureContentSetting_BlockInsecureContent'
        , 'DefaultInsecureContentSetting', 'DefaultSensorsSetting', 'DefaultWebUsbGuardSetting'
        , 'DefaultSerialGuardSetting','DefaultCookiesSetting', 'DefaultImagesSetting', 'DefaultJavaScriptSetting'
        , 'DefaultPluginsSetting', 'DefaultPopupsSetting', 'DefaultNotificationsSetting'
        , 'DefaultGeolocationSetting', 'DefaultMediaStreamSetting', 'DefaultWebBluetoothGuardSetting'
        , 'DefaultKeygenSetting', 'ChromeFrameRendererSettings', 'RenderInChromeFrameList'
        , 'ScreenOffDelayAC', 'ScreenLockDelayAC', 'IdleWarningDelayAC', 'IdleDelayAC'
        , 'ScreenDimDelayBattery', 'ScreenOffDelayBattery', 'ScreenLockDelayBattery'
        , 'IdleWarningDelayBattery','IdleDelayBattery', 'IdleAction', 'IdleActionAC'
        , 'IdleActionBattery', 'LidCloseAction', 'PresentationIdleDelayScale'
        , 'PresentationScreenDimDelayScale', 'UserActivityScreenDimDelayScale'
        , 'ProxyServerMode', 'QuickUnlockTimeout', 'PinUnlockMinimumLength', 'PinUnlockMaximumLength'
        , 'RestoreOnStartup', 'DeviceIdleLogoutTimeout', 'DeviceIdleLogoutWarningDuration'
        , 'DeviceLocalAccountAutoLoginDelay', 'DeviceLoginScreenSaverTimeout', 'DevicePolicyRefreshRate'
        , 'DeviceUpdateScatterFactor', 'DiskCacheSize', 'DisplayRotationDefault', 'ExtensionCacheSize'
        , 'ForceYouTubeRestrict', 'HeartbeatFrequency', 'IncognitoModeAvailability', 'LoginAuthenticationBehavior'
        , 'MaxConnectionsPerProxy', 'MaxInvalidationFetchDelay', 'MediaCacheSize'
        , 'NetworkPredictionOptions', 'PolicyRefreshRate', 'ReportUploadFrequency'
        , 'SAMLOfflineSigninTimeLimit', 'SessionLengthLimit', 'SystemTimezoneAutomaticDetection'
        , 'UptimeLimit', 'SafeBrowsingProtectionLevel'])


    def get_boolean(self,data):
        if data in ['0', 'false', None, 'none', 0]:
            return False
        if data in ['1', 'true', 1]:
            return True
    def get_parts(self, hivekeyname):
        '''
        Parse registry path string and leave key parameters
        '''
        parts = hivekeyname.replace(self.__registry_branch, '').split('\\')
        return parts


    def create_dict(self, firefox_keys):
        '''
        Collect dictionaries from registry keys into a general dictionary
        '''
        counts = dict()
        valuename_typeint = self.get_valuename_typeint()
        for it_data in firefox_keys:
            branch = counts
            try:
                if type(it_data.data) is bytes:
                    it_data.data = it_data.data.decode(encoding='utf-16').replace('\x00','')
                if it_data.valuename != it_data.data:
                    parts = self.get_parts(it_data.hive_key)
                    for part in parts[:-1]:
                        branch = branch.setdefault(part, {})
                    if it_data.type == 4:
                        if it_data.valuename in valuename_typeint:
                            branch[parts[-1]] = int(it_data.data)
                        else:
                            branch[parts[-1]] = self.get_boolean(it_data.data)
                    else:
                        branch[parts[-1]] = str(it_data.data).replace('\\', '/')
                else:
                    parts = self.get_parts(it_data.keyname)
                    for part in parts[:-1]:

                        branch = branch.setdefault(part, {})
                    if branch.get(parts[-1]) is None:
                        branch[parts[-1]] = list()
                    if it_data.type == 4:
                        branch[parts[-1]].append(self.get_boolean(it_data.data))
                    else:
                        if os.path.isdir(str(it_data.data).replace('\\', '/')):
                            branch[parts[-1]].append(str(it_data.data).replace('\\', '/'))
                        else:
                            branch[parts[-1]].append(str(it_data.data))
            except Exception as exc:
                logdata = dict()
                logdata['Exception'] = exc
                logdata['keyname'] = it_data.keyname
                log('D178', logdata)
        try:
            self.policies_json = counts['']
        except:
            self.policies_json = {}
