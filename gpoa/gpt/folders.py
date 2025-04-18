#
# GPOA - GPO Applier for Linux
#
# Copyright (C) 2019-2024 BaseALT Ltd.
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


from .dynamic_attributes import DynamicAttributes

from util.xml import get_xml_root



def action_enum2letter(enumitem):
    return enumitem.value


def folder_int2bool(val):
    value = val

    if type(value) == str:
        value = int(value)

    if value == 1:
        return True

    return False


def read_folders(folders_file):
    folders = list()

    for fld in get_xml_root(folders_file):
        props = fld.find('Properties')
        path = props.get('path')
        action = props.get('action', default='C')
        fld_obj = folderentry(path, action)
        fld_obj.set_delete_folder(folder_int2bool(props.get('deleteFolder', default=1)))
        fld_obj.set_delete_sub_folders(folder_int2bool(props.get('deleteSubFolders', default=1)))
        fld_obj.set_delete_files(folder_int2bool(props.get('deleteFiles', default=1)))
        fld_obj.set_hidden_folder(folder_int2bool(props.get('hidden', default=0)))

        folders.append(fld_obj)


    return folders

def merge_folders(storage, sid, folder_objects, policy_name):
    for folder in folder_objects:
        storage.add_folder(sid, folder, policy_name)


class folderentry(DynamicAttributes):
    def __init__(self, path, action):
        self.path = path
        self.action = action
        self.delete_folder = False
        self.delete_sub_folders = False
        self.delete_files = False
        self.hidden_folder = False

    def set_action(self, action):
        self.action = action

    def set_delete_folder(self, del_bool):
        self.delete_folder = del_bool

    def set_delete_sub_folders(self, del_bool):
        self.delete_sub_folders = del_bool

    def set_delete_files(self, del_bool):
        self.delete_files = del_bool

    def set_hidden_folder(self, hid_bool):
        self.hidden_folder = hid_bool