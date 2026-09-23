"""
root            :   "f:/dev"
path            :   "subfolder/"                    - directory structure of file below root
fullpath        :   "f:/dev/subfloder/"             - directory structure of file (root included)
filename        :   "name.txt"                      - filename  with extension
purefilename    :   "name"                          - filename  w/o  extension
extension       :   ".txt"                          - extension with '.'
pureextension   :   "txt"                           . extension w/o  '.'
filedate        :   "_20180512"                     - date of file creation with '_'
filetime        :   "-1244"                         - time of file creation with '-'
purefiledate    :   "20180512"                      - date of file creation w/o  '_'
purefiletime    :   "1244"                          - time of file creation w/o  '-'
fullfilename    :   "f:/dev/subfloder/name.txt"     - directory structure plus filename with extension
_raw            :   "...<id>...<timestamp>..."      - any string containing <> characters. Text btw. < and > are
                                                      keys pointing to strings to be inserted...

General module developed by Sziller to be used across several applications.
All programs here are courtesy of the author.
"""

import json
import os
import datetime as dt
from pyaml import yaml


def write_dict_to_file(dict_out, path, datelogical, filename, lispformat=False, ordered=False):
    """------------------------------------------------------
    - Script to write a dictionary to a file                -
    - The date can be included in the filename              -
    - Input example:                                        -
    -------------------------------------------by Sziller-"""
    if datelogical:
        as_year = dt.datetime.now().strftime("%Y")  # Actual String year
        as_month = dt.datetime.now().strftime("%m")  # Actual String month
        as_day = dt.datetime.now().strftime("%d")  # Actual String day
        as_hour = dt.datetime.now().strftime("%H")  # Actual String hour
        as_min = dt.datetime.now().strftime("%M")  # Actual String min
        fullpath = path + as_year + as_month + as_day + "_" + as_hour + as_min + '-' + filename  # set filename format
    else:
        fullpath = path + filename  # here you can set the filename format
    if ordered:
        keys_sequence = sorted(list(dict_out.keys()))
    else:
        keys_sequence = list(dict_out.keys())
    with open(fullpath, "w") as file:
        for k in keys_sequence:
            if lispformat:
                if isinstance(dict_out[k], str):
                    dict_out_i = dict_out[k].replace('\\', "\\\\")
                    if isinstance(k, str):
                        line_string = '"' + k + '"' + " " + '"' + dict_out_i + '"'
                    else:
                        line_string = str(k) + " " + '"' + dict_out_i + '"'
                else:
                    if isinstance(k, str):
                        line_string = '"' + k + '"' + " " + str(dict_out[k])
                    else:
                        line_string = str(k) + " " + str(dict_out[k])
                if not isinstance(dict_out[k], str):
                    line_string = line_string.replace(":", "")
                    line_string = line_string.replace(",", "")
                    line_string = line_string.replace("[", "(")
                    line_string = line_string.replace("]", ")")
                line_string = "( " + line_string + " )"
            else:
                line_string = str(k) + ": " + str(dict_out[k])
            file.write(line_string + "\n")


def write_list_to_file(string_list, path, datelogical, filename, lispformat=False):
    """------------------------------------------------------
    - Script to write a list of strings to a file           -
    - The date is always included in the filename           -
    - Input example:                                        -
    - L= ['first string\n', 'second string\n', 'third string\n', 'fourth string\n'],
    FileName="textfile.txt", Date=True, Path="f:\\"
    -------------------------------------------by Sziller-"""
    if datelogical:
        as_year = dt.datetime.now().strftime("%Y")  # Actual String year
        as_month = dt.datetime.now().strftime("%m")  # Actual String month
        as_day = dt.datetime.now().strftime("%d")  # Actual String day
        as_hour = dt.datetime.now().strftime("%H")  # Actual String hour
        as_min = dt.datetime.now().strftime("%M")  # Actual String min
        fullpath = path + as_year + as_month + as_day + "_" + as_hour + as_min + '-' + filename  # set filename format
    else:
        fullpath = path + filename  # here you can set the filename format

    with open(fullpath, "w") as file:
        for line in string_list:
            line_string = str(line)
            if lispformat:
                line_string = line_string.replace("[", "(")
                line_string = line_string.replace("]", ")")
                line_string = line_string.replace(",", "")
            file.write(line_string + "\n")


def write_list_to_file_v2(string_list, path, datelogical, filename):
    """------------------------------------------------------
    - Script to write a list of strings to a file           -
    - The date is always included in the filename           -
    - Input example:                                        -
    - L= ['first string\n', 'second string\n', 'third string\n', 'fourth string\n'],
    FileName="textfile.txt", Date=True, Path="f:\\"
    -------------------------------------------by Sziller-"""
    if datelogical:
        as_year = dt.datetime.now().strftime("%Y")  # Actual String year
        as_month = dt.datetime.now().strftime("%m")  # Actual String month
        as_day = dt.datetime.now().strftime("%d")  # Actual String day
        as_hour = dt.datetime.now().strftime("%H")  # Actual String hour
        as_min = dt.datetime.now().strftime("%M")  # Actual String min
        fullpath = path + as_year + as_month + as_day + "_" + as_hour + as_min + '-' + filename  # set filename format
    else:
        fullpath = path + filename  # here you can set the filename format

    with open(fullpath, "w") as file:
        for line in string_list:
            file.write(line)
    return string_list


def read_file_to_list(file, logical=True, nullbyte=False):
    """----------------------------------------------------------------------------------
    - Reader opens a file, and reads in its content into a list                         -
    - NullByte should be 'True' if NullBytes can be expected due to conversion issues   -
    - Input example:                                                                    -
    - File="f:/python/assets-txt/ID-Verzeichnis.txt", Logical=True, NullByte=False      -
    -----------------------------------------------------------------------by Sziller-"""
    rawtext = open(file, 'r').read()
    if nullbyte:
        rawtext = rawtext.replace("\0", "")  # deletes Null Bytes
    return rawtext.splitlines(logical)  # creates the list format


def read_file(file, logical=True, nullbyte=False, asstring=False):
    """----------------------------------------------------------------------------------
    - Reader opens a file, and reads in its content into a list                         -
    - NullByte should be 'True' if NullBytes can be expected due to conversion issues   -
    - Input example:                                                                    -
    - File="f:/python/assets-txt/ID-Verzeichnis.txt", Logical=True, NullByte=False      -
    -----------------------------------------------------------------------by Sziller-"""
    rawtext = open(file, 'r').read()
    if nullbyte:
        rawtext = rawtext.replace("\0", "")  # deletes Null Bytes
    if asstring:
        string = ""
        for line in rawtext.splitlines(True):
            string += line
        return string
    else:
        return rawtext.splitlines(logical)  # creates the list format


def txt_read_in(file, logical, nullbyte):
    """----------------------------------------------------------------------------------
    - Reader opens a file, and reads in its content into a list                         -
    - NullByte should be 'True' if NullBytes can be expected due to conversion issues   -
    - Input example:                                                                    -
    - File="f:/python/assets-txt/ID-Verzeichnis.txt", Logical=True, NullByte=False      -
    -----------------------------------------------------------------------by Sziller-"""
    rawtext = open(file, 'r').read()
    if nullbyte:
        rawtext = rawtext.replace("\0", "")  # deletes Null Bytes
    return rawtext.splitlines(logical)  # creates the list format


def read_config_settings(file: str="_EvoConfig_FPO.txt"):
    """

    :param file: string - filename
    :return:
    """
    if file.lower().endswith('.txt'):
        content = txt_read_in(file=file, logical=False, nullbyte=False)
        processed = {}
        for line in content:
            info = line.split(sep="#")[0]
            key = info.split(sep="=")[0].split()[0]
            value = eval(info.split(sep="=")[1])
            processed[key] = value
    elif file.lower().endswith(('.yml', '.yaml')):
        data = open(file, "r")
        processed = yaml.load(data)
    elif file.lower().endswith(('.jsn', '.json')):
        with open(file) as infile:
            processed = json.load(infile)
    return processed


def line_by_line_evaluate(line_list: list):
    """-------------------------------------------------------------------------------
    - When a list is read in out of a file this Script can reformat it -
    ---------------------------------------------------------------------------------"""
    answer = []
    for line in line_list:
        current_row = eval(line)
        answer.append(current_row)
    return answer


def export_manager(database: dict, fullpath: str, export_syntax: str, extension=".txt"):
    """
    Bundled export method.
    Entered database's every item will be exported into a separate file.
    Path for the files is defined as the 'fullpath' argument, filenames are included in 'database' dictionary as keys.
    An entry looks like this: {'01-filename': { < arbitrary dictionary > },
                               '02-filename': [ < arbitrary list       > ] }
    Database (dict) may include lists and/or dictionaries as values. Keys - being filenames - must be strings.
    If an items value is a dictionary, it (the dictionary) will be ordered.
    :param extension: string. File extension.
    :param export_syntax: syntax to be read by a certain software.
    :param database: the data to be processed
    :param fullpath: dictionary to save files to.
    :return:
    """
    if export_syntax == "lisp":
        formatanswer = True
    else:
        formatanswer = False
    for filename, data in list(database.items()):
        if isinstance(data, list):
            write_list_to_file(string_list=data,
                               path=fullpath,
                               datelogical=False,
                               filename=filename+extension,
                               lispformat=formatanswer)
        if isinstance(data, dict):
            write_dict_to_file(dict_out=data,
                               path=fullpath,
                               datelogical=False,
                               filename=filename+extension,
                               lispformat=formatanswer,
                               ordered=True)
    print("Exporting data finished!")
    return None


def txt_to_yaml_file_duplicator(filenames: list, fullpath: str):
    """
    helper to transform settings files from txt to yaml.
    :param fullpath:
    :param filenames:
    :return:
    """
    for _ in filenames:
        current_dict = read_config_settings(fullpath + _+".txt")
        with open(fullpath + _ + '.yaml', 'w') as outfile:
            yaml.dump(current_dict, outfile, default_flow_style=False)
            outfile.close()


def data_to_yaml(data, filename: str, fullpath=None):
    """=== Function name: data_to_yaml =================================================================================
    Script dumps whatever data (dictionary or list at this point) you enter into a yaml file
    :param data:
    :param filename:
    :param fullpath:
    :return: nothing
    ============================================================================================== by Sziller ==="""
    if not fullpath:
        fullfilename = filename
    else:
        fullfilename = fullpath + filename
    with open(fullfilename, 'w') as outfile:
        yaml.dump(data, outfile, default_flow_style=False)
        outfile.close()


def data_to_json(data, filename: str, fullpath=None):
    """=== Function name: data_to_json =================================================================================
    Script dumps whatever data (dictionary or list at this point) you enter into a json file
    ATTENTION! All keys in dictionaries are converted into strings, as json format only supports strings as keys:
    tupple as key returns an error.
    :param data: dictionary or a list to be dumped
    :param filename: the filename to be used (including extension!)
    :param fullpath: if given, used as prefix in front of the filename
    :return: nothing
    ============================================================================================== by Sziller ==="""
    if not fullpath:
        fullfilename = filename
    else:
        fullfilename = fullpath + filename
    with open(fullfilename, "w") as outfile:
        json.dump(data, outfile, default=lambda o: o.__dict__, indent=2)
        outfile.close()


def yaml_read_in(filename: str, fullpath=None):
    """=== Function name: yaml_read_in =================================================================================
    Script reads data from yaml file, and returns it as is.
    :param filename: the filename to be used (including extension!)
    :param fullpath: if given, used as prefix in front of the filename
    :return: read in data
    ============================================================================================== by Sziller ==="""
    if not fullpath:
        fullfilename = filename
    else:
        fullfilename = fullpath + filename
    data = open(fullfilename, "r")
    answer = yaml.load(data)
    data.close()
    return answer


def json_read_in(filename: str, fullpath=None):
    """=== Function name: json_read_in =================================================================================
    Script reads data from json file, and returns it as is.
    reads in a json type file
    :param filename: the filename to be used (including extension!)
    :param fullpath: if given, used as prefix in front of the filename
    :return: read in data
    ============================================================================================== by Sziller ==="""
    if not fullpath:
        fullfilename = filename
    else:
        fullfilename = fullpath + filename
    with open(fullfilename) as infile:
        in_data = json.load(infile)
        infile.close()
        return in_data


def custom_config_data_reader(filename_lead: str,
                              fullpath: str,
                              rawfilename: str = "Config",
                              problem_type:str = "GAD",
                              extension: str = "yaml",
                              messaging: bool = True,
                              devswitch: bool = True
                              ) -> dict:
    """=== Function name: custom_config_data_reader ================================================================
    Out of any EA-Engine style config file it reads out the actual data in a dictionary format.
    Returns the so called config_data, which still needs to be digested into config_info, done by an other function.
    :param filename_lead: str - the type of the confid data. What the data is about. E.g.: "Display", "Engine"
    :param rawfilename: str - the type of the information-set, we deal with. Mostly "Config"
    :param problem_type: str - 3 letter code to indicate project type / contractor
    :param extension: str - file extension. For "Config" it's 'yaml'
    :param fullpath: str - tha directory's absolute path, where file is located. Usually the project root.
    :param messaging: bool - if True, user will get important messages in the console at runtime.
    :param devswitch: bool - if True, developer will get messages in the console at runtime.
       Messaging and devswitch are in an AND relation. Given message only shows, when both values are True.
    :return:
    ============================================================================================== by Sziller ==="""
    filename = "".join(['_', filename_lead, rawfilename, "-", problem_type, '.', extension])
    config_fullfilename = path_corrector(os.path.join(fullpath, filename))
    if os.path.exists(config_fullfilename):
        si_print(
            string="  - config_filename:\n    %s" % config_fullfilename,
            on=messaging, switch=devswitch)
        config_data = read_config_settings(file=config_fullfilename)  # read config settings out of file
        si_print(
            string="  - path setup and read-in of default config-settings:                          --- done ---",
            on=messaging, switch=devswitch)
    else:
        print("ERROR: Couldn't find: %s" % config_fullfilename)
        return {}
    return config_data


def custom_config_info_setup(info_setup_request_list: list,
                             config_data: dict,
                             config_data_abspath: str,
                             messaging: bool = True,
                             devswitch: bool = True) -> dict:
    """=== Function name: custom_config_info_setup =================================================================
    Out of the confid_data, which is the raw dictionary read-out off a config file, this function sets up the
    actual config_info whatever that may be. (paths, boolean-switches, etc).
    config_data:    the raw data stored in the config files, such as:
                    strings of paths (relative or absolute)     |
                    strings of filenames                        > for external files:   - load sources (settings)
                    strings of extensions                       |                       - save targets (results, logs)
                    booleans for basic settings
    config_info:    digested, processed info comming from config data.
                    Difference is mainly in <fullfilenames> as these are made up of data crumbs
                    originating in config_data
                    Also relative-absolute distinction is omitted: config_info ALWAYS returns ABSOLUTE paths.
    task_dict:      contains the names (later keys) of config info lines, to be created in the data --> info convert
                    process.
                    Paths are converted into ABSOLUTE paths.
    :param info_setup_request_list: list - containing keys of the dictionary you want to set up.
    :param config_data: dict - dictionary formated config file content.
    :param config_data_abspath: str - ABSOLUTE path of the directory housing config file
                                      out of which config_data was created.
    :param messaging: bool - if True, user will get important messages in the console at runtime.
    :param devswitch: bool - if True, developer will get messages in the console at runtime.
       Messaging and devswitch are in an AND relation. Given message only shows, when both values are True.
    :return: config_info - dict - digested config_data in a dictionary format
    ============================================================================================== by Sziller ==="""
    config_info = {}  # empty return dictionary
    path_on_init = os.getcwd()  # working dictionary on init of THIS(!) function
    os.chdir(config_data_abspath)  # changing working directory to entered config_path
    for info in info_setup_request_list:  # looping through info, user needs
        # multiple ways to process an info-line:
        # 1). If info occurs in the request list as-is, then it (same key + it's value) is returned unchanged
        if info in config_data.keys():
            config_info[info] = config_data[info]
            if info.split(sep="_")[0] == "Path":
                config_info[info] = os.path.abspath(config_info[info])
        # 2). If the exact same key doesn't occur, more possibilities may come to pass.
        else:
            # ...al of these include:
            info_atoms = info.split(sep="_")  # splitting the request key into atoms
            info_data_types = ['type', 'category', 'subcategory', 'misc']
            ''' type        -   it can be:  'Logical', 'Path', 'Filename', 'Fullfilename', 'Extension', ...etc.
                category    -   or the name of the variable's group. From the apps point of view, what info refers to.
                                it can be:  'Response', 'Log', 'Incomming', 'AnimationSettings', ...etc.
                subcategory -   further detailing 'category': what kind of response, which Anim. settings, etc...
                misc        -   any info to distinguish bwt. otherwise identical aliases
            '''
            info_data = {}
            for counter, atom in enumerate(info_atoms):
                info_data[info_data_types[counter]] = atom
            # You have here a dictionary belonging to actual info in the following format:
            # info_data = {'type': 'Fullfilename', 'category': 'Response', 'subcategory': 'Genome'}

            # when full file names are requested:
            if info_data['type'] == 'Fullfilename':
                path_as_read = config_data["Path_" + info_data['category']]
                path = os.path.abspath(path_as_read)
                filename_key = "Filename_" + info_data['category']
                if 'subcategory' in info_data.keys():
                    filename_key += "_" + info_data['subcategory']
                filename = config_data[filename_key]
                if (filename_key + "_end") in config_data.keys():
                    filename += "_" + config_data[filename_key + "_end"]
                config_info[info] = os.path.join(path, filename)

    # IMPORTANT: we switch back to the working directory, that was active, on script init.
    os.chdir(path_on_init)  # changing working directory back to where it was on init
    return config_info  # answering


def directoryseeker_downtree_by_bookmark(fullpath_actual_file: str,
                                         filename_bookmark: str = "__root__.py") -> str:
    """=== Function name: directoryseeker_downtree_by_bookmark =========================================================
    Function returns the folder name in which the bookmark file is located.
    It searches through the entire filetree DOWNWARDS (towards the root), starting in 'fullpath_actual_file'
    :param fullpath_actual_file: a path in any format (Windows or Linux) with or without / at the end.
                                 starting directory of the search. If 'bookmark' is found here, this path is returned.
    :param filename_bookmark: the filename searched for.
    :return: str - directory name
    ============================================================================================== by Sziller ==="""
    # constructing theoretical absolute full filename in given directory:
    fullfilename = os.path.abspath(os.path.join(fullpath_actual_file, filename_bookmark))
    prev_fullpath = False  # there were no previous paths, as the search did not yet start.
    # starting search as long as either:
    # - file is found, or
    # - filesystem root is reached
    while (not os.path.exists(fullfilename)) and (prev_fullpath != fullpath_actual_file):
        prev_fullpath = fullpath_actual_file
        fullpath_actual_file = os.path.dirname(os.path.dirname(fullfilename))
        fullfilename = os.path.join(fullpath_actual_file, filename_bookmark)
    if os.path.exists(fullfilename):  # if file was found, it's full-path is returned
        return path_corrector(fullpath_actual_file)
    else:  # if filesystem root is reached w/o a valid file, function prints an error message and returns ''
        print("ERROR! File not found. - sais >directoryseeker_downtree_by_bookmark<")
        return ""


def fileseeker_downtree(original_fullfilename) -> str:
    """=== Function name: fileseaker_downtree ==========================================================================
    Script takes an alledged fullfilename. If it exists, it's returned, if it doesn't, function looks all the way down
    the file-tree (direction: root), down until the root, as long as it doesn't find the file of the same base-name.
    The first appearence of the original filename will be returned with the fullpath it was found in.
    Script returns the file's fullfilename (fullpath + filename) in LINUX format.

    :param original_fullfilename: str - a path in any format (Windows or Linux)
    :return: a Linux format fullfilename of the file entered.
    ============================================================================================== by Sziller ==="""
    if not os.path.exists(original_fullfilename):
        fullpath = os.path.dirname(original_fullfilename)
        filename = os.path.basename(original_fullfilename)
        prev_fullpath = False
        fullfilename = os.path.join(fullpath, filename)
        print("fullfilename: %s" % fullfilename)
        while (not os.path.exists(fullfilename)) and prev_fullpath != fullpath:
            prev_fullpath = fullpath
            fullpath = os.path.dirname(prev_fullpath)
            fullfilename = os.path.join(fullpath, filename)
            print("fullfilename: %s" % fullfilename)
        if prev_fullpath == fullpath:
            return ""
        else:
            return path_corrector(fullfilename)
    else:
        return path_corrector(original_fullfilename)


def path_corrector(incomming_path, **kwargs):
    """=== Function name: path_corrector ===============================================================================
    Turns an incoming path into a linux style path, using only '/' - forward-slash characters.
    Raw windows type filenames using single back-slash followed by a key character will not be processed correctly.
    :param incomming_path: str - any windows or mixed format path
    :return:
    ============================================================================================== by Sziller ==="""
    return '/'.join(incomming_path.split(sep='\\'))


def path_constructor(config_dict: dict, config_path: str, key: str):
    """=== Function name: path_constructor =============================================================================
    Routine to set up a specific path used by EA init files:
    EA config files are always stored in the root folder of the application they are used by.
    This leads to a complicated situation, when oyu want to reference the root of a subprocess, when run by a parent
    process. Roots are different when run as main and when run as subprocess.
    So the './folder/file.ext' type marking of relative parent directory only works, with one of these.
    """
    if config_dict[key].lower().startswith("."):
        constructed = path_corrector(os.path.join(config_path, config_dict[key]))
    else:
        constructed = config_dict[key]
    return constructed


def si_print(string="Default", switch=True, on=True):
    """

    :param switch:
    :param string:
    :param on:
    :return:
    """
    if on:
        if switch:
            print(string)
            return string


if __name__ == "__main__":
    pass
    dic = {'project_id': 1, 'solutions': [{'cog': {'position': {'x': 17428.363753836213, 'y': -5197.836536908416, 'z': 0}}, 'transformation': {'rotation': 50, 'offset': {'x': -300, 'y': -1000, 'z': 0}}, 'demolished': [], 'cuboids': [{'name': 'BiologicalTreatment', 'size': {'x': 8700.0, 'y': 6200.0, 'z': 5000.0}, 'position': {'x': 12000, 'y': -1066, 'z': 0}, 'rotation': 0}, {'name': 'SludgeStorageTanks', 'size': {'x': 7700.0, 'y': 4400.0, 'z': 5000.0}, 'position': {'x': 12500, 'y': -9366, 'z': 0}, 'rotation': 0}, {'name': 'ThickeningBlock', 'size': {'x': 10000.0, 'y': 3600.0, 'z': 4500.0}, 'position': {'x': 30200, 'y': -7466, 'z': 0}, 'rotation': 90}]}, {'cog': {'position': {'x': 17401.001453723147, 'y': -5197.836536908416, 'z': 0}}, 'transformation': {'rotation': 50, 'offset': {'x': -300, 'y': -1000, 'z': 0}}, 'demolished': [], 'cuboids': [{'name': 'BiologicalTreatment', 'size': {'x': 8700.0, 'y': 6200.0, 'z': 5000.0}, 'position': {'x': 12000, 'y': -1066, 'z': 0}, 'rotation': 0}, {'name': 'SludgeStorageTanks', 'size': {'x': 7700.0, 'y': 4400.0, 'z': 5000.0}, 'position': {'x': 12400, 'y': -9366, 'z': 0}, 'rotation': 0}, {'name': 'ThickeningBlock', 'size': {'x': 10000.0, 'y': 3600.0, 'z': 4500.0}, 'position': {'x': 30200, 'y': -7466, 'z': 0}, 'rotation': 90}]}, {'cog': {'position': {'x': 17428.363753836213, 'y': -5168.762073978356, 'z': 0}}, 'transformation': {'rotation': 50, 'offset': {'x': -300, 'y': -1000, 'z': 0}}, 'demolished': [], 'cuboids': [{'name': 'BiologicalTreatment', 'size': {'x': 8700.0, 'y': 6200.0, 'z': 5000.0}, 'position': {'x': 12000, 'y': -1066, 'z': 0}, 'rotation': 0}, {'name': 'SludgeStorageTanks', 'size': {'x': 7700.0, 'y': 4400.0, 'z': 5000.0}, 'position': {'x': 12500, 'y': -9366, 'z': 0}, 'rotation': 0}, {'name': 'ThickeningBlock', 'size': {'x': 10000.0, 'y': 3600.0, 'z': 4500.0}, 'position': {'x': 30200, 'y': -7366, 'z': 0}, 'rotation': 90}]}]}
    rates = {20180000: 309.57,
                   20180102: 309.57,    20180103: 309.42,   20180104: 308.57,   20180105: 308.33,   20180108: 308.96,
                   20180109: 309.31,    20180110: 309.69,   20180111: 309.06,   20180112: 308.62,   20180115: 309.25,
                   20180116: 309.06,    20180117: 309.05,   20180118: 308.34,   20180119: 309.28,   20180122: 309.49,
                   20180123: 309.91,    20180124: 309.09,   20180125: 309.34,   20180126: 309.80,   20180129: 309.38,
                   20180130: 310.11,    20180131: 310.60,   20180201: 310.09,   20180202: 309.38,   20180205: 309.92,
                   20180206: 310.16,    20180207: 309.99,   20180208: 311.10,   20180209: 312.14,   20180212: 312.05,
                   20180213: 311.90,    20180214: 312.27,   20180215: 311.60,   20180216: 311.16,   20180219: 311.34,
                   20180220: 311.86,    20180221: 312.09,   20180222: 312.38,   20180223: 312.99,   20180226: 313.20,
                   20180227: 313.55,    20180228: 314.28,   20180301: 313.80,   20180302: 313.79,   20180305: 313.62,
                   20180306: 313.85,    20180307: 312.80,   20180308: 311.75,   20180309: 311.57,   20180312: 311.72,
                   20180313: 311.68,    20180314: 311.66,   20180319: 310.96,   20180320: 311.24,   20180321: 311.43,
                   20180322: 311.55,    20180323: 313.10,   20180326: 312.74,   20180327: 312.61,   20180328: 312.77,
                   20180329: 312.55,    20180403: 312.45,   20180404: 312.03,   20180405: 311.34,   20180406: 311.81,
                   20180409: 311.85,    20180410: 311.60,   20180411: 311.60,   20180412: 311.27,   20180413: 310.99,
                   20180416: 310.25,    20180417: 310.68,   20180418: 310.35,   20180419: 310.35,   20180420: 310.49,
                   20180423: 311.18,    20180424: 312.55,   20180425: 312.89,   20180426: 313.33,   20180427: 312.62,
                   20180502: 313.84,    20180503: 314.23,   20180504: 314.40,   20180507: 313.89,   20180508: 314.53,
                   20180509: 314.71,    20180510: 314.41,   20180511: 314.49,   20180514: 315.15,   20180515: 317.26,
                   20180516: 317.19,    20180517: 316.35,   20180518: 317.33,   20180522: 316.65,   20180523: 318.80,
                   20180524: 318.87,    20180525: 319.61,   20180528: 318.97,   20180529: 319.88,   20180530: 319.31,
                   20180531: 318.88,    20180601: 319.82,   20180604: 319.08,   20180605: 318.66,   20180606: 318.94,
                   20180607: 317.30,    20180608: 319.80,   20180611: 320.87,   20180612: 321.72,   20180613: 320.43,
                   20180614: 321.39,    20180615: 323.37,   20180618: 322.65,   20180619: 324.33,   20180620: 323.09,
                   20180621: 326.17,    20180622: 324.53,   20180625: 324.72,   20180626: 325.58,   20180627: 327.25,
                   20180628: 328.10,    20180629: 328.60,   20180702: 330.04,   20180703: 328.01,   20180704: 326.48,
                   20180705: 324.24,    20180706: 324.16,   20180709: 322.76,   20180710: 325.32,   20180711: 324.62,
                   20180712: 325.20,    20180713: 324.58,   20180716: 322.04,   20180717: 322.84,   20180718: 323.89,
                   20180719: 325.15,    20180720: 325.91,   20180723: 325.97,   20180724: 326.84,   20180725: 325.64,
                   20180726: 324.26,    20180727: 323.26,   20180730: 322.28,   20180731: 321.31,   20180801: 321.21,
                   20180802: 321.50,    20180803: 321.17,   20180806: 320.20,   20180807: 319.56,   20180808: 319.36,
                   20180809: 320.08,    20180810: 322.60,   20180813: 324.16,   20180814: 323.36,   20180815: 323.29,
                   20180816: 323.81,    20180817: 323.53,   20180821: 323.33,   20180822: 322.93,   20180823: 324.17,
                   20180824: 324.25,    20180827: 323.94,   20180828: 323.74,   20180829: 324.84,   20180830: 326.53,
                   20180831: 326.45,    20180903: 326.76,   20180904: 327.71,   20180905: 328.37,   20180906: 327.37,
                   20180907: 324.55,    20180910: 324.88,   20180911: 324.51,   20180912: 324.72,   20180913: 325.52,
                   20180914: 323.56,    20180917: 324.79,   20180918: 324.81,   20180919: 323.40,   20180920: 323.65,
                   20180921: 323.42,    20180924: 323.85,   20180925: 323.80,   20180926: 323.80,   20180927: 323.65,
                   20180928: 323.78,    20181001: 323.43,   20181002: 323.92,   20181003: 322.89,   20181004: 324.04,
                   20181005: 325.10,    20181008: 325.54,   20181009: 325.35,   20181010: 324.86,   20181011: 325.32,
                   20181012: 324.94,    20181015: 324.15,   20181016: 322.20,   20181017: 322.30,   20181018: 322.02,
                   20181019: 323.51,    20181024: 323.00,   20181025: 323.86,   20181026: 324.12,   20181029: 324.44,
                   20181030: 324.76,    20181031: 324.69,   20181105: 322.49,   20181106: 322.11,   20181107: 321.66,
                   20181108: 321.53,    20181109: 321.42,   20181112: 321.81,   20181113: 322.70,   20181114: 322.91,
                   20181115: 322.65,    20181116: 321.62,   20181119: 321.50,   20181120: 321.76,   20181121: 321.61,
                   20181122: 321.66,    20181123: 321.25,   20181126: 322.34,   20181127: 324.02,   20181128: 324.32,
                   20181129: 323.21,    20181130: 323.55,   20181203: 322.41,   20181204: 323.00,   20181205: 323.90,
                   20181206: 323.66,    20181207: 323.10,   20181210: 323.21,   20181211: 323.44,   20181212: 323.59,
                   20181213: 323.52,    20181214: 323.72,   20181217: 323.45,   20181218: 323.30,   20181219: 322.49,
                   20181220: 321.95,    20181221: 321.86,   20181227: 321.18,   20190000: 322.16,
                   20190102: 322.16,    20190103: 322.55,   20190104: 321.25,   20190107: 321.18,   20190108: 321.40,
                   20190109: 321.78,    20190110: 321.75,   20190111: 321.40,   20190114: 321.17,   20190115: 321.80,
                   20190116: 323.52,    20190117: 321.44,   20190118: 318.92,   20190121: 318.20,   20190122: 318.00,
                   20190123: 318.11,    20190124: 318.76,   20190125: 318.41,   20190128: 317.85,   20190129: 317.15,
                   20190130: 317.13,    20190131: 315.87,   20190201: 317.23,   20190204: 317.75,   20190205: 317.75,
                   20190206: 318.82,    20190207: 319.55,   20190208: 319.25,   20190211: 319.65,   20190212: 318.90,
                   20190213: 317.90,    20190214: 318.94,   20190215: 318.05,   20190218: 318.05,   20190219: 318.19,
                   20190220: 317.51,    20190221: 317.37,   20190222: 317.83,   20190225: 318.03,   20190226: 317.71,
                   20190227: 316.39,    20190228: 316.39,   20190301: 315.85,   20190304: 316.12,   20190305: 315.55,
                   20190306: 315.48,    20190307: 315.30,   20190308: 315.80,   20190311: 315.65,   20190312: 315.51,
                   20190313: 314.75,    20190314: 314.45,   20190318: 314.33,   20190319: 313.65,   20190320: 312.82,
                   20190321: 314.29,    20190322: 315.83,   20190325: 316.85,   20190326: 316.23,   20190327: 319.95,
                   20190328: 320.17,    20190329: 320.79,   20190401: 321.19,   20190402: 322.05,   20190403: 319.72,
                   20190404: 319.93,    20190405: 320.61,   20190408: 321.57,   20190409: 321.01,   20190410: 321.81,
                   20190411: 321.49,    20190412: 322.30,   20190415: 320.69,   20190416: 319.81,   20190417: 319.21,
                   20190418: 320.23,    20190423: 320.77,   20190424: 321.20,   20190425: 322.12,   20190426: 322.18,
                   20190429: 322.61,    20190430: 322.87,   20190502: 324.32,   20190503: 323.82,   20190506: 323.69,
                   20190507: 324.10,    20190508: 324.49,   20190509: 324.31,   20190510: 323.51,   20190513: 324.24,
                   20190514: 324.04,    20190515: 324.96,   20190516: 324.20,   20190517: 325.19,   20190520: 326.38,
                   20190521: 327.19,    20190522: 326.71,   20190523: 326.78,   20190524: 326.19,   20190527: 325.63,
                   20190528: 326.40,    20190529: 327.26,   20190530: 325.49,   20190531: 324.92,   20190603: 324.35,
                   20190604: 322.04,    20190605: 321.71,   20190606: 321.20,   20190607: 321.54,   20190611: 320.60,
                   20190612: 321.87,    20190613: 322.29,   20190614: 321.94,   20190617: 322.29,   20190618: 322.20,
                   20190619: 323.79,    20190620: 324.29,   20190621: 323.86,   20190624: 324.06,   20190625: 324.11,
                   20190626: 323.51,    20190627: 323.42,   20190628: 323.54,   20190701: 322.76,   20190702: 322.88,
                   20190703: 323.01,    20190704: 322.39,   20190705: 323.61,   20190708: 324.66,   20190709: 325.24,
                   20190710: 325.93,    20190711: 325.53,   20190712: 325.68,   20190715: 325.79,   20190716: 325.41,
                   20190717: 326.64,    20190718: 326.58,   20190719: 325.67,   20190722: 324.95,   20190723: 325.74,
                   20190724: 325.82,    20190725: 325.23,   20190726: 326.59,   20190729: 326.90,   20190730: 327.84,
                   20190731: 327.15,    20190801: 326.42,   20190802: 327.67,   20190805: 327.45,   20190806: 325.75,
                   20190807: 325.25,    20190808: 325.05,   20190809: 324.55,   20190812: 324.70,   20190813: 324.11,
                   20190814: 323.45,    20190815: 326.13,   20190816: 324.96,   20190821: 327.36,   20190822: 327.64,
                   20190823: 328.38,    20190826: 329.21,   20190827: 329.00,   20190828: 329.92,   20190829: 330.19,
                   20190830: 331.11,    20190902: 331.01,   20190903: 331.13,   20190904: 328.50,   20190905: 329.50,
                   20190906: 329.85,    20190909: 329.95,   20190910: 331.13,   20190911: 332.25,   20190912: 331.37,
                   20190913: 332.70,    20190916: 331.89,   20190917: 333.36,   20190918: 333.12,   20190919: 332.65,
                   20190920: 332.50,    20190923: 334.94,   20190924: 335.29,   20190925: 334.47,   20190926: 334.45,
                   20190927: 336.02,    20190930: 334.65,   20191001: 334.77,   20191002: 334.81,   20191003: 333.32,
                   20191004: 332.45,    20191007: 333.05,   20191008: 333.99,   20191009: 334.32,   20191010: 333.63,
                   20191011: 331.87,    20191014: 331.50,   20191015: 332.17,   20191016: 332.58,   20191017: 332.72,
                   20191018: 330.95,    20191021: 330.39,   20191022: 330.19,   20191024: 329.32,   20191025: 329.10,
                   20191028: 328.69,    20191029: 328.62,   20191030: 329.82,   20191031: 329.82,   20191104: 327.99,
                   20191105: 329.10,    20191106: 331.46,   20191107: 332.56,   20191108: 333.65,   20191111: 334.34,
                   20191112: 334.45,    20191113: 334.95,   20191114: 333.76,   20191115: 334.61,   20191118: 335.36,
                   20191119: 334.91,    20191120: 333.25,   20191121: 333.75,   20191122: 334.36,   20191125: 335.04,
                   20191126: 336.50,    20191127: 335.91,   20191128: 336.71,   20191129: 334.70,   20191202: 333.44,
                   20191203: 332.29,    20191204: 331.35,   20191205: 330.96,   20191206: 330.33,   20191209: 331.73,
                   20191210: 331.72,    20191211: 330.28,   20191212: 329.56,   20191213: 328.82,   20191216: 329.01,
                   20191217: 330.45,    20191218: 330.65,   20191219: 331.39,   20191220: 330.35,   20191223: 330.83,
                   20191230: 330.71,    20191231: 330.52,   20200000: 329.99,
                   20200102: 329.99,    20200103: 329.45,   20200106: 329.98,   20200107: 330.71,   20200108: 331.40,
                   20200109: 331.58,    20200110: 333.84,   20200113: 334.98,   20200114: 332.65,   20200115: 333.21,
                   20200116: 333.83,    20200117: 335.49,   20200120: 336.91,   20200121: 335.53,   20200122: 335.09,
                   20200123: 336.90,    20200124: 336.17,   20200127: 337.16,   20200128: 337.36,   20200129: 337.61,
                   20200130: 337.98,    20200131: 336.65,   20200203: 338.06,   20200204: 336.36,   20200205: 335.74,
                   20200206: 337.09,    20200207: 338.87,   20200210: 338.09,   20200211: 337.71,   20200212: 338.76,
                   20200213: 338.83,    20200214: 334.94,   20200217: 334.67,   20200218: 335.44,   20200219: 335.10,
                   20200220: 337.86,    20200221: 337.76,   20200224: 338.32,   20200225: 337.21,   20200226: 339.56,
                   20200227: 339.12,    20200228: 339.88,   20200302: 337.47,   20200303: 337.03,   20200304: 335.10,
                   20200305: 336.04,    20200306: 337.60,   20200309: 336.22,   20200310: 335.93,   20200311: 334.86,
                   20200312: 337.51,    20200313: 338.00,   20200316: 340.17,   20200317: 347.34,   20200318: 350.17,
                   20200319: 357.62,    20200320: 349.85,   20200323: 351.55,   20200324: 350.33,   20200325: 354.49,
                   20200326: 357.79,    20200327: 354.30,   20200330: 357.21,   20200331: 359.09,   20200401: 364.57,
                   20200402: 361.76,    20200403: 364.42,   20200406: 363.35,   20200407: 359.95,   20200408: 358.76,
                   20200409: 355.66,    20200414: 351.75,   20200415: 351.34,   20200416: 350.15,   20200417: 350.56,
                   20200420: 353.24,    20200421: 355.09,   20200422: 354.30,   20200423: 357.04,   20200424: 356.15,
                   20200427: 353.80,    20200428: 355.31,   20200429: 355.73,   20200430: 353.01,   20200504: 353.39,
                   20200505: 352.06,    20200506: 349.42,   20200507: 350.56,   20200508: 349.57,   20200511: 349.68,
                   20200512: 350.70,    20200513: 353.30,   20200514: 354.33,   20200515: 353.88,   20200518: 353.99,
                   20200519: 351.97,    20200520: 349.91,   20200521: 348.99,   20200522: 349.56,   20200525: 350.53,
                   20200526: 349.66,    20200527: 349.25,   20200528: 350.01,   20200529: 348.35,   20200602: 344.75,
                   20200603: 345.94,    20200604: 345.57,   20200605: 344.67,   20200608: 343.62,   20200609: 344.83,
                   20200610: 343.77,    20200611: 344.70,   20200612: 345.86,   20200615: 347.21,   20200616: 345.67,
                   20200617: 344.53,    20200618: 344.96,   20200619: 346.18,   20200622: 346.25,   20200623: 349.10,
                   20200624: 350.84,    20200625: 353.84,   20200626: 354.95,   20200629: 355.65,   20200630: 356.57,
                   20200701: 353.63,    20200702: 351.66,   20200703: 351.17,   20200706: 352.80,   20200707: 353.78,
                   20200708: 355.07,    20200709: 354.34,   20200710: 353.73,   20200713: 353.84,   20200714: 355.10,
                   20200715: 353.87,    20200716: 353.98,   20200717: 353.78,   20200720: 352.26,   20200721: 351.67,
                   20200722: 350.24,    20200723: 346.73,   20200724: 347.54,   20200727: 345.79,   20200728: 346.15,
                   20200729: 347.25,    20200730: 345.71,   20200731: 344.74,   20200803: 344.99,   20200804: 344.73,
                   20200805: 345.84,    20200806: 346.38,   20200807: 346.21,   20200810: 345.36,   20200811: 344.89,
                   20200812: 345.69,    20200813: 344.97,   20200814: 346.25,   20200817: 348.17,   20200818: 349.92,
                   20200819: 349.64,    20200824: 351.80,   20200825: 353.71,   20200826: 353.95,   20200827: 356.30,
                   20200828: 355.85,    20200831: 354.06,   20200901: 355.06,   20200902: 357.09,   20200903: 357.69,
                   20200904: 359.43,    20200907: 360.04,   20200908: 360.18,   20200909: 357.98,   20200910: 357.56,
                   20200911: 357.44,    20200914: 357.83,   20200915: 357.66,   20200916: 358.95,   20200917: 360.16,
                   20200918: 360.95,    20200921: 362.91,   20200922: 362.45,   20200923: 364.10,   20200924: 365.33,
                   20200925: 362.58,    20200928: 363.86,   20200929: 365.96,   20200930: 364.65,   20201001: 361.89,
                   20201002: 358.77,    20201005: 358.05,   20201006: 360.51,   20201007: 359.57,   20201008: 357.70,
                   20201009: 356.82,    20201012: 356.61,   20201013: 358.81,   20201014: 363.59,   20201015: 365.44}
    data = {'uwdf': {'room_area_cluster_overlap_relative': {'max': 1, 'min': 0.999, 'threshold': 0.999},
                               'quadrilateral_group_rel_area_on_polygonal_slot': {'max': 1, 'min': 0.999,
                                                                                  'threshold': 0.999},
                               'quadrilateral_group_rel_area_on_polygonal_site': {'max': 1, 'min': 0.999,
                                                                                  'threshold': 0.999},
                               'room_edge_overlap_absolute': {'max': 1, 'min': 0.94, 'threshold': 0.94},
                               'quadrilateral_cog_distance_to_point': {'max': 1, 'min': 0.94, 'threshold': 0.94}}}
    # data_to_yaml(filename="f:/secondary_filter.yaml", data=data)
    # aa = {'project_id': 1,
    #       'cuboids':
    #           [
    #               {'name': 'BiologicalTreatment 1',
    #                'position': {'x': 0.0, 'y': 0.0, 'z': 0.0},
    #                'rotation': 90,
    #                'size': {'x': 171600.0, 'y': 300700.0, 'z': 5000.0}},
    #               {'name': 'Sludge Collector 1',
    #                'position': {'x': 0.0, 'y': 0.0, 'z': 0.0},
    #                'rotation': 0,
    #                'size': {'x': 6100.0, 'y': 12000.0, 'z': 5000.0}},
    #               {'name': 'Gravity Thickeners 1',
    #                'position': {'x': 0.0, 'y': 0.0, 'z': 0.0},
    #                'rotation': 0,
    #                'size': {'x': 45200.0, 'y': 45200.0, 'z': 4500.0}},
    #               {'name': 'Secondary Clarifiers 1',
    #                'position': {'x': 0.0, 'y': 0.0, 'z': 0.0},
    #                'rotation': 0,
    #                'size': {'x': 89200.0, 'y': 183400.0, 'z': 4500.0}},
    #               {'name': 'Dewatering Building 1',
    #                'position': {'x': 0.0, 'y': 0.0, 'z': 0.0},
    #                'rotation': 90,
    #                'size': {'x': 24997.0, 'y': 24997.0, 'z': 4000.0}},
    #               {'name': 'Blower Building 1',
    #                'position': {'x': 0.0, 'y': 0.0, 'z': 0.0},
    #                'rotation': 90,
    #                'size': {'x': 21754.0, 'y': 21754.0, 'z': 4000.0}}
    #            ],
    #       'exclude':
    #           [
    #               {'name': 'Existing_01',
    #                '': True,
    #                'coordinates': [[], [], [], [], [], []]},
    #               {'name': 'Existing_02',
    #                'coordinates': [[], [], [], [], [], []]},
    #               {'name': 'Existing_03',
    #                'coordinates': [[], [], [], [], [], []]}
    #           ],
    #       'include':
    #           [
    #               {'name': 'Site',
    #                'coordinates': [[], [], [], [], [], []]}
    #           ],
    #       'relations':
    #           [
    #               {'name': 'ConnecionMatrix',
    #                'name_sequence': [],
    #                'matrix': [[], [], [], []]}
    #           ]
    #       }
    # AAD_TASK_OVERRIDE = {'AdministrativeBuilding':  {'size':        {'x': 'MODIFIED'}
    #                                                  },
    #                      'AdministrativeCXilding':  {'size':        {'y': 'MODIFIED'}
    #                                                  },
    #                      'PretreatmentBuilding':    {'size':        {'y': 'MODIFIED'},
    #                                                  'position':    {'x': 'MODIFIED',
    #                                                                  'z': 'MODIFIED',
    #                                                                  'q': 'MODIFIED'},
    #                                                  'feeling':     {'x':  'MODIFIED'}
    #                                                  },
    #                      'BiologicalTreatment':     {'rotation':    'MODIFIED',
    #                                                  'elevation':   'MODIFIED'},
    #                      'SecondaryClarifiers':     {'rotation':    'MODIFIED',
    #                                                  'position':    {'z': 'MODIFIED'}
    #                                                  },
    #                      'DewateringBlock':         {}
    #                      }
    # data_to_yaml(AAD_TASK_OVERRIDE, "F:/__AAD__.yaml")
    # dictionary_out = {}
    fullfilename_yaml = "F:/Projects/Projects_SzLA/017_EA/ea_engine/AAD_comm/_assumptions-fromNico/assumptions20210209.yaml"
    fullfilename_json = "F:/Projects/Projects_SzLA/011_Bitcoin/bitcoin/documentation/utxo.json"
    print(yaml_read_in(filename=fullfilename_yaml))
    # #data_to_yaml(data=dictionary_out, filename=fullfilename_out_yaml)

    # data_2_json = []
    # data_to_json(data=data_2_json, filename=fullfilename_json)

    # dictionary_in = json_read_in("F:/Projects/Projects_SzLA/017_EA/ea_engine/AAD_comm/_tasks-AAD/arrangement_input (808).json")
    # print(dictionary_in)
    '''------------------------------------------------------------
    - custom_config_info_setup                            - START -
    ------------------------------------------------------------'''
    # _info_setup_request_list = ['Logical_Response_Directcall_export',
    #                             'Fullfilename_Response_Directcall',
    #                             'Fullfilename_Response_Revit',
    #                             'Fullfilename_Log_Resources'
    #                             ]
    # _config_data = {
    #     "Path_Incoming":  "./eaGAD/_tasks-GAD/",
    #     "Path_Response":  "../mifoska/",
    #     "Path_Log":  "./eaGAD/_logfiles-GAD/",
    #     "Logical_Response_Directcall_export":  True,
    #     "Filename_Response_Directcall":  "<id>_<timestamp>_TASK",
    #     "Filename_Response_Directcall_end":  "directcall.json",
    #     "Logical_Response_Genome_export": True,
    #     "Filename_Response_Genome":  "<id>_<timestamp>_GAD-RESULT",
    #     "Filename_Response_Genome_end":  "genes.json",
    #     "Logical_Response_Revit_export": True,
    #     "Filename_Response_Revit":  "<id>_<timestamp>_REVIT",
    #     "Filename_Response_Revit_end":  "export.json",
    #     "Logical_Log_Data_export":  True,
    #     "Filename_Log_Resources":  "<id>_<timestamp>_Log-Resource.json",
    #     "Filename_Log_Settings":  "<id>_<timestamp>_Log-Settings.json"}
    # _config_data_abspath = 'F:/Projects/Projects_SzLA/017_EA/ea_engine'
    #
    # dictionary = custom_config_info_setup(info_setup_request_list=_info_setup_request_list,
    #                                       config_data=_config_data,
    #                                       config_data_abspath=_config_data_abspath,
    #                                       messaging=True,
    #                                       devswitch=True)
    # MeOp.si_compact_data(dictionary)
    # print(dictionary)
    '''------------------------------------------------------------
    - custom_config_info_setup                            - ENDED -
    ------------------------------------------------------------'''
    '''------------------------------------------------------------
    - directoryseeker_downtree_by_bookmark                - START -
    ------------------------------------------------------------'''
    # print(directoryseeker_downtree_by_bookmark.__doc__)
    # _directory = "f:/dir_a\\dir_b/dir_c\dir_d/"
    # _marker = "__root__.py"
    # print(directoryseeker_downtree_by_bookmark(_directory, _marker))
    '''------------------------------------------------------------
    - directoryseeker_downtree_by_bookmark                - ENDED -
    ------------------------------------------------------------'''

    '''------------------------------------------------------------
    - path_corrector                                      - START -
    ------------------------------------------------------------'''
    # print(path_corrector.__doc__)
    # _original_fullfilename = "F:\\dir_a/dir_b\dir_c\\file.txt"
    # _original_fullfilename = "F:\\dir_a/dir_b\\ndir_c\\file.txt"
    # print("raw_fullfilename: %s" % _original_fullfilename)
    # ans = path_corrector(_original_fullfilename)
    # print("path corrector returns: %s" % ans)
    '''------------------------------------------------------------
    - path_corrector                                      - ENDED -
    ------------------------------------------------------------'''
    '''------------------------------------------------------------
    - fileseeker_downtree                                 - START -
    ------------------------------------------------------------'''
    # print(fileseeker_downtree.__doc__)
    # _original_fullfilename = "F:/dir_a/dir_b/dir_c/BIP039.yaml"
    # print("answer: %s" % fileseeker_downtree(_original_fullfilename))
    '''------------------------------------------------------------
    - fileseeker_downtree                                 - ENDED -
    ------------------------------------------------------------'''

    '''------------------------------------------------------------
    - dev_prompt_dictionary_read_in                       - START -
    ------------------------------------------------------------'''
    # print(dev_prompt_dictionary_read_in.__doc__)
    # print(dev_prompt_dictionary_read_in())
    '''------------------------------------------------------------
    - dev_prompt_dictionary_read_in                       - ENDED -
    ------------------------------------------------------------'''

    '''------------------------------------------------------------
    - txt_read_in                                         - START -
    ------------------------------------------------------------'''
    # szar = txt_read_in("F:/seeddict.txt",
    #                    logical=False,
    #                    nullbyte=False)
    # print(szar)
    '''------------------------------------------------------------
    - txt_read_in                                         - ENDED -
    ------------------------------------------------------------'''
    '''------------------------------------------------------------
    - read_config_settings                                - START -
    ------------------------------------------------------------'''
    # data = read_config_settings(file="_Variable_dict.txt")
    # print(data)
    '''------------------------------------------------------------
    - read_config_settings                                - ENDED -
    ------------------------------------------------------------'''
    '''------------------------------------------------------------
    - data_to_yaml + data_to_json                         - START -
    ------------------------------------------------------------'''
    # print(data_to_yaml.__doc__)
    # print(data_to_json.__doc__)
    # dictionary_out =   {0: '1',     1: '2',     2: '3',     3: '4',     4: '5',     5: '6',     6: '7',     7: '8',
    #                     8: '9',     9: 'A',     10: 'B',    11: 'C',    12: 'D',    13: 'E',    14: 'F',    15: 'G',
    #                     16: 'H',    17: 'J',    18: 'K',    19: 'L',    20: 'M',    21: 'N',    22: 'P',    23: 'Q',
    #                     24: 'R',    25: 'S',    26: 'T',    27: 'U',    28: 'V',    29: 'W',    30: 'X',    31: 'Y',
    #                     32: 'Z',    33: 'a',    34: 'b',    35: 'c',    36: 'd',    37: 'e',    38: 'f',    39: 'g',
    #                     40: 'h',    41: 'i',    42: 'j',    43: 'k',    44: 'm',    45: 'n',    46: 'o',    47: 'p',
    #                     48: 'q',    49: 'r',    50: 's',    51: 't',    52: 'u',    53: 'v',    54: 'w',    55: 'x',
    #                     56: 'y',    57: 'z'}
    # fullfilename_out_yaml = "F:/Projects/Projects_SzLA/011_Bitcoin/bitcoin/documentation/BIP039.yaml"
    # fullfilename_out_json = "F:/Projects/Projects_SzLA/011_Bitcoin/bitcoin/documentation/BIP039.json"
    # dictionary_out = {0: 'abandon',     1: 'ability',   2: 'able',      3: 'about',     4: 'above',     5: 'absent',
    #                   6: 'absorb',      7: 'abstract',  8: 'absurd',    9: 'abuse',     10: 'access',   11: 'accident'}
    # dictionary_try = {0: 'zero', '1': 1, 2.1: "twopointone", "3": 3.0, 'list': [0, 1, 2],
    #                   "di": {'1': 1, 1: 1}, 'bool': False, True: 2, (1, 2): 2}
    # list_out = [0, 1, "2", "three", [4, 4, 4], {1: [1, 2], "two": False}]
    #
    # data_to_be_processed = dictionary_try
    #
    # purefilename = 'BIP039'
    # fullpath_in = "f:\\"
    # fullfilename_out_yaml = fullpath_in + purefilename + ".yaml"
    # fullfilename_out_json = fullpath_in + purefilename + ".json"
    # data_to_yaml(data=dictionary_out, filename=fullfilename_out_yaml)
    # data_to_json(data=dictionary_out, filename=fullfilename_out_json)
    '''------------------------------------------------------------
    - data_to_yaml + data_to_json                         - ENDED -
    ------------------------------------------------------------'''

    '''------------------------------------------------------------
    - json_read_in + yaml_read_in                         - START -
    ------------------------------------------------------------'''
    # purefilename = 'BIP039'
    # fullpath_in = "f:\\"
    # fullfilename_out_yaml = fullpath_in + purefilename + ".yaml"
    # fullfilename_out_json = fullpath_in + purefilename + ".json"
    # print('as exported:')
    # print(data_to_be_processed)
    # print(yaml_read_in.__doc__)
    # print(json_read_in.__doc__)
    # print("yaml read in:")
    # print(yaml_read_in(filename=fullfilename_out_yaml))
    '''
    print("json read in:")
    # fullfilename_out_json = "F:/Projects/Projects_SzLA/017_EA/ea_engine/eaGAD/_results-GAD/Thread-#0DCtest_20200528-144325_TASK_directcall.json"
    fullfilename_in_yaml = "F:/Projects/Projects_SzLA/017_EA/ea_engine/assumptions.yaml"
    print(yaml_read_in(filename=fullfilename_in_yaml))
    '''
    '''------------------------------------------------------------
    - json_read_in + yaml_read_in                         - START -
    ------------------------------------------------------------'''

    # adat = json_read_in("F:/BIP039.json")
    # print(adat)

    # data_to_yaml(data=adat, filename="F:/BIP039.yaml")


    # szar = txt_read_in("F:/Projects/Projects_SzLA/017_EA/ea_engine/_EvoConfig_FPO.txt",
    #                     logical=False,
    #                     nullbyte=False)
    #
    # filename = '_GraphicsSettings_Translator.yml'
    # filename = '_GraphicsSettings_Translator.txt'
    # szar = read_config_settings(filename)
    # print(szar)

    # path = "F:/Projects/Projects_SzLA/016_TravellingSalesmanProblem/_settings/"
    # path = "F:/Projects/Projects_SzLA/004_FloorPlanOptimizer/_settings/_101/"
    # path = "F:/Projects/Projects_SzLA/004_FloorPlanOptimizer/_settings/"
    # li = ["EvoSettings-_GeneralParameters", "EvoSettings-EnvironmentalParameters",
    #      "EvoSettings-EvolutionMechanics", "EvoSettings-PopulationSizes",
    #      "EvoSettings-SelectionMechanics", "EvoSettings-TerminationConditions"]
    # li = ["_EvoSettings-Default"]
    # path = ""
    # li = ["_GraphicsSettings_Translator", "_AnimationSettings", "_GraphicsSettings_Grid", "_GraphicsSettings_Site"]
    # txt_to_yaml_file_duplicator(filenames=li, fullpath=path)

    data1 = {
        'DocumentationInput': {'DocumentationSets': None},
        'ModelInput':
            {'LevelList': None,
             'WallList': None,
             'FloorList': None,
             'PadList': None,
             'RoomList': None,
             'BeamList': None,
             'ColumnList': None,
             'OpeningList': None,
             'Topography': {'Id': 'ec785ee9-dced-4a15-b329-db5373db0439',
                            'SitePoints': [
                                {'X': -48564.0, 'Y': -42493.0, 'Z': 0.0},
                                {'X': -48564.0, 'Y': 95200.0, 'Z': 0.0},
                                {'X': 267972.0, 'Y': 95200.0, 'Z': 0.0},
                                {'X': 267972.0, 'Y': -42493.0, 'Z': 0.0}
                            ]
                            },
             'ReactorModules': None,
             'CircularCollector': None,
             'EnclosureCollector': None,
             'SiteCollector':
                 {'EntranceElement': None,
                  'EarthFill': None,
                  'BackfilledEarth': None,
                  'RoadFcr': None,
                  'RoadAs': None},
             'ProjectData':
                 {'EnclosureType': '',
                  'Technology': 16,
                  'ProjectName': 'validation test 3',
                  'ProjectNumber': '4702',
                  'ClientName': 'Bánki Orsi',
                  'TypeOfDesign': 'Concept',
                  'Capacity': 125.0},
             'BoundingBoxList': None,
             'EquipmentList': {'EquipmentPlaceHolderList': [
                 {'Id': '9200863c-b979-4a11-9232-99ef6e42613d',
                  'LevelName': 'level at 0.0',
                  'OffsetFromLevel': 0,
                  'TypeName': 'EquipmentPlaceHolder',
                  'JsonXyz': {'X': 224672.0, 'Y': 36650.0, 'Z': 0.0},
                  'Rotation': 0,
                  'Height': 2000.0,
                  'Width': 1000.0,
                  'Length': 1500.0,
                  'SubTypeName': 'Pump'}
                  ]
             }
             },
        'is_error': False,
        'is_warning': False,
        'info_message': {},
        'error_message': {},
        'warning_message': {},
        'exception_message': {},
        'is_info': False,
        'is_success': True,
        'is_exception': False
        }

    data2 = {
        'is_error': False,
        'is_warning': False,
        'info_message': {},
        'error_message': {},
        'warning_message': {},
        'exception_message': {},
        'is_info': False,
        'is_success': True,
        'is_exception': False,
        'DocumentationInput': {'DocumentationSets': None},
        'ModelInput':
            {'LevelList': None,
             'WallList': None,
             'FloorList': None,
             'PadList': None,
             'RoomList': None,
             'BeamList': None,
             'ColumnList': None,
             'OpeningList': None,
             'Topography': {'Id': 'ec785ee9-dced-4a15-b329-db5373db0439',
                            'SitePoints': [
                                {'X': -48564.0, 'Y': -42493.0, 'Z': 0.0},
                                {'X': -48564.0, 'Y': 95200.0, 'Z': 0.0},
                                {'X': 267972.0, 'Y': 95200.0, 'Z': 0.0},
                                {'X': 267972.0, 'Y': -42493.0, 'Z': 0.0}
                            ]
                            },
             'ReactorModules': None,
             'CircularCollector': None,
             'EnclosureCollector': None,
             'SiteCollector':
                 {'EntranceElement': None,
                  'EarthFill': None,
                  'BackfilledEarth': None,
                  'RoadFcr': None,
                  'RoadAs': None},
             'ProjectData':
                 {'EnclosureType': '',
                  'Technology': 16,
                  'ProjectName': 'validation test 3',
                  'ProjectNumber': '4702',
                  'ClientName': 'Bánki Orsi',
                  'TypeOfDesign': 'Concept',
                  'Capacity': 125.0},
             'BoundingBoxList': None,
             'EquipmentList': {'EquipmentPlaceHolderList': [
                 {'Id': '9200863c-b979-4a11-9232-99ef6e42613d',
                  'LevelName': 'level at 0.0',
                  'OffsetFromLevel': 0,
                  'TypeName': 'EquipmentPlaceHolder',
                  'JsonXyz': {'X': 224672.0, 'Y': 36650.0, 'Z': 0.0},
                  'Rotation': 0,
                  'Height': 2000.0,
                  'Width': 1000.0,
                  'Length': 1500.0,
                  'SubTypeName': 'Pump'}
             ]
             }
             }
    }


