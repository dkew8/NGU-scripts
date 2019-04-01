import sys
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtCore import QBuffer
from design.design import Ui_MainWindow
from design.options import Ui_OptionsWindow
from design.inventory import Ui_InventorySelecter
from classes.inputs import Inputs
from classes.window import Window
from distutils.util import strtobool
from PIL import Image
from PIL.ImageQt import ImageQt
import io
import json
import itopod
import questing
import inspect
import math
import time
import re
import coordinates as coords
import pytesseract
import win32gui


class NguScriptApp(QtWidgets.QMainWindow, Ui_MainWindow):
    """Main window."""

    def __init__(self, parent=None):
        """Generate UI."""
        super(NguScriptApp, self).__init__(parent)
        self.setupUi(self)  # generate the UI
        self.mutex = QtCore.QMutex()  # lock for script thread to enable pausing
        self.w = Window()
        self.i = Inputs(self.w, self.mutex)

        self.setup()

    def setup(self):
        """Add logic to UI elements."""
        self.rebirth_progress.setAlignment(QtCore.Qt.AlignCenter)
        self.task_progress.setAlignment(QtCore.Qt.AlignCenter)
        self.get_ngu_window()
        self.test_tesseract()
        self.task_progress.setValue(0)
        self.rebirth_progress.setValue(0)
        self.task_progress_animation = QtCore.QPropertyAnimation(self.task_progress, b"value")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.action_stop)
        self.run_button.clicked.connect(self.action_run)
        self.run_options.clicked.connect(self.action_options)

        try:
            with open("stats.txt", "r") as f:  # load stats from file if it exists
                data = json.loads(f.read())
                self.lifetime_itopod_kills = int(data["itopod_snipes"])
                self.lifetime_itopod_kills_data.setText(str(self.human_format(self.lifetime_itopod_kills)))
                self.lifetime_itopod_time_saved_data.setText(data["itopod_time_saved"])
        except FileNotFoundError:
            self.lifetime_itopod_kills_data.setText("0")
            self.lifetime_itopod_time_saved_data.setText("0")
            self.lifetime_itopod_kills = 0
        # self.tabWidget.setFixedSize(self.sizeHint())  # shrink window

    def closeEvent(self, event):
        """Event fired when exiting the application. This will save the current stats to file."""
        quit_msg = "Are you sure you want to exit?"
        reply = QtWidgets.QMessageBox.question(self, 'Message',
                                               quit_msg, QtWidgets.QMessageBox.Yes,
                                               QtWidgets.QMessageBox.No)

        if reply == QtWidgets.QMessageBox.Yes:
            with open("stats.txt", "w") as f:
                data = {"itopod_snipes": self.lifetime_itopod_kills,
                        "itopod_time_saved": self.lifetime_itopod_time_saved_data.text()}
                f.write(json.dumps(data))
            event.accept()
        else:
            event.ignore()
    def window_enumeration_handler(self, hwnd, top_windows):
        """Add window title and ID to array."""
        top_windows.append((hwnd, win32gui.GetWindowText(hwnd)))

    def get_ngu_window(self):
        """Get window ID for NGU IDLE."""
        window_name = "play ngu idle"
        top_windows = []
        win32gui.EnumWindows(self.window_enumeration_handler, top_windows)
        for i in top_windows:
            if window_name in i[1].lower():
                self.w.id = i[0]
        self.window_retry.disconnect()
        if self.w.id:
            self.window_retry.setText("Show Window")
            self.window_retry.clicked.connect(self.action_show_window)
            self.window_info_text.setText("Window detected!")
            self.get_top_left()
            if Window.x and Window.y:
                self.window_info_text.setStyleSheet("color: green")
                self.window_info_text.setText(f"Window detected! Game detected at: {Window.x}, {Window.y}")
                self.run_button.setEnabled(True)
                self.run_options.setEnabled(True)
        else:
            self.window_retry.clicked.connect(self.get_ngu_window)
            self.run_button.setEnabled(False)
            self.run_options.setEnabled(False)

    def test_tesseract(self):
        """Check if tesseract is installed."""
        try:
            pytesseract.image_to_string(Image.open("images/consumable.png"))
            self.get_ngu_window()
        except pytesseract.pytesseract.TesseractNotFoundError:
            self.window_info_text.setStyleSheet("color: red")
            self.window_info_text.setText("Tesseract not found")
            self.window_retry.setText("Try again")
            self.window_retry.disconnect()
            self.window_retry.clicked.connect(self.test_tesseract)
            self.run_button.setEnabled(False)

    def get_top_left(self):
        """Get coordinates for top left of game."""
        try:
            Window.x, Window.y = self.i.pixel_search(coords.TOP_LEFT_COLOR, 0, 0, 400, 600)
        except TypeError:
            self.window_info_text.setText(f"Window detected, but game not found!")
            self.window_info_text.setStyleSheet("color: red")
            self.window_retry.setText("Retry")
            self.window_retry.disconnect()
            self.window_retry.clicked.connect(self.get_ngu_window)

    def action_show_window(self):
        """Activate game window."""
        win32gui.ShowWindow(self.w.id, 5)
        win32gui.SetForegroundWindow(self.w.id)

    def action_stop(self, thread):
        """Stop script thread."""
        if self.mutex.tryLock(1000):  # only way to check if we have the lock without crashing?
            self.run_thread.terminate()
            self.run_button.setText("Run")
            self.run_button.disconnect()
            self.run_button.clicked.connect(self.action_run)
            self.stop_button.setEnabled(False)
            self.mutex.unlock()
        else:
            QtWidgets.QMessageBox.information(self, "Error", "Couldn't acquire lock of script thread.")

    def action_pause(self, thread):
        """Attempt to block script thread by acquiring lock."""
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(False)  # stopping while paused causes a deadlock
        self.run_options.setEnabled(False)  # trying to open inventory viewer causes deadlock
        self.run_button.setText("Pausing...")
        self.mutex.lock()
        self.run_button.disconnect()
        self.run_button.clicked.connect(self.action_resume)
        self.run_button.setText("Resume")
        self.run_button.setEnabled(True)

    def action_resume(self, thread):
        """Attempt to release lock to un-block script thread."""
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.run_button.setText("Pause")
        self.run_button.disconnect()
        self.mutex.unlock()
        self.run_button.setEnabled(True)
        self.run_button.clicked.connect(self.action_pause)

    def action_options(self):
        """Display option window."""
        index = self.combo_run.currentIndex()
        self.options = OptionsWindow(index, self.i)
        self.options.show()

    def human_format(self, num):
        """Convert large integer to readable format."""
        num = float('{:.3g}'.format(num))
        if num > 1e14:
            return
        magnitude = 0
        while abs(num) >= 1000:
            magnitude += 1
            num /= 1000.0
        return '{}{}'.format('{:f}'.format(num).rstrip('0').rstrip('.'), ['', 'K', 'M', 'B', 'T'][magnitude])

    def timestamp(self):
        """Update timestamp for elapsed time."""
        n = time.time() - self.start_time
        days = math.floor(n // (24 * 3600))
        n = n % (24 * 3600)

        if days > 0:
            result = f"{days} days, {time.strftime('%H:%M:%S', time.gmtime(n))}"
        else:
            result = f"{time.strftime('%H:%M:%S', time.gmtime(n))}"
        self.elapsed_data.setText(result)

    def update(self, result):
        """Update data in UI upon event."""
        for k, v in result.items():
            if k == "exp":
                self.exp_data.setText(self.human_format(v))
            elif k == "pp":
                self.pp_data.setText(self.human_format(v))
            elif k == "qp":
                self.qp_data.setText(self.human_format(v))
            elif k == "xph":
                self.exph_data.setText(self.human_format(v))
            elif k == "pph":
                self.pph_data.setText(self.human_format(v))
            elif k == "qph":
                self.qph_data.setText(self.human_format(v))
            elif k == "task_progress":
                self.task_progress_animation.setDuration(200)
                self.task_progress_animation.setStartValue(self.task_progress.value())
                self.task_progress_animation.setEndValue(v)
                print(f"start: {self.task_progress.value()}, end: {v}")
                self.task_progress_animation.start()
                # self.task_progress.setValue(math.ceil(v))
            elif k == "itopod_snipes":
                self.lifetime_itopod_kills += 1
                self.lifetime_itopod_kills_data.setText(str(self.human_format(self.lifetime_itopod_kills)))

                n = self.lifetime_itopod_kills * 0.8
                days = math.floor(n // (24 * 3600))
                n = n % (24 * 3600)
                hours = math.floor(n // 3600)
                n %= 3600
                minutes = math.floor(n // 60)
                n %= 60
                seconds = math.floor(n)

                self.lifetime_itopod_time_saved_data.setText(f"{days} days, {hours} hours, {minutes} minutes, {seconds} seconds")

            elif k == "task":
                self.current_task_text.setText(v)

    def action_run(self):
        """Start the selected script."""
        run = self.combo_run.currentIndex()
        self.start_time = time.time()
        self.timer = QtCore.QTimer()
        self.timer.setInterval(1010)
        self.timer.timeout.connect(self.timestamp)
        self.timer.start()
        if run == 0:
            self.run_thread = ScriptThread(0, self.w, self.mutex)
            self.run_thread.signal.connect(self.update)
            self.run_button.setText("Pause")
            self.run_button.disconnect()
            self.run_button.clicked.connect(self.action_pause)
            self.w_exp.show()
            self.w_pp.hide()
            self.w_pph.hide()
            self.w_exph.show()
            self.w_qp.show()
            self.w_qph.show()
            self.current_rb_text.hide()
            self.rebirth_progress.hide()
            self.setFixedSize(300, 320)
            self.current_task_text.show()
            self.task_progress.show()
            self.task_progress.setValue(0)
            self.stop_button.setEnabled(True)
            self.run_thread.start()

        elif run == 1:
            self.run_thread = ScriptThread(1, self.w, self.mutex)
            self.run_thread.signal.connect(self.update)
            self.run_button.setText("Pause")
            self.run_button.disconnect()
            self.run_button.clicked.connect(self.action_pause)
            self.w_exp.show()
            self.w_pp.show()
            self.w_pph.show()
            self.w_exph.show()
            self.w_qp.hide()
            self.w_qph.hide()
            self.current_rb_text.hide()
            self.rebirth_progress.hide()
            self.setFixedSize(300, 320)
            self.current_task_text.show()
            self.task_progress.show()
            self.task_progress.setValue(0)
            self.stop_button.setEnabled(True)
            self.run_thread.start()


class OptionsWindow(QtWidgets.QMainWindow, Ui_OptionsWindow):
    """Option window."""

    def __init__(self, index, inputs, parent=None):
        """Setup UI."""
        super(OptionsWindow, self).__init__(parent)
        self.setupUi(self)
        self.index = index
        self.i = inputs
        self.settings = QtCore.QSettings("Kujan", "NGU-Scripts")
        self.button_ok.clicked.connect(self.action_ok)
        self.radio_group_gear = QtWidgets.QButtonGroup(self)
        self.radio_group_gear.addButton(self.radio_equipment)
        self.radio_group_gear.addButton(self.radio_cube)
        self.check_gear.stateChanged.connect(self.state_changed_gear)
        self.check_force.stateChanged.connect(self.state_changed_force_zone)
        self.gui_load()

    def state_changed_gear(self, int):
        """Update UI."""
        if self.check_gear.isChecked():
            self.radio_equipment.setEnabled(True)
            self.radio_cube.setEnabled(True)
        else:
            self.radio_equipment.setEnabled(False)
            self.radio_equipment.setChecked(False)
            self.radio_cube.setEnabled(False)
            self.radio_cube.setChecked(False)

    def state_changed_boost_inventory(self, int):
        """Update UI."""
        if self.check_boost_inventory.isChecked():
            self.inventory_selecter = InventorySelecter("arr_boost_inventory", self.i)
            self.inventory_selecter.show()

    def state_changed_merge_inventory(self, int):
        """Update UI."""
        if self.check_merge_inventory.isChecked():
            self.inventory_selecter = InventorySelecter("arr_merge_inventory", self.i)
            self.inventory_selecter.show()

    def state_changed_force_zone(self, int):
        """Update UI."""
        if self.check_force.isChecked():
            self.combo_force.setEnabled(True)
        else:
            self.combo_force.setEnabled(False)

    def state_changed_subcontract(self, int):
        """Show warning."""
        if self.check_subcontract.isChecked():
            msg = QtWidgets.QMessageBox(self)
            msg.setIcon(QtWidgets.QMessageBox.Warning)
            msg.setText("Are you sure you wish to subcontract your quests?")
            msg.setWindowTitle("Subcontract warning")
            msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
            msg.exec()
    def gui_load(self):
        """Load settings from registry."""
        if self.index == 0:
            self.label_duration.setText("Duration in minutes to run:")
            self.check_force.show()
            self.check_major.show()
            self.check_subcontract.show()
            self.combo_force.show()
            self.setFixedSize(300, 300)

        elif self.index == 1:
            self.label_duration.setText("Duration in seconds to run:")
            self.check_force.hide()
            self.check_major.hide()
            self.check_subcontract.hide()
            self.combo_force.hide()
            self.setFixedSize(300, 200)
        for name, obj in inspect.getmembers(self):
            if isinstance(obj, QtWidgets.QComboBox):
                index = obj.currentIndex()
                text = obj.itemText(index)
                name = obj.objectName()
                value = (self.settings.value(name))

                if value == "":
                    continue

                index = obj.findText(value)

                if index == -1:
                    obj.insertItems(0, [value])
                    index = obj.findText(value)
                    obj.setCurrentIndex(index)
                else:
                    obj.setCurrentIndex(index)

            if isinstance(obj, QtWidgets.QLineEdit):
                name = obj.objectName()
                value = (self.settings.value(name))
                obj.setText(value)

            if isinstance(obj, QtWidgets.QCheckBox):
                name = obj.objectName()
                value = self.settings.value(name)
                if value is not None:
                    obj.setChecked(strtobool(value))
            if isinstance(obj, QtWidgets.QRadioButton):
                name = obj.objectName()
                value = self.settings.value(name)
                if value is not None:
                    obj.setChecked(strtobool(value))

        self.check_boost_inventory.stateChanged.connect(self.state_changed_boost_inventory)
        self.check_merge_inventory.stateChanged.connect(self.state_changed_merge_inventory)
        self.check_subcontract.stateChanged.connect(self.state_changed_subcontract)

    def action_ok(self):
        """Save settings and close window."""
        for name, obj in inspect.getmembers(self):
            if isinstance(obj, QtWidgets.QComboBox):
                name = obj.objectName()
                index = obj.currentIndex()
                text = obj.itemText(index)
                self.settings.setValue(name, text)
                self.settings.setValue(name + "_index", index)

            if isinstance(obj, QtWidgets.QLineEdit):
                name = obj.objectName()
                value = obj.text()
                self.settings.setValue(name, value)

            if isinstance(obj, QtWidgets.QCheckBox):
                name = obj.objectName()
                state = obj.isChecked()
                self.settings.setValue(name, state)

            if isinstance(obj, QtWidgets.QRadioButton):
                name = obj.objectName()
                value = obj.isChecked()
                self.settings.setValue(name, value)
        self.close()


class InventorySelecter(QtWidgets.QMainWindow, Ui_InventorySelecter):
    """Option window."""

    def __init__(self, mode, inputs, parent=None):
        """Setup UI."""
        super(InventorySelecter, self).__init__(parent)
        self.setupUi(self)
        self.mode = mode
        self.i = inputs
        self.settings = QtCore.QSettings("Kujan", "NGU-Scripts")
        self.slots = []
        self.button_ok.clicked.connect(self.action_ok)
        self.generate_inventory()
        self.setFixedSize(761, 350)

    def action_ok(self):
        """Save settings and close window."""
        for name, obj in inspect.getmembers(self):
            if isinstance(obj, QtWidgets.QPushButton):
                if obj.toggled:
                    name = obj.objectName()
                    if name == "button_ok":
                        continue
                    print(name)
                    self.slots.append(re.sub(r"[^0-9]", "", name))
        print(self.slots)
        self.settings.setValue(self.mode, self.slots)
        self.close()

    def pil2pixmap(self, im):
        """Convert PIL Image object to QPixmap"""
        with io.BytesIO() as output:
            im.save(output, format="png")
            output.seek(0)
            data = output.read()
            qim = QtGui.QImage.fromData(data)
            pixmap = QtGui.QPixmap.fromImage(qim)
        return pixmap

    def action_button_clicked(self):
        button = getattr(self, self.sender().objectName())

        if not button.toggled:
            button.toggled = True
            print("toggling on")
            button.setStyleSheet("border:3px solid rgb(0, 0, 0)")
        else:
            button.toggled = False
            print("toggling off")
            button.setStyleSheet("")

    def generate_inventory(self, depth=0):
        """Get image from inventory and create clickable grid."""
        if depth > 4:  # infinite recursion guard
            msg = QtWidgets.QMessageBox(self)
            msg.setIcon(QtWidgets.QMessageBox.Critical)
            msg.setText("Couldn't find inventory, is the game running?")
            msg.setWindowTitle("Inventory error")
            msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
            msg.exec()

        self.i.click(*coords.MENU_ITEMS["inventory"])
        if self.i.check_pixel_color(*coords.INVENTORY_SANITY):
            print("in inventory")
        else:
            self.generate_inventory(depth=depth + 1)
        self.i.click(*coords.INVENTORY_PAGE_1)
        bmp = self.i.get_bitmap()
        bmp = bmp.crop((self.i.window.x + 8, self.i.window.y + 8, self.i.window.x + 968, self.i.window.y + 608))
        bmp = bmp.crop((coords.INVENTORY_AREA.x1, coords.INVENTORY_AREA.y1, coords.INVENTORY_AREA.x2, coords.INVENTORY_AREA.y2))
        button_count = 1
        for y in range(5):
            for x in range(12):
                x1 = x * coords.INVENTORY_SLOT_WIDTH
                y1 = y * coords.INVENTORY_SLOT_HEIGHT
                x2 = x1 + coords.INVENTORY_SLOT_WIDTH
                y2 = y1 + coords.INVENTORY_SLOT_WIDTH
                slot = bmp.crop((x1, y1, x2, y2))
                button = getattr(self, f"pushButton_{button_count}")
                pixmap = self.pil2pixmap(slot)
                icon = QtGui.QIcon(pixmap)
                button.setIcon(icon)
                button.setIconSize(pixmap.rect().size())
                button.toggled = False
                button.clicked.connect(self.action_button_clicked)
                button_count += 1

        toggles = self.settings.value(self.mode)
        if toggles is not None:
            for toggle in toggles:
                button = getattr(self, "pushButton_" + toggle)
                button.toggled = True
                button.setStyleSheet("border:3px solid rgb(0, 0, 0)")

class ScriptThread(QtCore.QThread):
    """Thread class for script."""

    signal = QtCore.pyqtSignal("PyQt_PyObject")

    def __init__(self, run, w, mutex):
        """Init thread variables."""
        QtCore.QThread.__init__(self)
        self.run = run
        self.w = w
        self.mutex = mutex

    def run(self):
        """Check which script to run."""
        if self.run == 0:
            questing.run(self.w, self.mutex, self.signal)
        if self.run == 1:
            itopod.run(self.w, self.mutex, self.signal)


def run():
    """Start GUI thread."""
    app = QtWidgets.QApplication(sys.argv)
    GUI = NguScriptApp()
    GUI.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    run()

"""
Ideas

Progressbars tracking current long running task (sniping, questing)
Progressbar tracking run progression (if applicable)
Tools for annoying actions while playing manually (cap all diggers)
Quickstart for infinite questing/itopod sniping
Track minor/major quests done
Track current function (via object?)
"""