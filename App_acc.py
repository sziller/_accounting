import os
import sys
import kivy
from pyaml import yaml
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.stacklayout import StackLayout
from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.animation import Animation
import collections as Coll
from kivy.graphics import Color
from kivy.graphics import Rectangle

import Invoice as Inv
# from Invoice import Spending

CATEGORIES = {  "": "N/A",
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
                "eksv": "einkommen-kirchen-soli-vorauszahlung"}


class AccScreenManager(ScreenManager):
    def __init__(self, **kwargs):
        super(AccScreenManager, self).__init__(**kwargs)
        self.statedict = {
            "screen_intro": {
                "seq": 0,
                "inst": "button_nav_intro",
                "down": ["button_nav_intro"],
                "normal": ["button_nav_sum"]},
            "screen_sum": {
                "seq": 1,
                "inst": "button_nav_sum",
                "down": ["button_nav_sum"],
                "normal": ["button_nav_intro"]}
            }



class TxLine(BoxLayout):
    orientation = "horizontal"

    def __init__(self, counterparty: str, rnr: str, payedsum: float, **kwargs):
        super(TxLine, self).__init__(**kwargs)
        self.size_hint = (1, None)
        self.height = 40

        self.flt_payedsum       = payedsum
        self.txt_payedsum       = str(self.flt_payedsum)
        self.txt_counterparty   = counterparty
        self.txt_id             = rnr

        self.lbl_counterparty   = Label(text=self.txt_counterparty)
        self.lbl_id             = Label(text=self.txt_id)
        self.lbl_sum            = Label(text=self.txt_payedsum)

        self.btn_del            = Button(text="-")
        self.btn_del.bind(on_release=self.delete_this_widget)
        
        self.lbl_counterparty.size_hint = (0.3, 1)
        self.lbl_id.size_hint = (0.3, 1)
        self.lbl_sum.size_hint = (0.3, 1)
        self.btn_del.size_hint = (0.1, 1)
        
        self.add_widget(self.lbl_counterparty)
        self.add_widget(self.lbl_id)
        self.add_widget(self.lbl_sum)
        self.add_widget(self.btn_del)

        self.key = (self.txt_counterparty, self.txt_id, self.flt_payedsum)

    def delete_this_widget(self, inst, **kwargs):
        """
        Removing Transaction data from 3 different locations:
        :param inst:
        :param kwargs:
        :return:
        """

        # Removing transaction line object from screen:
        self.parent.remove_widget(self.parent.tx_dict[self.key])
        # Removing transactions line representation object from parent object's registry:
        App.get_running_app().root.ids.screen_intro.ids.opareaintro.ids.txdisplay.tx_dict.__delitem__(self.key)
        # Removing transaction from Applications tx collection:
        App.get_running_app().transaction_dict.__delitem__(self.key)


class TXdisplay(StackLayout):
    tx_dict = {}

    def __init__(self, **kwargs):
        super(TXdisplay, self).__init__(**kwargs)
        self.tx_counter = 0
        # self.orientation = "vertical"

    def btnclck_tx_add(self, inst):
        App.get_running_app().setup_spending(reset=inst.reset)


class OperationAreaBox(BoxLayout):
    pass


class OpAreaIntro(OperationAreaBox):
    def __init__(self, **kwargs):
        super(OpAreaIntro, self).__init__(**kwargs)

    def btnclck_dataconfirm(self, instance):
        if instance.state == "down":
            if self.ids.txt_nameline.text and self.ids.txt_yearline.text:
                self.ids.nameline.disabled = True
                self.ids.yearline.disabled = True
                instance.text = "Locked"
                self.ids.btn_add_amend.disabled = False
                self.ids.btn_add_clean.disabled = False
                self.ids.msg_opareaintro.text = "{} - {}".format(self.ids.txt_nameline.text, self.ids.txt_yearline.text)
                with self.ids.msg_opareaintro.canvas.before:
                    Color(0.0, 0.4, 0)
                    Rectangle(pos=self.ids.msg_opareaintro.pos, size=self.ids.msg_opareaintro.size)

                App.get_running_app().actual_name = self.ids.txt_nameline.text
                App.get_running_app().actual_year = self.ids.txt_yearline.text

                self.ids.btn_calc.disabled = False
                self.ids.btn_load.disabled = False
            else:
                instance.state = "normal"
                App.get_running_app().actual_name = ""
                App.get_running_app().actual_year = 0

        elif instance.state == "normal":
            self.ids.nameline.disabled = False
            self.ids.yearline.disabled = False
            self.ids.btn_calc.disabled = True
            self.ids.btn_load.disabled = True
            instance.text = "Click to accept!"
            self.ids.btn_add_amend.disabled = True
            self.ids.btn_add_clean.disabled = True
            self.ids.msg_opareaintro.text = "Finalize basic settings!"
            self.ids.msg_opareaintro.background_color = (0, 1, 0, 1)
            with self.ids.msg_opareaintro.canvas.before:
                Color(0.4, 0.0, 0)
                Rectangle(pos=self.ids.msg_opareaintro.pos, size=self.ids.msg_opareaintro.size)

    def btnclck_calc(self):
        App.get_running_app().change_screen(screen_name="screen_sum", screen_direction="left")

    def btnclck_load(self):
        App.get_running_app().load()



class OpAreaPos(OperationAreaBox):
    def __init__(self, **kwargs):
        super(OpAreaPos, self).__init__(**kwargs)
        self.qr_path_list: list = []
        self.qr_counter: int = 0
        self.spending = Inv.Spending()
        self.update_result = {}

        self._staticargdata_ =\
            Coll.OrderedDict( {
                "payed_sum":            {
                    "prompt": " >  Enter numerical value of the PAYED SUM                 : ",
                    "restrict": None,
                    "argtype": float,
                    "data": None},
                "used_currency":        {
                    "prompt": " >  Used CURRENCY - (E)uro, (F)t or (B)tc                  : ",
                    "restrict": {"e": '€', "f": 'ft', "b": 'btc'},
                    "argtype": str,
                    "data": '€'},
                "spending_date":        {
                    "prompt": " >  SPENDING DATE of the sum (yyyymmdd)                    : ",
                    "restrict": None,
                    "argtype": int,
                    "data": None},
                "payment_method":       {
                    "prompt": " >  Payment METHOD - (C)ash, (T)ransfer, (B)lockchain or (N)/A    : ",
                    "restrict": {"c": "cash", "t": "transfer", "b": "blockchain", "n": "N/A"},
                    "argtype": str,
                    "data": None},
                "other_pier":           {
                    "prompt": " >  Who did you pay to or did you receive payment from     ? ",
                    "restrict": None,
                    "argtype": str,
                    "data": None},
                "inland_eu":            {
                    "prompt": " >  Is it (I)nland or (E)u                                 ? ",
                    "restrict": {"i": "inland", "e": "eu"},
                    "argtype": str,
                    "data": None},
                "category":             {
                    "prompt": " >  Enter ACCOUNTING CATEGORY!                             : ",
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
                    "argtype": str,
                    "data": None},
                "groups":               {
                    "prompt": " >  List of groups as reminder   . (Enter closes list)     : ",
                    "restrict": {"": "N/A", "buro": "buro", "porto": "porto", "werkzeug": "werkzeug"},
                    "argtype": list,
                    "data": None},
                "remarks":              {
                    "prompt": " >  .... any comments: ",
                    "restrict": None,
                    "argtype": str,
                    "data": None},
                "is_there_an_invoice":  {
                    "restrict": [True, False],
                    "argtype":  bool,
                    "data": True},
                "invoice_date":         {
                    "prompt": " >  INVOICE DATE. (enter '0' if it's the spending date)    : ",
                    "restrict": None,
                    "argtype": int,
                    "data": None},
                "invoice_nr":   {
                    "prompt": " >  ID of the invoice                                      : ",
                    "restrict": None,
                    "argtype": str,
                    "data": None}
            }
            )

        self.pay_date = 'xxxxxxxx'
        self.inv_date = 'xxxxxxxx'

    def reset_screen(self):
        self.ids.toggle_traced.state = "normal"
        self.ids.txt_payedsum.text = ""
        self.ids.spinn_curr.text = "EUR"
        self.ids.txt_pier.text = ""
        self.ids.spinn_meth.text = "pick method"
        self.ids.spinn_cat.text = "pick category"
        self.ids.txt_invnr.text = ""

    def on_reinit(self, reset=True):
        # self.ids.lbl_payyear.text = str(App.get_running_app().actual_year)
        # self.ids.lbl_invyear.text = str(App.get_running_app().actual_year)
        if reset:
            self.reset_screen()

        self.ids.txt_paydate.text = str(App.get_running_app().actual_year)
        self.ids.txt_invdate.text = str(App.get_running_app().actual_year)

        self.ids.spinn_cat.values = sorted(list(self._staticargdata_["category"]["restrict"].values()))
        self.ids.spinn_meth.values = sorted(list(self._staticargdata_["payment_method"]["restrict"].values()))

    def fetch_return_data(self):
        self.update_result["payed_sum"]     = round(float(self.ids.txt_payedsum.text), 2)
        self.update_result["invoice_nr"]    = self.ids.txt_invnr.text
        self.update_result["other_pier"]    = self.ids.txt_pier.text
        self.update_result["spending_date"] = int(self.ids.txt_paydate.text)  # non-int must be allowed: change elswhere
        self.update_result["invoice_date"]  = int(self.ids.txt_invdate.text)  # non int must be allowed: change elswhere
        self.update_result["used_currency"] = {"EUR": '€', "HUF": 'ft', "BTC": 'btc'}[self.ids.spinn_curr.text]
        self.update_result["payment_method"] = self.ids.spinn_meth.text
        self.update_result["category"] = self.ids.spinn_cat.text

        # self.update_result["spending_date"] = int(self.ids.lbl_payyear.text + self.ids.txt_paydate.text)
        # self.update_result["invoice_date"]  = int(self.ids.lbl_invyear.text + self.ids.txt_invdate.text)

        self.spending.update_from_dict_inclusive_source_driven(dictionary=self.update_result,
                                                               exclude_list=list())
        self.spending.update_dynamicdata()

        key = (self.spending.other_pier,
               self.spending.invoice_nr,
               self.spending.payed_sum)

        if key not in App.get_running_app().root.ids.screen_intro.ids.opareaintro.ids.txdisplay.tx_dict:
            App.get_running_app().append_actual_spending(used_key=key)
            newline = TxLine(counterparty=key[0], rnr=key[1], payedsum=key[2])
            App.get_running_app().root.ids.screen_intro.ids.opareaintro.ids.txdisplay.tx_dict[key] = newline
            App.get_running_app().root.ids.screen_intro.ids.opareaintro.ids.txdisplay.add_widget(newline)

            App.get_running_app().change_screen(screen_name="screen_intro", screen_direction="right")

    def on_togglestate_traced(self, inst):
        if inst.state == "down":
            inst.text = 'Without invoice'

            self.update_result["is_there_an_invoice"] = False
            self.ids.txt_invnr.text = "N/A"
            self.ids.txt_invdate.text = "0"

            self.ids.row_invnr.disabled = True
            self.ids.row_invdate.disabled = True

            self.update_result["is_there_an_invoice"] = False
        else:
            inst.text = 'Invoice'
            self.update_result["is_there_an_invoice"] = True
            self.ids.txt_invnr.text = "--- missing ---"
            self.ids.txt_invdate.text = "--- missing ---"

            self.ids.row_invnr.disabled = False
            self.ids.row_invdate.disabled = False

    def btnclck_datecopy(self):
        self.ids.txt_invdate.text = self.ids.txt_paydate.text

    def on_togglestate_loc(self, inst):
        if inst.state == "normal":
            inst.text = 'Inland'
            self.update_result["inland_eu"] = 'inland'
        else:
            inst.text = 'EU'
            self.update_result["inland_eu"] = 'eu'

    def on_textupdate_invid(self, inst):
        self._staticargdata_["invoice_nr"]["data"] = inst.text

    def on_textupdate_pier(self, inst):
        self._staticargdata_["other_pier"]["data"] = inst.text

    def on_buttonclick_edittext(self):
        App.get_running_app().change_screen(screen_name="screen_text",
                                            screen_direction="left")

    def on_release_confirm(self):
        self.fetch_return_data()

    def on_release_cancel(self):
        App.get_running_app().change_screen(screen_name="screen_intro", screen_direction="right")

class OpAreaSum(OperationAreaBox):
    def __init__(self, **kwargs):
        super(OpAreaSum, self).__init__(**kwargs)

    def btnclck_screen_intro(self):
        self.ids.btn_extract_summary.disabled = False
        self.ids.txt_summary.text = "N/A"
        App.get_running_app().change_screen(screen_name="screen_intro",
                                            screen_direction="right")

    def btnclck_summary(self, instance):
        self.ids.txt_summary.text = "New summary created"
        instance.disabled = True
        App.get_running_app().summarize()

    def btnclck_save(self):
        App.get_running_app().save()


class Accounting(App):
    """=== Class name: AppObj ========================================================================================
    Child of built in class: App
    This is the Parent application for a project.
    Instantiation should - contrary to what is used on the net - happen by assigning it to a variable name.
    :param window_content:
    ============================================================================================== by Sziller ==="""
    def __init__(self,
                 window_content: str,
                 app_title: str     = "DefaultTitle",
                 app_icon: str      = "./icon.png",
                 csm: float         = 1.0):
        super(Accounting, self).__init__()
        self.title                      = app_title
        self.icon                       = app_icon
        self.window_content             = window_content
        self.content_size_multiplier    = csm
        self.external_var: list         = []

        # ------------------------------------------------------------
        self.actual_name: str               = ""
        self.actual_year: int               = 0

        self.transaction_dict: dict         = {}
        self.actual_spending                = None  # spending position obj, you process at a given moment at runtime

    def get_directory_name_template(self):
        return "./{}_{}".format("Erklaerung", self.actual_year)

    def setup_spending(self, reset):
        self.actual_spending = Inv.Spending()
        self.root.ids.screen_pos.ids.opareapos.spending = self.actual_spending
        self.root.ids.screen_pos.ids.opareapos.on_reinit(reset=reset)
        self.change_screen(screen_name="screen_pos", screen_direction="left")
    
    def append_actual_spending(self):
        """=== Method name: append_actual_spending =====================================================================
        Method adds the actual Spending to the dictionary storeing
        :var self.transaction_dict: storing all Spendings used
        :var self.actual_spending: the one Spending actually processed
        :return:
        ========================================================================================== by Sziller ==="""
        self.transaction_dict[self.actual_spending.get_id_key()] = self.actual_spending

    def change_screen(self, screen_name, screen_direction="left"):
        """=== Method name: change_screen ==============================================================================
        Use this screenchanger instead of the built-in method for more customizability and to enable further
        actions before changing the screen.
        Also, if screenchanging first needs to be validated, use this method!
        ========================================================================================== by Sziller ==="""
        self.clear_msg_area()
        smng = self.root  # 'root' refers to the only one root instance in your App. Here it is the actual ROOT
        smng.current = screen_name
        smng.transition.direction = screen_direction

    def build(self):
        return self.window_content

    def on_stop(self):
        print("yepp")  # self.app_response

    def testfunction(self):
        self.display_message("ERR: testmessage")

    def transaction_list_extractor(self):
        return list(self.transaction_dict.values())

    def getfullpath(self):
        fullpath = self.get_directory_name_template()
        if os.path.isdir(fullpath):
            return fullpath
        else: return False

    def getfullfilename(self):
        fullpath = self.getfullpath()
        if fullpath:
            return fullpath + "/{}.yaml".format(self.actual_name)
        else:
            return False

    def save(self, data):
        fullpath = self.getfullpath()
        if not fullpath:
            os.makedirs(self.get_directory_name_template())
        data_to_yaml(data, filename=self.getfullfilename())
        print("Data will be saved to:    {}".format(self.getfullfilename()))

    def load(self):
        fullpath = self.getfullpath()
        loaded_data = False
        if fullpath:
            loaded_data = yaml_read_in(filename=self.getfullfilename())
        for spendingdata in loaded_data:
            processed_spending = Inv.Spending()
            processed_spending.update_from_dict_inclusive_source_driven(dictionary=spendingdata)
            key = (processed_spending.other_pier,
                   processed_spending.invoice_nr,
                   processed_spending.payed_sum)
            self.transaction_dict[key] = self.actual_spending


    def display_message(self, message):
        self.root.ids[self.root.current].ids.ribbon.ids.lbl_ribbon.text = message

    def clear_msg_area(self):
        self.display_message(message="---")

    def summarize(self):
        transaction_obj_list = self.transaction_list_extractor()

        read_in_spendings_o_dict_list = Inv.convert_obj_to_odict_list(object_list=transaction_obj_list)
        read_in_spendings_dict_list = Inv.convert_odict_to_dict_list(read_in_spendings_o_dict_list)



        data_in = ""
        data_out = ""
        data = data_in + data_out

        for c, line in enumerate(read_in_spendings_dict_list):
            print("Line: {:>3}".format(c))
            print(line)

        self.save(data=read_in_spendings_dict_list)

        testobj = Inv.Spending()
        testobj.update_from_dict_inclusive_source_driven(read_in_spendings_dict_list[0])

        print("//////////")
        print(testobj.__dict__)
        print("//////////")


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
    with open(fullfilename, "r") as file:
        answer = yaml.safe_load(file)

    file.close()
    return answer


if __name__ == "__main__":
    from kivy.lang import Builder  # to freely pick kivy files
    #
    display_settings = {0: {'fullscreen': False, 'run': Window.maximize},
                        1: {'fullscreen': False, 'size': (400, 800)},
                        2: {'fullscreen': False, 'size': (600, 400)},
                        3: {'fullscreen': False, 'size': (1000, 500)}}

    style_code = 1

    Window.fullscreen = display_settings[style_code]['fullscreen']
    if 'size' in display_settings[style_code].keys(): Window.size = display_settings[style_code]['size']
    if 'run' in display_settings[style_code].keys(): display_settings[style_code]['run']()

    try:
        content = Builder.load_file(str(sys.argv[1]))
    except IndexError:
        content = Builder.load_file("account.kv")

    application_title_in_window_head    = "Sziller's accounting app"
    application_window_icon             = "icon.png"
    content_size_multiplier             = 1

    application = Accounting(window_content=content,
                             app_title=application_title_in_window_head,
                             app_icon=application_window_icon,
                             csm=content_size_multiplier)
    # g = application.app_response  # fucking trick!!! Mutable data used to fetch data
    application.run()
    # print(g[0])
