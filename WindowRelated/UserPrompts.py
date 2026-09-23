"""
Use of words with examples:
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

General module developed by Szilard Gabor Ladanyi to be used across several applications.
All programs here are courtesy of the author.
"""

import os
from pyaml import yaml
import json
import tkinter as tk  # only to be used with Python 3.x versions
from tkinter import filedialog


# --- BASIC read-in functions ----------------------------------------------------------------- START ------------
# json and yaml read in included here to avoid dependency to other modules!
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

# --- BASIC read-in functions ----------------------------------------------------------------- ENDED ------------


def user_prompt_window_file_select(default_dir: str = "/") -> str:
    """=== Function name: user_prompt_window_file_select ===============================================================
    Script prompts user to enter a filename via window entry. Using Open command as reference.
    It returns a string of the name of the file. (eventually to be opened)
    ATTENTION! File itself will not be opened!
    :param default_dir: str - the location the window opens when popping up
    :return str - fullfilename of file (absolute path)
    ============================================================================================== by Sziller ==="""
    if not os.path.exists(os.path.abspath(default_dir)): default_dir = "/"
    root = tk.Tk()
    root.attributes("-topmost", True)
    root.withdraw()
    file_path = filedialog.askopenfilename(initialdir=default_dir)
    if isinstance(file_path, tuple): file_path = ""
    root.destroy()
    return file_path


def user_prompt_window_directory_select(default_dir: str = "/") -> str:
    """=== Function name: user_prompt_window_directory_select ==========================================================
    Script prompts user to enter a directory via window entry.
    It returns a string of the name of the directory.
    ATTENTION! Directory itself will not be opened!
    :param default_dir: str - the location the window opens when popping up
    :return str - fullpath representing directory (absolute path)
    ============================================================================================== by Sziller ==="""
    if not os.path.exists(os.path.abspath(default_dir)): default_dir = "/"
    root = tk.Tk()
    root.attributes("-topmost", True)
    root.withdraw()
    dir_path = filedialog.askdirectory(initialdir=default_dir)
    if isinstance(dir_path, tuple): dir_path = ""
    root.destroy()
    return dir_path


def user_prompt_window_file_save(default_dir: str = "/") -> str:
    """=== Function name: user_prompt_window_file_save =================================================================
    Script prompts user to enter a filename via window entry. Using Save command as reference.
    It returns a string of the name of the file. (eventually to be saved)
    ATTENTION! File itself will not be saved!
    :param default_dir: str - the location the window opens when popping up
    :return str - fullfilename of file (absolute path)
    ============================================================================================== by Sziller ==="""
    if not os.path.exists(os.path.abspath(default_dir)): default_dir = "/"
    root = tk.Tk()
    root.attributes("-topmost", True)
    root.withdraw()
    file_path = filedialog.asksaveasfilename(initialdir=default_dir)
    root.destroy()
    return file_path


def dev_prompt_dictionary_read_in(default_dir: str = "/") -> dict:
    """=== Function name: dev_prompt_dictionary_read_in ================================================================
    Script helps quick opening a file stored dictionary
    :param default_dir: str - the location the window opens when popping up
    :return - dictionary: containing said data
    ============================================================================================== by Sziller ==="""
    fullfilename = user_prompt_window_file_select(default_dir=default_dir)
    if fullfilename.lower().endswith(('.json', '.jsn')):
        dc = json_read_in(filename=fullfilename)
    elif fullfilename.lower().endswith(('.yaml', '.yml')):
        dc = yaml_read_in(filename=fullfilename)
    else:
        print("ERROR! No matching data extension! - sais: >dev_prompt_dictionary_read_in< at UserPrompts.py")
        dc = {}
    return dc


if __name__ == "__main__":
    """------------------------------------------------------------
    - user_prompt_window_directory_select                   START -
    ------------------------------------------------------------"""
    # print(user_prompt_window_directory_select())
    """------------------------------------------------------------
    - user_prompt_window_directory_select                   ENDED -
    ------------------------------------------------------------"""

    """------------------------------------------------------------
    - user_prompt_window_file_select                        START -
    ------------------------------------------------------------"""
    # print(user_prompt_window_file_select())
    """------------------------------------------------------------
    - user_prompt_window_file_select                        ENDED -
    ------------------------------------------------------------"""

    """------------------------------------------------------------
    - user_prompt_window_file_select                        START -
    ------------------------------------------------------------"""
    # print(user_prompt_window_file_save())
    """------------------------------------------------------------
    - user_prompt_window_file_select                        ENDED -
    ------------------------------------------------------------"""

    """------------------------------------------------------------
    - dev_prompt_dictionary_read_in                         START -
    ------------------------------------------------------------"""
    print(dev_prompt_dictionary_read_in())
    """------------------------------------------------------------
    - dev_prompt_dictionary_read_in                         START -
    ------------------------------------------------------------"""
    pass
