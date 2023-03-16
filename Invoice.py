"""
General accounting software
"""
import collections as Coll
import yaml
from kivy.core.window import Window
from FileProcessing import FileRelatedOperations as FiRO
from WindowRelated import UserPrompts as UsPr



def validate_user_input(vtype: type = int):
    """=== Function name: validate_user_input ==========================================================================
    A possibly recursive interface script to validate user entries based on data type.
    A prompt asks you to keyboard enter data.
    :param vtype:
    :return:
    ============================================================================================== by Sziller ==="""
    valid = False
    if vtype == list:
        returned_list = []
        toadd = True
        while toadd:
            toadd = validate_user_input(vtype=str)
            returned_list.append(toadd)
        data = returned_list[:-1]
    else:
        while not valid:
            try:
                data = vtype(input("...data type - %s: " % vtype))
                valid = True
            except ValueError:
                valid = False
    return data


class Spending:
    def __init__(self):
        self.common_currency: str = "€"  # currency in which you pay the tax: should be fixed!
        self.value_in_common_currency = 0  # invoice value in the currency you pay the tax
        self.PAYED_SUM_to_write_off: float = 0  # the actual value you will write off in the taxing currency
        self.payed_sum: float = 0  # the sum you payed in whatever currency
        self.vat_rate: float = 0  # VAT rate for this type of expenditure
        self.vat: float = 0  # actual vat value in the taxing currency
        self.VAT_to_write_off = 0  # total vat value you can write off in the taxing currency
        self.used_currency: str = "€"  # currency you payed in
        self.spending_date: int = 20000101  # integer formatted date of the expenditure
        self.payment_method: str = "cash"  # how did you pay
        self.other_pier: str = ""  # hwo did you pay to or receive payment from
        self.inland_eu: str = "inland"  # home country of EU
        self.category: str = "buro"  # VAT category
        self.groups: list = []  # your private info
        self.is_there_an_invoice: bool = False  # boolean to mark invoice's existence
        self.invoice_date: int = None  # date the invoice was issued
        self.invoice_nr: str = ""  # if invoice has a nr, fill it in here
        self.remarks: str = "N/A"
        self.years_active: list = None
        self.conditional_init()
        self._staticbaseargs_ = {'common_currency': self.common_currency}
        self._dynamicdata_ = Coll.OrderedDict(
            {'value_in_common_currency': self.calc_value_in_common_currency,
             'vat_rate': self.define_vat_rate,
             'vat': self.calc_vat,
             'invoice_date': self.fill_in_invoice_date,
             'PAYED_SUM_to_write_off': self.calc_sum_to_wo,
             'VAT_to_write_off': self.calc_vat_to_wo,
             'years_active': self.calc_years})
        self._staticargdata_ = Coll.OrderedDict(
            {"payed_sum":           {"prompt": " >  Enter numerical value of the PAYED SUM                 : ",
                                     "restrict": None,
                                     "argtype": float},
             "used_currency":       {"prompt": " >  Used CURRENCY - (E)uro, (F)t or (B)tc                  : ",
                                     "restrict": {"e": '€', "f": 'ft', "b": 'btc'},
                                     "argtype": str},
             "spending_date":       {"prompt": " >  SPENDING DATE of the sum (yyyymmdd)                    : ",
                                     "restrict": None,
                                     "argtype": int},
             "payment_method":      {"prompt": " >  Payment METHOD - (C)ash, (T)ransfer, (B)lockchain or (N)/A    : ",
                                     "restrict": {"c": "cash", "t": "transfer", "b": "blockchain", "n": "N/A"},
                                     "argtype": str},
             "other_pier":          {"prompt": " >  Who did you pay to or did you receive payment from     ? ",
                                     "restrict": None,
                                     "argtype": str},
             "inland_eu":           {"prompt": " >  Is it (I)nland or (E)u                                 ? ",
                                     "restrict": {"i": "inland", "e": "eu"},
                                     "argtype": str},
             "category":            {"prompt": " >  Enter ACCOUNTING CATEGORY!                             : ",
                                     "restrict": {"": "N/A",
                                                  "buro": "buro",
                                                  "stber": "steuerberatung",
                                                  "einr": "einrichtung",
                                                  "betrieb": "betriebsbedarf",
                                                  "port-o": "porto-ohne-ust",
                                                  "port-m": "porto-mit-ust",
                                                  "werk": "werkzeug",
                                                  "werk3": "werkzeug-mehrjaehrige-abschreibung",
                                                  "auto": "auto",
                                                  "raum": "raum",
                                                  "bk": "betriebskosten",
                                                  "bew": "bewirtung",
                                                  "werb": "werbung",
                                                  "handyv": "handy-vertrag",
                                                  "handyp": "handy-prepaid",
                                                  "lit": "fachliteratur",
                                                  "nacht": "ubernachtung",
                                                  "krank": "krankenversicherung",
                                                  "pflege": "pfegeversicherung",
                                                  "hausr": "hausratversicherung",
                                                  "haft": "haftpflichtversicherung",
                                                  "rente": "rentenversicherung",
                                                  "reise": "reiseversicherung",
                                                  "fest": "festnetz",
                                                  "db": "bahn",
                                                  "bvg": "bvg",
                                                  "eingang": "eingang",
                                                  "honorar": "honorar",
                                                  "ustv": "umsatzsteuer-vorauszahlung",
                                                  "eksv": "einkommen-kirchen-soli-vorauszahlung",
                                                  },
                                     "argtype": str},
             "groups":              {"prompt": " >  List of groups as reminder   . (Enter closes list)     : ",
                                     "restrict": {"": "N/A", "buro": "buro", "porto": "porto", "werkzeug": "werkzeug"},
                                     "argtype": list},
             "remarks":             {"prompt": " >  .... any comments: ",
                                     "restrict": None,
                                     "argtype": str},
             "is_there_an_invoice": {},
             "invoice_date":        {"prompt": " >  INVOICE DATE. (enter '0' if it's the spending date)    : ",
                                     "restrict": None,
                                     "argtype": int},
             "invoice_nr":          {"prompt": " >  ID of the invoice                                      : ",
                                     "restrict": None,
                                     "argtype": str}
             })

    def get_id_key(self):
        return (self.other_pier, self.invoice_nr, self.payed_sum)

    def calc_value_in_common_currency(self):
        """

        :return:
        """
        if self.common_currency == self.used_currency:
            self.value_in_common_currency = self.payed_sum
        else:
            lookup_rates = {'ft': EUR_HUF_X_RATES,
                            'btc': EUR_BTC_X_RATES}[self.used_currency]
            self.value_in_common_currency = self.payed_sum / x_rate_lookup(date=self.spending_date, dictionary=lookup_rates)

    def define_vat_rate(self):
        """

        :return:
        """
        if self.inland_eu == "eu":
            self.vat_rate = VAT_EU
        elif self.inland_eu == "inland":
            self.vat_rate = VAT_DE_VALUES[VAT_DE[self.category]]
        else:
            print("ERROR! Unknown <inland_eu> code!")
            return False

    def calc_vat(self):
        """=== Method name: calc_vat =================================================================================
        Method calculates VAT value. UPDATED 2020-09-16 as it was invalid!
        :var self.value_in_common_currency: calculated base gross value
        :return:
        ========================================================================================== by Sziller ==="""
        self.vat = self.value_in_common_currency * ( 1 - ( 1 / ( 1 + (0.01 * self.vat_rate)) ) )

    def calc_sum_to_wo(self):
        if self.category in CATEGORY_PERCENTAGES.keys():
            self.PAYED_SUM_to_write_off = self.value_in_common_currency * CATEGORY_PERCENTAGES[self.category] * 0.01
        else:
            self.PAYED_SUM_to_write_off = self.value_in_common_currency

    def calc_vat_to_wo(self):
        if self.category in CATEGORY_PERCENTAGES.keys():
            self.VAT_to_write_off = self.vat * CATEGORY_PERCENTAGES[self.category] * 0.01
        else:
            self.VAT_to_write_off = self.vat

    def fill_in_invoice_date(self):
        """
        :return:
        """
        if self.invoice_date == 0:
            self.invoice_date = "N/A"

    def calc_years(self):
        """

        :return:
        """
        self.years_active = [int(str(self.spending_date)[:4])]
        if VAT_DE[self.category] == "mehrjaehrig":
            self.years_active.append(self.years_active[-1] + 1)
            self.years_active.append(self.years_active[-1] + 1)

    def update_from_dict_inclusive_source_driven(self, dictionary, exclude_list: list=list()):
        """
        Updater overrides (includes into the process) everytihng, that isn't explicitly excluded.
        :param dictionary:
        :param exclude_list:
        :return:
        """
        for key, value in dictionary.items():
            if value not in exclude_list:
                setattr(self, key, value)

    def update_from_dict_exclusive_source_driven(self, dictionary, include_list: list=list()):
        """
        Updater skipps (excludes from the process) everytihng, except what isn't explicitly included.
        :param dictionary:
        :param include_list:
        :return:
        """
        for key, value in dictionary.items():
            if value in include_list:
                setattr(self, key, value)

    def update_from_dict_exclusive_target_driven(self, dictionary, include_list: list = list()):
        """=== Function name: ==========================================================================================
        Updater skipps (excludes from the process) everytihng, except what isn't explicitly included.
        :param dictionary:
        :param include_list:
        :return:
        ========================================================================================== by Sziller ==="""
        for key, value in dictionary.items():
            target_value = getattr(self, key)
            if target_value in include_list:
                setattr(self, key, value)

    def conditional_init(self):
        if self.is_there_an_invoice:
            self.invoice_date = None
            self.invoice_nr = None
        else:
            self.invoice_date = False
            self.invoice_nr = False

    def variable_list_noinvoice(self):
        return sorted([attr for attr in dir(self) if not (callable(getattr(self, attr)) or attr.startswith("__"))
                       and attr not in['is_there_an_invoice']
                       and "invoice" not in attr
                       and not attr.startswith("_staticargdata_")
                       and not attr.startswith("_limited_")
                       ])

    def variable_list_invoice(self):
        return [attr for attr in dir(self) if not (callable(getattr(self, attr)) or attr.startswith("__"))
                and attr not in['is_there_an_invoice']
                and not attr.startswith("_staticargdata_")
                and not attr.startswith("_limited_")
                # and not attr.startswith("spending_")
                ]

    def update_dynamicdata(self):
        for arg, funct in self._dynamicdata_.items():
            funct()

    def return_dict(self):
        answer = {}
        for attr in dir(self):
            if (not callable(getattr(self, attr)) and not attr.startswith("__") and attr not in ['_staticargdata_'])\
                    or attr in['payload_function']:
                answer[attr] = getattr(self, attr)
            else:
                print("ommit: {}".format(attr))
        sequence = list(self._staticargdata_.keys()) + \
                   list(self._staticbaseargs_.keys()) + \
                   list(self._dynamicdata_.keys())
        returned = Coll.OrderedDict({key: answer[key] for key in sequence})
        print("+++++++++++++")
        for k, v in returned.items():
            print("{} - {}".format(k, v))
        print("+++++++++++++")
        return returned


    def fill_in_ui(self):
        """

        :return:
        """
        accepted = False  # set user's acceptance to False
        answer_0 = False
        while answer_0 not in ['y', 'Y', 'yes', 'Yes', 'yES', 'YES', 'n', 'N', 'no', 'No', 'nO', 'NO']:
            answer_0 = input("Is there an invoice? ")
        if answer_0 in ['y', 'Y', 'yes', 'Yes', 'yES', 'YES']:
            self.is_there_an_invoice = True
            list_of_args = self.variable_list_invoice()
        else:
            self.is_there_an_invoice = False
            list_of_args = self.variable_list_noinvoice()
        self.conditional_init()
        result = {}

        while not accepted:
            for actual_arg in self._staticargdata_:
                if actual_arg in list_of_args:
                    actual_comment = self._staticargdata_[actual_arg]['prompt']
                    actual_type = self._staticargdata_[actual_arg]['argtype']
                    print(actual_comment)
                    if self._staticargdata_[actual_arg]['restrict']:
                        if actual_type != list:
                            loc_answer = None
                            while loc_answer not in self._staticargdata_[actual_arg]['restrict'].keys():
                                loc_answer = validate_user_input(actual_type)
                            newline = self._staticargdata_[actual_arg]['restrict'][loc_answer]
                        else:
                            loc_answer = ["_________"]
                            while set(loc_answer) != set(loc_answer) & set(self._staticargdata_[actual_arg]['restrict'].keys()):
                                print(" -- Please only enter valid categories -- ")
                                loc_answer = validate_user_input(actual_type)
                            # print(loc_answer)
                            newline = [self._staticargdata_[actual_arg]['restrict'][item] for item in loc_answer] # item by item replacement of aliases
                            # print(newline)
                    else:
                        newline = validate_user_input(actual_type)
                    if actual_type == str:
                        result[actual_arg] = newline.lower()
                    else:
                        result[actual_arg] = newline

            answer_1 = False
            self.update_from_dict_inclusive_source_driven(dictionary=result, exclude_list=list())
            print("--------------------------------")
            self.update_dynamicdata()
            data = self.return_dict()
            for k, v in data.items():
                print("%s: %s" % (k, v))
            print("--------------------------------")
            while answer_1 not in ['y', 'Y', 'yes', 'Yes', 'yES', 'YES', 'n', 'N', 'no', 'No', 'nO', 'NO']:
                answer_1 = input("Do you accept these data? ")
            if answer_1 in ['y', 'Y', 'yes', 'Yes', 'yES', 'YES']:
                accepted = True

        self.update_from_dict_inclusive_source_driven(dictionary=result)
        print("...just entered...")
        data = self.return_dict()
        print(data)
        return result

def accounting_():
    input("----------------------")

def accounting():
    """
    Main code to process all accounting related tasks.
    :return:
    """
    # print("Welcome")
    # input("----------------------")
    finished = False
    read_in_spendings_object_list = []  # empty object list
    read_in_spendings_o_dict_list = []
    out_spendings_o_dict_list = []
    while not finished:  # program keeps retuning until finished...
        print("You have following choices:"
              "\n - (O)pen an existing file, containing previously saved invoices."
              "\n - Enter a (N)ew invoice."
              "\n - (S)ave current dataset."
              "\n - E(X)it")
        print("What do you wanna do?")
        answer_0 = False

        while answer_0 not in ['x', 'X', 'n', 'N', 'd', 'D', 'o', 'O', 's', 'S']:
            answer_0 = input("make your choice: ")

        if answer_0 in ['x', 'X']:
            finished = True
        elif answer_0 in ['n', 'N']:
            position = Spending()
            position.app_ui()
            # position.fill_in_ui()


            read_in_spendings_object_list.append(position)
        elif answer_0 in ['o', 'O']:
            print("'o' - answer: Opening a file.")
            print("Please choose a file to open!")
            fullfilename_open = UsPr.user_prompt_window_file_select()
            print("fullfilename: %s" % fullfilename_open)
        elif answer_0 in ['s', 'S']:
            print("'s' - answer: Saving data to file.")
            print("Please choose a location to save data to!")
            fullfilename_save = UsPr.user_prompt_window_file_save()
            print("fullfilename: %s" % fullfilename_save)
            print(read_in_spendings_object_list)
            read_in_spendings_o_dict_list = convert_obj_to_odict_list(read_in_spendings_object_list)
            read_in_spendings_dict_list = convert_odict_to_dict_list(read_in_spendings_o_dict_list)
            FiRO.data_to_yaml(read_in_spendings_dict_list, filename=fullfilename_save)


def convert_obj_to_odict_list(object_list: list):
    """
    Script converts a list of 'Spending' class objects into a list of ordered dictionaries that include said objects'
    arguments.
    :param object_list: list including 'Spending' type objects.
    :return: list of ordered dictionaries containing the arguments of each instance.
    """
    o_dict_list = []
    for obj in object_list:
        o_dict_list.append(obj.return_dict())
    return o_dict_list


def convert_odict_to_dict_list(o_dict_list: list):
    """

    :param o_dict_list:
    :return:
    """
    dict_list = []
    for o_dict in o_dict_list:
        dict_list.append(dict(o_dict))
    return dict_list


# with open(fullfilename_json_to_save, "w") as outfile:
#     dumped_data = json.dumps(outfile, default=lambda x: answer_data.__dict__, indent=4)
#     outfile.write(dumped_data)
#     outfile.write("\n")

def x_rate_lookup(date: int, dictionary: dict):
    """=== Function name: x_rate_lookup ================================================================================
    Function returns a value assigned to a key which is nearest to the date entered in integer format.
    Used as rate calculator for lookup table style rate history:
    20180205 : 311
    If date does not exist, function takes the nearest PAST date.
    :param date: integer - simple integer range: 2018.03.01. --> 20180301
    :param dictionary: dict - lookup table representing each entry as date:rate
                              20180420 : 300
    :return: a float - the value belonging to the 'date'
    ============================================================================================== by Sziller ==="""
    earliest_date = min(list(dictionary.keys()))
    if date > earliest_date:
        while date not in dictionary.keys():
            date += -1
    else:
        date = earliest_date
    return dictionary[date]



def summarize():
    """=== Function name: summarize ====================================================================================

    :return:
    ============================================================================================== by Sziller ==="""
    sheet_0_lines = []

    print("-------------------------------------------------------------\n"
          "- defining paths:                                     START -\n"
          "-------------------------------------------------------------")
    list_of_in_paths = []
    print("Please mark 1st file containing INCOMING PAYMENTS")
    path_data_in = UsPr.user_prompt_window_file_select()
    data_in = FiRO.yaml_read_in(path_data_in)
    sheet_0_lines.append('_')

    list_of_out_paths = []
    print("Please mark 1st file containing OUTGOING PAYMENTS")
    path_data_out = UsPr.user_prompt_window_file_select()
    list_of_out_paths.append(path_data_out)
    data_out = FiRO.yaml_read_in(path_data_out)
    print("     added following file: %s" % path_data_out)

    print("You can add additional files containing OUTGOING PAYMENTS:")
    out_answer = False
    while out_answer not in ['y', 'Y', 'yes', 'YES', 'yES', 'Yes',
                             'n', 'N', 'no', 'NO', 'nO', 'No']:
        out_answer = input("...please answer yes or no: ")
        if out_answer in ['y', 'Y', 'yes', 'YES', 'yES', 'Yes']:
            path_data_out = UsPr.user_prompt_window_file_select()
            if path_data_out not in list_of_out_paths:
                list_of_out_paths.append(path_data_out)
                data_out = data_out + FiRO.yaml_read_in(path_data_out)
                print("     added following file: %s" % path_data_out)
            else:
                print("     duplicate omitted   : %s" % path_data_out)
            out_answer = False

    print()
    print("-------------------------------------------------------------\n"
          "- defining paths:                                     ENDED -\n"
          "-------------------------------------------------------------")

    print("-------------------------------------------------------------\n"
          "- reading in data                                           -\n"
          "-------------------------------------------------------------")

    data = data_in + data_out
    print("------------------------------------------------- inland ab hier <<<")
    for category in VAT_DE.keys():
        print("------------------------------------------------- %s" % category)
        inland_lohnsteuer_kosten = sum([inv['PAYED_SUM_to_write_off'] for inv in data
                                        if (inv['category'] == category and inv['inland_eu'] == 'inland')])
        inland_umsatzsteuer = sum([inv['VAT_to_write_off'] for inv in data
                                   if (inv['category'] == category and inv['inland_eu'] == 'inland')])
        eu_lohnsteuer_kosten = sum([inv['PAYED_SUM_to_write_off'] for inv in data
                                    if (inv['category'] == category and inv['inland_eu'] == 'eu')])
        eu_umsatzsteuer = sum([inv['VAT_to_write_off'] for inv in data
                               if (inv['category'] == category and inv['inland_eu'] == 'eu')])
        print("inlaendische LOHNSTEUER   kosten     : %s" % round(inland_lohnsteuer_kosten, 2))
        print("eu           LOHNSTEUER   kosten     : %s" % round(eu_lohnsteuer_kosten, 2))
        print("inlaendische UMSATZSTEUER absaetzbar : %s" % round(inland_umsatzsteuer, 2))
        print("eu           UMSATZSTEUER absaetzbar : %s" % round(eu_umsatzsteuer, 2))

    finished = input("push any key to finish...")


EUR_HUF_X_RATES = {20180000: 309.57,
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
                   20181220: 321.95,    20181221: 321.86,   20181227: 321.18,
                   20190000: 322.16,
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
                   20191230: 330.71,    20191231: 330.52,
                   20200000: 329.99,
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
                   20201009: 356.82,    20201012: 356.61,   20201013: 358.81,   20201014: 363.59,   20201015: 365.44,
                   20201016: 364.85,    20201019: 365.07,   20201020: 365.37,   20201021: 364.12,   20201022: 364.75,
                   20201026: 365.01,    20201027: 365.06,   20201028: 367.04,   20201029: 369.03,   20201030: 367.75,
                   20201102: 366.85,    20201103: 363.03,   20201104: 364.12,   20201105: 359.97,   20201106: 358.77,
                   20201109: 358.02,    20201110: 359.03,   20201111: 355.22,   20201112: 354.94,   20201113: 355.35,
                   20201116: 358.08,    20201117: 361.40,   20201118: 361.31,   20201119: 361.40,   20201120: 359.23,
                   20201123: 360.33,    20201124: 360.94,   20201125: 360.96,   20201126: 361.16,   20201127: 361.20,
                   20201130: 360.09,    20201201: 357.37,   20201202: 356.90,   20201203: 359.01,   20201204: 358.62,
                   20201207: 360.06,    20201208: 360.90,   20201209: 357.92,   20201210: 355.72,   20201211: 354.23,
                   20201214: 353.65,    20201215: 354.48,   20201216: 355.34,   20201217: 355.47,   20201218: 357.57,
                   20201221: 361.08,    20201222: 361.58,   20201223: 362.34,   20201228: 363.46,   20201229: 363.73,
                   20201230: 364.59,    20201231: 365.13,
                   20210000: 360.90,
                   20210104: 360.90,    20210105: 361.29,   20210106: 357.27,   20210107: 356.78,   20210108: 359.70,
                   20210111: 360.60,    20210112: 360.60,   20210113: 359.37,   20210114: 359.62,   20210115: 359.30,
                   20210118: 360.63,    20210119: 359.27,   20210120: 357.23,   20210121: 357.25,   20210122: 356.81,
                   20210125: 357.32,    20210126: 358.30,   20210127: 359.78,   20210128: 360.38,   20210129: 358.51,
                   20210201: 356.60,    20210202: 355.20,   20210203: 355.94,   20210204: 355.81,   20210205: 356.44,
                   20210208: 358.19,    20210209: 358.78,   20210210: 358.09,   20210211: 356.76,   20210212: 359.30,
                   20210215: 359.12,    20210216: 357.65,   20210217: 359.05,   20210218: 358.80,   20210219: 358.65,
                   20210222: 359.24,    20210223: 359.61,   20210224: 359.23,   20210225: 360.17,   20210226: 361.01,
                   20210301: 362.82,    20210302: 363.85,   20210303: 363.55,   20210304: 364.56,   20210305: 366.42,
                   20210308: 367.75,    20210309: 366.40,   20210310: 366.83,   20210311: 366.12,   20210312: 366.38,
                   20210316: 367.34,    20210317: 367.46,   20210318: 367.71,   20210319: 368.25,   20210322: 367.33,
                   20210323: 366.90,    20210324: 365.62,   20210325: 364.71,   20210326: 364.13,   20210329: 362.72,
                   20210330: 363.11,    20210331: 363.73,   20210401: 361.93,   20210406: 361.40,   20210407: 360.45,
                   20210408: 358.70,    20210409: 358.67,   20210412: 357.09,   20210413: 358.57,   20210414: 358.94,
                   20210415: 358.91,    20210416: 360.84,   20210419: 361.31,   20210420: 360.97,   20210421: 362.16,
                   20210422: 363.21,    20210423: 363.40,   20210426: 363.85,   20210427: 363.11,   20210428: 362.01,
                   20210429: 361.10,    20210430: 359.59,   20210503: 360.21,   20210504: 360.45,   20210505: 360.08,
                   20210506: 358.72,    20210507: 358.54,   20210510: 358.20,   20210511: 358.71,   20210512: 357.81,
                   20210513: 356.91,    20210514: 356.16,   20210517: 352.47,   20210518: 350.99,   20210519: 351.47,
                   20210520: 349.76,    20210521: 349.51,   20210525: 348.42,   20210526: 350.32,   20210527: 349.16,
                   20210528: 348.00,    20210531: 348.24,   20210601: 347.32,   20210602: 346.38,   20210603: 346.43,
                   20210604: 347.35,    20210607: 345.64,   20210608: 347.37,   20210609: 347.05,   20210610: 346.30,
                   20210611: 346.08,    20210614: 350.14,   20210615: 351.26,   20210616: 351.14,   20210617: 353.79,
                   20210618: 355.38,    20210621: 354.72,   20210622: 353.85,   20210623: 349.28,   20210624: 349.51,
                   20210625: 351.33,    20210628: 351.10,   20210629: 351.13,   20210630: 351.90,   20210701: 351.31,
                   20210702: 351.76,    20210705: 351.44,   20210706: 353.54,   20210707: 354.33,   20210708: 358.10,
                   20210709: 355.98,    20210712: 355.34,   20210713: 356.35,   20210714: 358.65,   20210715: 358.94,
                   20210716: 359.29,    20210719: 360.09,   20210720: 359.55,   20210721: 359.73,   20210722: 359.01,
                   20210723: 358.76,    20210726: 361.48,   20210727: 361.80,   20210728: 359.25,   20210729: 358.81,
                   20210730: 357.62,    20210802: 356.85,   20210803: 355.16,   20210804: 354.80,   20210805: 354.07,
                   20210806: 353.07,    20210809: 354.46,   20210810: 352.58,   20210811: 354.73,   20210812: 353.21,
                   20210813: 352.69,    20210816: 351.86,   20210817: 351.93,   20210818: 351.13,   20210819: 351.48,
                   20210823: 350.07,    20210824: 349.17,   20210825: 347.35,   20210826: 348.83,   20210827: 350.73,
                   20210830: 348.25,    20210831: 348.48,   20210901: 348.43,   20210902: 347.15,   20210903: 348.49,
                   20210906: 347.41,    20210907: 347.79,   20210908: 349.84,   20210909: 351.36,   20210910: 351.10,
                   20210913: 349.77,    20210914: 349.72,   20210915: 349.49,   20210916: 348.90,   20210917: 351.42,
                   20210920: 353.75,    20210921: 352.89,   20210922: 354.30,   20210923: 355.39,   20210924: 356.68,
                   20210927: 357.71,    20210928: 359.41,   20210929: 359.47,   20210930: 360.52,   20211001: 359.21,
                   20211004: 356.21,    20211005: 357.05,   20211006: 359.87,   20211007: 358.42,   20211008: 359.46,
                   20211011: 361.58,    20211012: 359.89,   20211013: 360.34,   20211014: 359.77,   20211015: 359.76,
                   20211018: 360.86,    20211019: 359.99,   20211020: 362.88,   20211021: 361.65,   20211022: 363.24,
                   20211025: 364.46,    20211026: 365.36,   20211027: 365.34,   20211028: 363.84,   20211029: 360.80,
                   20211102: 360.22,    20211103: 359.09,   20211104: 360.19,   20211105: 359.88,   20211108: 359.87,
                   20211109: 362.23,    20211110: 361.53,   20211111: 365.15,   20211112: 365.43,   20211115: 367.08,
                   20211116: 365.64,    20211117: 365.24,   20211118: 363.66,   20211119: 365.03,   20211122: 369.86,
                   20211123: 371.35,    20211124: 368.29,   20211125: 366.69,   20211126: 367.69,   20211129: 368.63,
                   20211130: 366.83,    20211201: 364.35,   20211202: 362.22,   20211203: 363.51,   20211206: 363.94,
                   20211207: 365.65,    20211208: 367.62,   20211209: 365.85,   20211210: 365.75,   20211213: 366.51,
                   20211214: 367.03,    20211215: 368.76,   20211216: 368.92,   20211217: 367.71,   20211220: 367.12,
                   20211221: 367.98,    20211222: 367.94,   20211223: 369.52,   20211227: 371.20,   20211228: 369.52,
                   20211229: 369.55,    20211230: 369.71,   20211231: 369.00,
                   20220000: 367.66,
                   20220103: 367.66,    20220104: 365.44,   20220105: 361.71,   20220106: 361.12,   20220107: 359.36,
                   20220110: 357.88,    20220111: 357.39,   20220112: 356.11,   20220113: 355.15,   20220114: 354.74,
                   20220117: 355.89,    20220118: 356.74,   20220119: 356.48,   20220120: 357.05,   20220121: 357.02,
                   20220124: 358.70,    20220125: 360.52,   20220126: 359.65,   20220127: 358.69,   20220128: 357.28,
                   20220131: 358.11,    20220201: 355.50,   20220202: 355.25,   20220203: 354.66,   20220204: 354.51,
                   20220207: 353.14,    20220208: 353.69,   20220209: 353.15,   20220210: 353.52,   20220211: 353.69,
                   20220214: 357.00,    20220215: 355.52,   20220216: 354.49,   20220217: 356.14,   20220218: 356.35,
                   20220221: 356.11,    20220222: 357.14,   20220223: 356.55,   20220224: 364.45,   20220225: 368.17,
                   20220228: 369.80,    20220301: 372.46,   20220302: 380.47,   20220303: 378.42,   20220304: 381.71,
                   20220307: 397.31,    20220308: 388.08,   20220309: 383.18,   20220310: 380.06,   20220311: 381.23,
                   20220316: 372.20,    20220317: 371.45,   20220318: 373.54,   20220321: 374.54,   20220322: 373.46,
                   20220323: 371.92,    20220324: 375.27,   20220325: 375.18,   20220328: 373.15,   20220329: 372.57,
                   20220330: 367.22,    20220331: 369.62,   20220401: 367.52,   20220404: 368.77,   20220405: 370.49,
                   20220406: 378.43,    20220407: 381.83,   20220408: 377.28,   20220411: 379.99,   20220412: 378.68,
                   20220413: 378.11,    20220414: 376.08,   20220419: 373.19,   20220420: 371.09,   20220421: 371.60,
                   20220422: 371.04,    20220425: 373.14,   20220426: 376.14,   20220427: 380.41,   20220428: 377.37,
                   20220429: 377.12,    20220502: 378.14,   20220503: 382.38,   20220504: 378.93,   20220505: 378.26,
                   20220506: 380.41,    20220509: 383.60,   20220510: 378.86,   20220511: 379.46,   20220512: 382.76,
                   20220513: 384.08,    20220516: 384.69,   20220517: 387.50,   20220518: 385.28,   20220519: 386.01,
                   20220520: 384.58,    20220523: 382.60,   20220524: 383.23,   20220525: 385.03,   20220526: 393.35,
                   20220527: 392.82,    20220530: 393.01,   20220531: 394.05,   20220601: 397.03,   20220602: 394.53,
                   20220603: 394.68,    20220607: 389.61,   20220608: 389.90,   20220609: 394.71,   20220610: 398.12,
                   20220613: 397.69,    20220614: 398.53,   20220615: 398.50,   20220616: 395.56,   20220617: 398.81,
                   20220620: 400.21,    20220621: 396.40,   20220622: 395.46,   20220623: 399.58,   20220624: 400.80,
                   20220627: 403.52,    20220628: 400.72,   20220629: 396.27,   20220630: 396.75,   20220701: 398.74,
                   20220704: 400.02,    20220705: 404.79,   20220706: 409.98,   20220707: 412.97,   20220708: 405.63,
                   20220711: 409.00,    20220712: 413.78,   20220713: 410.43,   20220714: 409.82,   20220715: 404.08,
                   20220718: 403.04,    20220719: 399.10,   20220720: 397.28,   20220721: 401.59,   20220722: 397.40,
                   20220725: 396.36,    20220726: 399.03,   20220727: 404.10,   20220728: 406.68,   20220729: 404.20,
                   20220801: 403.28,    20220802: 397.93,   20220803: 396.01,   20220804: 396.49,   20220805: 394.82,
                   20220808: 392.66,    20220809: 395.02,   20220810: 401.29,   20220811: 394.59,   20220812: 393.04,
                   20220815: 397.33,    20220816: 404.01,   20220817: 406.92,   20220818: 405.05,   20220819: 406.85,
                   20220822: 405.83,    20220823: 410.88,   20220824: 411.24,   20220825: 408.35,   20220826: 409.00,
                   20220829: 410.80,    20220830: 407.29,   20220831: 405.11,   20220901: 401.28,   20220902: 398.96,
                   20220905: 403.83,    20220906: 403.34,   20220907: 401.49,   20220908: 397.57,   20220909: 395.48,
                   20220912: 395.06,    20220913: 396.42,   20220914: 402.09,   20220915: 405.65,   20220916: 405.21,
                   20220919: 400.98,    20220920: 398.90,   20220921: 403.14,   20220922: 406.17,   20220923: 406.29,
                   20220926: 406.50,    20220927: 407.45,   20220928: 411.26,   20220929: 420.21,   20220930: 421.41,
                   20221003: 422.51,    20221004: 417.50,   20221005: 422.40,   20221006: 423.53,   20221007: 423.77,
                   20221010: 426.68,    20221011: 427.89,   20221012: 429.82,   20221013: 432.94,   20221014: 419.61,
                   20221017: 419.20,    20221018: 412.52,   20221019: 412.93,   20221020: 412.46,   20221021: 413.14,
                   20221024: 412.84,    20221025: 412.69,   20221026: 410.61,   20221027: 407.71,   20221028: 412.01,
                   20221102: 408.30,    20221103: 409.54,   20221104: 402.82,   20221107: 401.78,   20221108: 401.10,
                   20221109: 405.05,    20221110: 401.91,   20221111: 403.66,   20221114: 406.16,   20221115: 405.80,
                   20221116: 407.13,    20221117: 411.57,   20221118: 410.50,   20221121: 410.42,   20221122: 408.51,
                   20221123: 405.82,    20221124: 414.44,   20221125: 412.60,   20221128: 408.30,   20221129: 408.04,
                   20221130: 407.67,    20221201: 410.00,   20221202: 408.78,   20221205: 409.36,   20221206: 414.34,
                   20221207: 410.55,    20221208: 414.49,   20221209: 414.94,   20221212: 417.81,   20221213: 411.22,
                   20221214: 408.41,    20221215: 405.73,   20221216: 406.09,   20221219: 403.83,   20221220: 403.16,
                   20221221: 402.64,    20221222: 402.23,   20221223: 400.60,   20221227: 401.96,   20221228: 402.95,
                   20221229: 402.54,    20221230: 400.25,
                   20230102: 400.66,    20230103: 402.81,   20230104: 397.14,   20230105: 395.66,   20230106: 396.68,
                   20230109: 397.10,    20230110: 398.26,   20230111: 400.08,   20230112: 399.29,   20230113: 396.19,
                   20230116: 398.98,    20230117: 399.12,   20230118: 394.81,   20230119: 395.39,   20230120: 395.88,
                   20230123: 394.62,    20230124: 396.68,   20230125: 389.46,   20230126: 388.61,   20230127: 388.18,
                   20230130: 391.96,    20230131: 388.99,   20230201: 390.13,   20230202: 387.69,   20230203: 384.95,
                   20230206: 389.48,    20230207: 392.70,   20230208: 389.61
                   }

VAT_DE = Coll.OrderedDict({'honorar': "standard",
                           'eingang': "standard",
                           "steuerberatung": "standard",
                           'krankenversicherung': "ohne",
                           'pfegeversicherung': "ohne",
                           'rentenversicherung': "ohne",
                           'hausratversicherung': "ohne",
                           'haftpflichtversicherung': "ohne",
                           'reiseversicherung': "ohne",
                           'raum': "ohne",
                           'betriebskosten': "ohne",
                           'buro': 'standard',
                           'einrichtung': 'standard',
                           'betriebsbedarf': "standard",
                           'werkzeug': "standard",
                           'werkzeug-mehrjaehrige-abschreibung': "mehrjaehrig",
                           'porto-ohne-ust': "ohne",
                           'porto-mit-ust': "standard",
                           'fachliteratur': 'ermaesigt',
                           'werbung': "standard",
                           'handy-vertrag': "standard",
                           'handy-prepaid': "ohne",
                           'festnetz': "ohne",
                           'auto': "ohne",
                           'bewirtung': "standard",
                           'ubernachtung': 'ermaesigt',
                           'bahn': "standard",
                           'bvg': "ohne",
                           'umsatzsteuer-vorauszahlung': "na",
                           'einkommen-kirchen-soli-vorauszahlung': "na",
                           'n/a': 'standard'})
VAT_DE_VALUES = {'mehrjaehrig': 19,
                 'standard': 19,
                 'ermaesigt': 7,
                 'ohne': 0,
                 'na': 0}
VAT_EU = 0
CATEGORY_PERCENTAGES = {'n/a': 100,
                        'werkzeug-mehrjaehrige-abschreibung': 33.333,
                        'auto': 0,
                        'raum': 100,
                        'bewirtung': 70,
                        'hausratversicherung': 50,
                        'haftpflichtversicherung': 50,
                        'festnetz': 50
                        }
EUR_BTC_X_RATES = {20180000: 0.01}
if __name__ == "__main__":
    # accounting()
    # summarize()

    # position = Spending()
    # # position.fill_in_ui()
    # position.payed_sum = 1200
    # position.used_currency = "ft"
    # print(position.payed_sum)
    # print(position.used_currency)
    # print(position.common_currency)
    # # print(position.calc_value_in_common_currency())
    # position.update_dynamicdata()
    # print(position.value_in_common_currency)
    # print(position.vat_rate)
    # print(position.vat)




    #
    print(validate_user_input(vtype=int))

    """--------------------------------------------------------------------------
    - x_rate_lookup                                                           START -
    --------------------------------------------------------------------------"""
    # print(x_rate_lookup.__doc__)
    # _table = EUR_HUF_X_RATES
    # _date = 20170223
    # print(x_rate_lookup(date=_date, dictionary=EUR_HUF_X_RATES))
    """--------------------------------------------------------------------------
    - x_rate_lookup                                                           ENDED -
    --------------------------------------------------------------------------"""