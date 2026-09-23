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

General module developed by Sziller to be used across several applications.
All programs here are courtesy of the author.
"""

import openpyxl
from openpyxl import load_workbook
from pyexcel_ods import get_data
from collections import OrderedDict
import time

"""
"""

# FILENAME = 'F:/Projects_SzLA/009_Aukett+Heese/_Automatisierung/05-Excel/IN/8175_Mepl_TuerlisteMuster.xlsx'
# WORKSHEET = 'EG'
# FIRST_ROW = 11
# NAME_COLUMN_ID = 'ID_000'

# a = OrderedDict([('T.U2.36.1', {'ID_007': 'text 01', 'ID_008': 'KORR-03', 'ID_009': 'KORR-04', 'ID_003': 'KORR-02',
#                                 'ID_001': 'KORR-01'}),
#                  ('T.U2.T02.1', {'ID_008': '', 'ID_007': 'text 02', 'ID_003': 'KORR-06', 'ID_001': 'KORR-05'}),
#                  ('T.U2.14.1', {'ID_008': 'KORR-08', 'ID_007': '', 'ID_003': 'KORR-06', 'ID_001': ''}),
#                  ('T.U2.34.1', {'ID_008': 'KORR-09', 'ID_007': 'text 04', 'ID_003': '', 'ID_001': 'korr-08'}),
#                  ('T.U2.35.2', {'ID_008': '', 'ID_007': '', 'ID_003': 'KORR-11', 'ID_001': 'KORR-10'})])


def fill_idcolumn(sheet):
    """
    Fills idcolumn dictionary
    :param sheet:
    :return:
    """
    idcol = {}  # stores column number of 'ID_<>'
    for row in sheet:
        for cell in row:
            if cell.value is not None and type(cell.value) is str:
                if 'ID_' in cell.value:
                    idcol[cell.value] = cell.col_idx
    return idcol


def insert_xls(sheet, file, filename, name_cell, first_row, idcol, odict):
    """
    Inserts the keys of the OrderedDict into xls based on the name_cell id
    :param sheet:
    :param file:
    :param filename:
    :param name_cell:
    :param first_row:
    :param idcol:
    :param odict:
    :return:
    """
    counter = 0
    for name in odict:
        sheet.cell(row=first_row + counter, column=idcol[name_cell]).value = name
        counter += 1
    file.save(filename)


def update_xls(sheet, file, filename, idcol, odict):
    """
    Updates xls file based on the OrderedDict
    :param sheet:
    :param file:
    :param filename:
    :param idcol:
    :param odict:
    :return:
    """
    nf = []
    for row in sheet:
        for cell in row:
            if cell.value is not None and type(cell.value) is str:
                if cell.value in odict.keys():
                    for k in odict[cell.value]:
                        if k in idcol:
                            sheet.cell(row=cell.row, column=idcol[k]).value = odict[cell.value][k]
                        else:
                            nf.append(k)
    time.sleep(2)
    file.save(filename)
    if len(nf) > 0:
        return {'not found:': nf}


def write_od_to_excel(fn, ws, nc, fr, od):
    """

    :param fn:
    :param ws:
    :param nc:
    :param fr:
    :param od:
    :return:
    """
    xfile = openpyxl.load_workbook(fn)
    worksheet = xfile.get_sheet_by_name(ws)
    idcolumn = fill_idcolumn(sheet=worksheet)
    insert_xls(sheet=worksheet, file=xfile, filename=fn,  name_cell=nc, first_row=fr, idcol=idcolumn, odict=od)
    update_xls(sheet=worksheet, file=xfile, filename=fn, idcol=idcolumn, odict=od)


def read_excel_template2(filename):
    """

    :param filename:
    :return:
    """
    wb = load_workbook(filename = filename)
    for ws in wb.worksheets:
        print("Worksheet %s include %d tables:" % (ws.title, len(ws._tables)))
        print(ws["a4"].value)


def read_ods(filename, sheetname, mode=None):
    """=== Function name: read_ods =====================================================================================
    Function read in data from an ods extension file.
    :param filename:
    :param sheetname:
    :param mode:
    :return:
    ============================================================================================== by Sziller ==="""
    as_read_list = get_data(filename)[sheetname]
    as_answered = []
    for line in as_read_list:
        line = [_ if _ != '' else None for _ in line]
        as_answered.append(line)
    return as_answered


def read_excel(filename, sheetname, mode="dict"):
    """=== Function name: read_excel ===================================================================================
    Function reads in data from an xlsx type Excel file, and sorts it into a primitive list or a dictionary.
    If using list mode, actual cell values occupy the spaces.
    list is a 2 dimensional tensor, of values in a row, and rows in a column. Basically as in html tables.
    :param filename: string - representing full filename
    :param sheetname: name of sheet you want to read
    :param mode: use "list" for an expected behaviour!
    :return:
    ============================================================================================== by Sziller ==="""
    workbook = openpyxl.load_workbook(filename=filename, data_only=True)
    worksheet = workbook[sheetname]
    # for sheet in workbook:
    #     print(sheet.title)
    if mode == "dict":
        answer = {}
        for line in worksheet:
            for _ in line:
                # print(_)
                answer[str(_.column)+str(_.row)] = _
    elif mode == "list":
        answer = []
        for line in worksheet:
            currentline = []
            for _ in line:
                currentline.append(_.value)  # _.value if you need the formula
            answer.append(currentline)
    else:
        answer = None
    return answer


if __name__ == "__main__":
    # write_od_to_excel(fn=FILENAME, ws=WORKSHEET, nc=NAME_COLUMN_ID, fr=FIRST_ROW, od=a)
    '''-----------------------------------------------------------
    - read_excel                                           START -
    -----------------------------------------------------------'''
    print(read_excel.__doc__)
    answer = read_excel(
        filename="F:/Projects/Projects_SzLA/001_GeneralCoding/Pyton/general_package_development/"
                 "FileProcessing/assets/sample.xlsx",
        sheetname="Table-A",
        mode="list")
    print(answer)
    '''-----------------------------------------------------------
    - read_excel                                           ENDED -
    -----------------------------------------------------------'''

    '''-----------------------------------------------------------
    - read_ods                                             START -
    -----------------------------------------------------------'''
    print(read_ods.__doc__)
    answer = read_ods(
        filename="F:/Projects/Projects_SzLA/001_GeneralCoding/Pyton/general_package_development/"
                 "FileProcessing/assets/sample.ods",
        sheetname="Table-A",
        mode="list")
    print(answer)
    '''-----------------------------------------------------------
    - read_ods                                             ENDED -
    -----------------------------------------------------------'''
