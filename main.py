# ///////////////////////////////////////////////////////////////
#
# BY: WANDERSON M.PIMENTA
# PROJECT MADE WITH: Qt Designer and PySide6
# V: 1.0.0
#
# This project can be used freely for all uses, as long as they maintain the
# respective credits only in the Python scripts, any information in the visual
# interface (GUI) can be modified without any implication.
#
# There are limitations on Qt licenses if you want to use your products
# commercially, I recommend reading them on the official website:
# https://doc.qt.io/qtforpython/licenses.html
#
# ///////////////////////////////////////////////////////////////

import sys
import os
import platform
from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import QGraphicsOpacityEffect
from PySide6.QtGui import QFont, QFontDatabase
import signal
from Core.agent import TarsAgent
from Core.tts import shutdown, register_speak_callback
import time

# IMPORT / GUI AND MODULES AND WIDGETS
# ///////////////////////////////////////////////////////////////
from modules import *
from modules import resources_rc  # Import resources explicitly
from widgets import *
os.environ["QT_FONT_DPI"] = "96" # FIX Problem for High DPI and Scale above 100%

# SET AS GLOBAL WIDGETS
# ///////////////////////////////////////////////////////////////
widgets = None

# FSM Worker
# ///////////////////////////////////////////////////////////////
class FSMWorker(QtCore.QObject):
    state_changed = QtCore.Signal(str)
    current_state = None

    def __init__(self, agent: TarsAgent):
        super().__init__()
        self.agent = agent
        # Performance monitoring
        self.performance_metrics = {}
        self.loop_count = 0
        self.last_performance_report = time.perf_counter()

    def start_performance_timer(self, action_name):
        """Start timing for a specific action"""
        return time.perf_counter()

    def stop_performance_timer(self, action_name, start_time):
        """Stop timing and record the result"""
        elapsed = time.perf_counter() - start_time
        if action_name not in self.performance_metrics:
            self.performance_metrics[action_name] = []
        self.performance_metrics[action_name].append(elapsed)
        return elapsed

    def print_performance_report(self):
        """Print performance report every 10 seconds"""
        print(f"\n=== FSM Performance Report (Loops: {self.loop_count}) ===")
        for action, times in self.performance_metrics.items():
            if times:
                avg_time = sum(times) / len(times)
                print(f"{action}: avg={avg_time*1000:.2f}ms, count={len(times)}, min={min(times)*1000:.2f}ms, max={max(times)*1000:.2f}ms")
        
        # Reset counters
        self.performance_metrics.clear()
        self.loop_count = 0

    @QtCore.Slot()
    def run(self):
        fsm = self.agent.fsm
        loop_start_time = time.perf_counter()
        
        while not self.agent.is_interrupted:
            # Performance monitoring
            self.loop_count += 1
            current_time = time.perf_counter()
            
            # Print performance report every 10 seconds
            if current_time - self.last_performance_report >= 10.0:
                self.print_performance_report()
                self.last_performance_report = current_time

            # Check transitions with performance timing
            transition_start = self.start_performance_timer("transition_check")
            transition_found = False
            
            for t in fsm.transitions:
                if t.from_state == fsm.current_state:
                    # Time the condition check
                    condition_start = self.start_performance_timer("condition_check")
                    condition_result = t.condition()
                    condition_time = self.stop_performance_timer("condition_check", condition_start)
                    
                    # Log slow conditions
                    if condition_time > 0.1:  # 100ms threshold
                        print(f"WARNING: Slow condition check for {t.from_state.name} -> {t.to_state.name}: {condition_time*1000:.2f}ms")
                    
                    if condition_result:
                        # State transition
                        transition_time = self.stop_performance_timer("transition_check", transition_start)
                        print(f"State transition: {fsm.current_state.name} -> {t.to_state.name} (check took {transition_time*1000:.2f}ms)")
                        
                        fsm.current_state = t.to_state
                        self.state_changed.emit(fsm.current_state.name)
                        self.current_state = fsm.current_state
                        
                        # wait before action
                        delay = self.get_delay_before_action(fsm.current_state) 
                        QtCore.QThread.msleep(int((delay) * 1000))
                        
                        if t.action:
                            action_start = self.start_performance_timer("action_execution")
                            t.action()
                            action_time = self.stop_performance_timer("action_execution", action_start)
                            print(f"Action execution took: {action_time*1000:.2f}ms")
                        
                        # wait after action
                        delay = self.get_delay_after_action(fsm.current_state)
                        QtCore.QThread.msleep(int((delay + 1 ) * 1000)) # + 1 delay for UI
                        
                        transition_found = True
                        break
            
            if not transition_found:
                self.stop_performance_timer("transition_check", transition_start)
            
            # CRITICAL FIX: Add a small sleep to prevent tight loop
            # This allows other threads (like network updates) to run
            QtCore.QThread.msleep(50)  # 50ms sleep = 20 checks per second instead of thousands
            
            # Alternative: Use processEvents to allow other operations
            # QtCore.QCoreApplication.processEvents()
            
    def get_delay_before_action(self, state):
        delay = getattr(state, "delay_before_action", 0)
        if delay is None:
            delay = 0
        elif isinstance(delay, str):
            try:
                delay = float(delay)
            except ValueError:
                    delay = 0
        if delay and delay > 0:
            print(f"waiting for {delay} seconds before executing action for state {state.name}")
        return delay
    
    def get_delay_after_action(self, state):
        delay = getattr(state, "delay_after_action", 0)
        if delay is None:
            delay = 0
        elif isinstance(delay, str):
            try:
                delay = float(delay)
            except ValueError:
                    delay = 0
        if delay and delay > 0:
            print(f"waiting for {delay} seconds after executing action for state {state.name}")
        return delay
            
# Agent Thread
# ///////////////////////////////////////////////////////////////
class AgentThread(QtCore.QThread):
    def __init__(self, agent):
        super().__init__()
        self.agent = agent

    def run(self):
        self.agent.start()


class MainWindow(QMainWindow):
    tts_speak_signal = QtCore.Signal(str)

    def __init__(self):
        QMainWindow.__init__(self)

        # SET AS GLOBAL WIDGETS
        # ///////////////////////////////////////////////////////////////
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        
        self.agent = TarsAgent()
        signal.signal(signal.SIGINT, self.agent.signal_handler)
        self.ui.tars_status_label.setText(f"{self.agent.agent_name} Connected.")
        
        # Start the agent in a separate thread
        self.agent_thread = AgentThread(self.agent)
        self.agent_thread.start()
        
        
        # FSM Worker in a thread
        self.fsm_thread = QtCore.QThread()
        self.fsm_worker = FSMWorker(self.agent)
        self.fsm_worker.moveToThread(self.fsm_thread)
        self.fsm_worker.state_changed.connect(self.update_state)
        self.fsm_thread.started.connect(self.fsm_worker.run)
        self.fsm_thread.start()

        self.current_state = None
        self.previous_state = None
        self.next_state = None

        self.tts_speak_signal.connect(self.on_tts_speak)
        register_speak_callback(self.tts_callback)
        self.ui.current_task_container_3.setObjectName("currentTaskContainer")

        #countdown timer for current task
        self.current_countdown_timer = QtCore.QTimer(self)
        self.current_countdown_timer.setInterval(1000)
        self.current_countdown_timer.timeout.connect(self.update_current_countdown)
        self.current_countdown_value = 0
        

        #countdown timer for next task
        self.next_countdown_timer = QtCore.QTimer(self)
        self.next_countdown_timer.setInterval(1000)
        self.next_countdown_timer.timeout.connect(self.update_next_countdown)
        self.next_countdown_value = 0

        global widgets
        
        widgets = self.ui

        # USE CUSTOM TITLE BAR | USE AS "False" FOR MAC OR LINUX
        # ///////////////////////////////////////////////////////////////
        #Settings.ENABLE_CUSTOM_TITLE_BAR = False
        if platform.system() == "Darwin" or platform.system() == "Linux":
            Settings.ENABLE_CUSTOM_TITLE_BAR = True
        if platform.system() == "Windows":
            Settings.ENABLE_CUSTOM_TITLE_BAR = True

        # APP NAME
        # ///////////////////////////////////////////////////////////////
        title = "TARS Interface"
        description = "TARS Interface - Python GUI Framework"
        # APPLY TEXTS
        self.setWindowTitle(title)
        widgets.titleRightInfo.setText(description)

        # TOGGLE MENU
        # ///////////////////////////////////////////////////////////////
        widgets.toggleButton.clicked.connect(lambda: UIFunctions.toggleMenu(self, True))

        # SET UI DEFINITIONS
        # ///////////////////////////////////////////////////////////////
        UIFunctions.uiDefinitions(self)

        # QTableWidget PARAMETERS
        # ///////////////////////////////////////////////////////////////
        widgets.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # BUTTONS CLICK
        # ///////////////////////////////////////////////////////////////
        widgets.task_done_button.clicked.connect(self.task_done_clicked)
        widgets.int_panel_right_button.clicked.connect(self.task_done_clicked)
        widgets.cancel_task_button_2.clicked.connect(self.task_cancel_clicked)
        widgets.int_panel_left_button.clicked.connect(self.task_cancel_clicked)
        # LEFT MENUS
        widgets.btn_home.clicked.connect(self.buttonClick)
        widgets.btn_briefing.clicked.connect(self.buttonClick)

        # EXTRA LEFT BOX
        def openCloseLeftBox():
            UIFunctions.toggleLeftBox(self, True)
        widgets.toggleLeftBox.clicked.connect(openCloseLeftBox)
        widgets.extraCloseColumnBtn.clicked.connect(openCloseLeftBox)

        # EXTRA RIGHT BOX
        def openCloseRightBox():
            UIFunctions.toggleRightBox(self, True)
        widgets.settingsTopBtn.clicked.connect(openCloseRightBox)

        # SHOW APP
        # ///////////////////////////////////////////////////////////////
        self.show()

        # SET CUSTOM THEME
        # ///////////////////////////////////////////////////////////////
        useCustomTheme = False
        themeFile = "themes/py_dracula_light.qss"

        # SET THEME AND HACKS
        if useCustomTheme:
            # LOAD AND APPLY STYLE
            UIFunctions.theme(self, themeFile, True)

            # SET HACKS
            AppFunctions.setThemeHack(self)

        # SET HOME PAGE AND SELECT MENU
        # ///////////////////////////////////////////////////////////////
        widgets.stackedWidget.setCurrentWidget(widgets.home)
        widgets.btn_home.setStyleSheet(UIFunctions.selectMenu(widgets.btn_home.styleSheet()))
        widgets = self.ui

    def hide_label(self, label):
        opacity_effect = label.graphicsEffect()
        if not isinstance(opacity_effect, QGraphicsOpacityEffect):
            opacity_effect = QGraphicsOpacityEffect(label)
            label.setGraphicsEffect(opacity_effect)
        opacity_effect.setOpacity(0.0)
    
    def show_label(self, label):
        opacity_effect = label.graphicsEffect()
        if not isinstance(opacity_effect, QGraphicsOpacityEffect):
            opacity_effect = QGraphicsOpacityEffect(label)
            label.setGraphicsEffect(opacity_effect)
        opacity_effect.setOpacity(0.99)
        label.show()
    
    def update_current_countdown(self):
        if self.current_countdown_value > 0:
            self.ui.c_t_s_value_2.setText(str(self.current_countdown_value))
            self.current_countdown_value -= 1
        else:
            self.ui.c_t_s_value_2.setText("0")
            self.current_countdown_timer.stop()

    def update_next_countdown(self):
        if self.next_countdown_value > 0:
            self.ui.n_t_s_value_2.setText(str(self.next_countdown_value))
            self.next_countdown_value -= 1
        else:
            self.ui.n_t_s_value_2.setText("0")
            self.next_countdown_timer.stop()

    def tts_callback(self, text):
        self.tts_speak_signal.emit(text)

    def start_glow_effect(self, widget, color):
        # Flicker parameters: border width and color alpha
        if color == "red":
            self._glow_steps = [
                (2, "#ff3333"), (4, "#ff3333"), (6, "#ff3333"), (8, "#ff3333"),
                (6, "#ff3333"), (4, "#ff3333"), (2, "#ff3333"), (2, "#ff3333"), (4, "#ff3333"), (6, "#ff3333"), (8, "#ff3333"),
                (6, "#ff3333"), (4, "#ff3333"), (2, "#ff3333")
            ]       
        elif color == "blue":
            self._glow_steps = [
                (2, "#3399ff"), (4, "#3399ff"), (6, "#3399ff"), (8, "#3399ff"),
                (6, "#3399ff"), (4, "#3399ff"), (2, "#3399ff"), (2, "#3399ff"), (4, "#3399ff"), (6, "#3399ff"), (8, "#3399ff"),
                (6, "#3399ff"), (4, "#3399ff"), (2, "#3399ff")
            ]
        elif color == "green":
            self._glow_steps = [
                (2, "#00ff00"), (4, "#00ff00"), (6, "#00ff00"), (8, "#00ff00"),
                (6, "#00ff00"), (4, "#00ff00"), (2, "#00ff00"), (2, "#00ff00"), (4, "#00ff00"), (6, "#00ff00"), (8, "#00ff00"),
                (6, "#00ff00"), (4, "#00ff00"), (2, "#00ff00")
            ]
        self._glow_index = 0
        self._glow_timer = getattr(self, "_glow_timer", None)
        if self._glow_timer is None:
            self._glow_timer = QtCore.QTimer(self)
            self._glow_timer.timeout.connect(lambda: self._glow_tick(widget))
            self._glow_timer.setSingleShot(False)
        self._glow_timer.start(30)  # Flicker speed

    def _glow_tick(self, widget):
        width, color = self._glow_steps[self._glow_index]
        widget.setStyleSheet(f"""
            #currentTaskContainer {{
            border: {width}px solid {color};
            border-radius: 8px;
            background-color: rgba(19, 20, 23, 255);
            }}
        """)
        self._glow_index += 1
        if self._glow_index >= len(self._glow_steps):
            # Stabilize to a steady glow after flicker
            self._glow_timer.stop()
            widget.setStyleSheet(f"""
                #currentTaskContainer {{
                border: 4px solid {color};
                border-radius: 8px;
                background-color: rgba(19, 20, 23, 255)
                }}
            """)
        else:
            self._glow_timer.start(60)
    
    def remove_glow(self, widget):
        widget.setStyleSheet(f"""
                #currentTaskContainer {{
                    border: 2px solid rgba(19, 20, 23, 255);
                    border-radius: 10px;
                    background-color: rgba(19, 20, 23, 255);
                }}
                """)

    @QtCore.Slot(str)
    def on_tts_speak(self, text):
        self.ui.tars_action_icon.show()
        self.ui.tars_output_speech_label.show()
        self.ui.tars_output_speech_label.setText(f"\"{text}\"")


    @QtCore.Slot(str)
    def update_state(self, state_name):
        self.current_state = state_name
        fsm = self.agent.fsm
        self.next_state = None
        previous_task = None
        previous_procedure_text = None
        

        for t in fsm.transitions:
            if t.from_state.name == state_name:
                self.next_state = t.to_state.name
                break
        
        if self.previous_state is not None:
            previous_task = next((task for task in self.agent.tasks if task.get("task_name", "") == self.previous_state),None)
        current_task = next((task for task in self.agent.tasks if task.get("task_name", "") == self.current_state),None)
        next_task = next((task for task in self.agent.tasks if task.get("task_name", "") == self.next_state),None)
        previous_state_text = self.previous_state.replace("_", " ").upper() if previous_task is not None else ""
        current_state_text = self.current_state.replace("_", " ").upper() if current_task is not None else ""
        next_state_text = self.next_state.replace("_", " ").upper() if next_task is not None else ""
        
        if previous_task is not None:
            previous_procedure_text = previous_task["procedure_name"].replace("_", " ").upper()
        current_procedure_text = current_task["procedure_name"].replace("_", " ").upper() if current_task is not None else ""
        next_procedure_text = next_task["procedure_name"].replace("_", " ").upper() if next_task is not None else ""
        
        self.ui.p_g_2.setText(f"{previous_procedure_text if previous_procedure_text else ''}")
        self.ui.p_t_2.setText(f"{previous_state_text if self.previous_state else ''}")
        self.ui.c_g_2.setText(f"{current_procedure_text if current_procedure_text else ''}")
        self.ui.c_t_2.setText(f"{current_state_text if self.current_state else ''}")
        self.ui.n_g_label_2.setText(f"{next_procedure_text if next_procedure_text else ''}")
        self.ui.n_t_label_2.setText(f"{next_state_text if self.next_state else ''}")
        self.ui.alert_label_2.setText(f"Current procedure : {current_procedure_text}")
        

        
        
        if previous_task is not None:
            if previous_task["autonomy_role"] != "performer":
                self.hide_label(self.ui.p_t_prog_widget_2)
            else:
                self.show_label(self.ui.p_t_prog_widget_2)
        else:
            self.ui.p_t_prog_widget_2.hide()
        
        self.remove_glow(self.ui.current_task_container_3)

        if current_task["autonomy_role"] != "performer":
            self.hide_label(self.ui.c_t_prog_widget_2)
            self.remove_glow(self.ui.current_task_container_3)
            self.ui.cancel_task_button_2.hide()
            self.ui.task_done_button.show()
            self.ui.task_done_button.setStyleSheet(
                """
                border: 2px solid #3399ff;
                border-radius: 5px;
                background-color: rgba(0, 168, 120, 255);
                font: 600 16pt "JetBrains Mono";
                """)
        else:
            self.show_label(self.ui.c_t_prog_widget_2)
            self.start_glow_effect(self.ui.current_task_container_3, "blue")
            self.ui.task_done_button.hide()
            self.ui.cancel_task_button_2.show()            
            self.ui.task_done_button.setStyleSheet(
                """
                border: 2px solid #3399ff;
                border-radius: 5px;
                background-color: rgba(208, 04, 04, 255);
                font: 600 16pt "JetBrains Mono";
                """)

        if next_task is not None:
            if next_task["autonomy_role"] != "performer":
                self.hide_label(self.ui.n_t_prog_widget_2)
            else:
                self.show_label(self.ui.n_t_prog_widget_2)
        elif next_task is None:
            self.ui.n_t_prog_widget_2.hide()

        if current_task["interaction"] is not None:
            self.ui.int_panel_right_button.hide()
            self.ui.int_panel_left_button.hide()
            self.ui.interaction_panel_text.setText("There is no interaction for the current task...")
            match current_task["interaction"]:
                case "display_winds_and_ack":
                    self.ui.interaction_panel_text.setText("Winds: \nWind calm\nWind 026° at 3 knots")
                    if not self.ui.int_panel_right_button.isVisible() : self.show_button(self.ui.int_panel_right_button, "green")
                    self.ui.int_panel_right_button.setText("Acknowledge")
                case "display_cas":
                    self.ui.interaction_panel_text.setText("CAS: CLEAR")
                case "display_fadec":
                    self.ui.interaction_panel_text.setText("Clear")
                case "display_eng_spool_evenly":
                    self.ui.interaction_panel_text.setText("Clear")
                case "display_n1_matches_command_bug":
                    self.ui.interaction_panel_text.setText("Clear")
                case "display_trim_rudder":
                    self.ui.interaction_panel_text.setText("Current trim : 0%")
                case "display_alarm":
                    self.ui.interaction_panel_text.setText("Alarm: Engine Fire")
                case "display_l/g":
                    self.ui.interaction_panel_text.setText("Landing Gear: up")
                case "display_airspeed":
                    self.ui.interaction_panel_text.setText("Airspeed: V2")
                case "display_set_speed":
                    self.ui.interaction_panel_text.setText("Set Speed mode: FLC heading mode")
                case "display_ATC_msg_and_buttons_mayday":
                    self.ui.interaction_panel_text.setText("ATC Message: Mayday, Mayday, Mayday, Montreal Tower, from Papa Oscar Lima Yankee, engine fire after takeoff due to bird strike")
                    if not self.ui.int_panel_right_button.isVisible(): self.show_button(self.ui.int_panel_right_button, "green")
                    self.ui.int_panel_left_button.hide()
                    self.ui.int_panel_right_button.setText("Allow TARS to send Mayday message to ATC")
                case "display_engage_autopilot":
                    self.ui.interaction_panel_text.setText("Engage Autopilot: ")
                    if not self.ui.int_panel_right_button.isVisible() : self.show_button(self.ui.int_panel_right_button, "green")
                    if not self.ui.int_panel_left_button.isVisible() : self.show_button(self.ui.int_panel_left_button, "red")
                    self.ui.int_panel_right_button.setText("Engage")
                    self.ui.int_panel_left_button.setText("CANCEL")
                case "display_check_v2_plus_12":
                    self.ui.interaction_panel_text.setText("")
                case "display_start_chrono":
                    self.ui.interaction_panel_text.setText("Start chrono")
                case "display_chrono_15_s":
                    self.ui.interaction_panel_text.setText("Check the emergency fire light in 15 s")
                case "display_chrono_30_s":
                    self.ui.interaction_panel_text.setText("Check the emergency fire light in 30 s")
                case "display_checklist_emer_eng_fire_continue":
                    self.ui.interaction_panel_text.setText("Emergency Fire Checklist: ")
                    if not self.ui.int_panel_right_button.isVisible(): self.show_button(self.ui.int_panel_right_button, "green")
                    self.ui.int_panel_right_button.setText("Continue")
                case "display_allocate_radio":
                    self.ui.interaction_panel_text.setText("Allocate radio : ")
                    if not self.ui.int_panel_right_button.isVisible() : self.show_button(self.ui.int_panel_right_button, "green")
                    if not self.ui.int_panel_left_button.isVisible() : self.show_button(self.ui.int_panel_left_button, "red")
                    self.ui.int_panel_right_button.setText("TARS does the radio")
                    self.ui.int_panel_left_button.setText("Captain does the radio")
                case "display_checklist_emer_eng_fire":
                    self.ui.interaction_panel_text.setText("Emergency Fire Checklist: ")
                case "display_imm_act_check":
                    self.ui.interaction_panel_text.setText("Immediate action item : Throttle affected engine IDLE\nIlluminated ENGINE FIRE Switch LIFT COVER AND PUSH")
                case "display_ATC_msg_and_buttons_panpan":
                    self.ui.interaction_panel_text.setText("ATC Message: PanpanPan-Pan, Pan-Pan, Pan-Pan, Montreal Tower, from Papa Oscar Lima Yankee, request vectors to return for landing with one engine.")
                    if not self.ui.int_panel_right_button.isVisible(): self.show_button(self.ui.int_panel_right_button, "green")
                    self.ui.int_panel_left_button.hide()
                    self.ui.int_panel_right_button.setText("Allow TARS to send Panpan message to ATC")
                case "display_set_heading":
                    self.ui.interaction_panel_text.setText("Set heading : ")
                case "display_set_flc":
                    self.ui.interaction_panel_text.setText("Set FLC : ")
                case "display_checklist_aft_takeoff_continue":
                    self.ui.interaction_panel_text.setText("After takeoff Checklist: ")
                    if not self.ui.int_panel_right_button.isVisible(): self.show_button(self.ui.int_panel_right_button, "green")
                    self.ui.int_panel_right_button.setText("Continue")
                case "display_checklist_aft_takeoff":
                    self.ui.interaction_panel_text.setText("After takeoff Checklist: ")
                case "display_yaw_damper_prop":
                    self.ui.interaction_panel_text.setText("Yaw damper : TARS suggest ON")
                    if not self.ui.int_panel_right_button.isVisible() : self.show_button(self.ui.int_panel_right_button, "green")
                    if not self.ui.int_panel_left_button.isVisible() : self.show_button(self.ui.int_panel_left_button, "red")
                    self.ui.int_panel_right_button.setText("Accept")
                    self.ui.int_panel_left_button.setText("Refuse")
                case "display_deice_prop":
                    self.ui.interaction_panel_text.setText("De-ice : TARS suggest OFF")
                    if not self.ui.int_panel_right_button.isVisible() : self.show_button(self.ui.int_panel_right_button, "green")
                    if not self.ui.int_panel_left_button.isVisible() : self.show_button(self.ui.int_panel_left_button, "red")
                    self.ui.int_panel_right_button.setText("Accept")
                    self.ui.int_panel_left_button.setText("Refuse")
                case "display_pax_safety_prop":
                    self.ui.interaction_panel_text.setText("Pax safety: TARS suggest ON")
                    if not self.ui.int_panel_right_button.isVisible() : self.show_button(self.ui.int_panel_right_button, "green")
                    if not self.ui.int_panel_left_button.isVisible() : self.show_button(self.ui.int_panel_left_button, "red")
                    self.ui.int_panel_right_button.setText("Accept")
                    self.ui.int_panel_left_button.setText("Refuse")
                case "display_alti_set_std":
                    self.ui.interaction_panel_text.setText("Setting altimeter to STD")
                case "display_checklist_eng_fail_proc_continue":
                    self.ui.interaction_panel_text.setText("Engine Failure Procedure")
                    if not self.ui.int_panel_right_button.isVisible(): self.show_button(self.ui.int_panel_right_button, "green")
                    self.ui.int_panel_right_button.setText("Continue")
                case "display_checklist_eng_fail_proc":
                    self.ui.interaction_panel_text.setText("Engine Failure Procedure")
                case "display_caution_text":
                    self.ui.interaction_panel_text.setText("Caution text \nIf possible, the engines should remain at idle for a minimum of two minutes prior to shutdown to allow the engine inter-turbine temperature to stabilize and avoid turbine blade rub.\nIf the engine windmills for more than 15 minutes without a positive indication of oil pressure, a notation is required in the engine logbook and the engine must be inspected in accordance with the Pratt & Whitney engine maintenance manual.\nIf the engine windmills for more than 30 minutes with the firewall shutoff closed or the boost pump turned off, the engine fuel pump must be inspected in accordance with the Pratt & Whitney engine maintenance manual.")
                case "display_checklist_sing_eng_app":
                    self.ui.interaction_panel_text.setText("Single Engine Approach and Landing Checklist")
        self.current_countdown_timer.stop()
        self.next_countdown_timer.stop()
        # For current task counter
        try:
            seconds = int(current_task["time_init_action"])
            print(f"\nCurrent task time_init_action: {seconds} seconds")
            self.current_countdown_value = seconds
            self.ui.c_t_s_value_2.setText(str(self.current_countdown_value))
            self.current_countdown_timer.start()
        except (KeyError, ValueError, TypeError):
            seconds = "0"
            self.ui.c_t_s_value_2.setText(seconds)

        # For next task counter
        try:
            seconds = seconds + int(current_task["time_end_action"]) + int(next_task["time_init_action"])
            print(f"\nNext task time_init_action: {seconds} seconds")
            self.next_countdown_value = seconds
            self.ui.n_t_s_value_2.setText(str(self.next_countdown_value))
            self.next_countdown_timer.start()
        except (KeyError, ValueError, TypeError):
            seconds = "N/A"
            self.next_countdown_timer.stop()
            self.ui.n_t_s_value_2.setText(seconds)

        self.previous_state = self.current_state
    # ///////////////////////////////////////////////////////////////
    # BUTTONS CLICK
    # Post here your functions for clicked buttons
    # ///////////////////////////////////////////////////////////////
    def buttonClick(self):
        # GET BUTTON CLICKED
        btn = self.sender()
        btnName = btn.objectName()

        # SHOW BRIEFING PAGE
        if btnName == "btn_briefing":
            widgets.stackedWidget.setCurrentWidget(widgets.briefing)
            UIFunctions.resetStyle(self, btnName)
            btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet()))
        # SHOW HOME PAGE
        if btnName == "btn_home":
            widgets.stackedWidget.setCurrentWidget(widgets.home)
            UIFunctions.resetStyle(self, btnName)
            btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet()))

        # SHOW WIDGETS PAGE
        if btnName == "btn_widgets":
            widgets.stackedWidget.setCurrentWidget(widgets.widgets)
            UIFunctions.resetStyle(self, btnName)
            btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet()))

        # SHOW NEW PAGE
        if btnName == "btn_new":
            widgets.stackedWidget.setCurrentWidget(widgets.new_page) # SET PAGE
            UIFunctions.resetStyle(self, btnName) # RESET ANOTHERS BUTTONS SELECTED
            btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet())) # SELECT MENU

        if btnName == "btn_save":
            print("Save BTN clicked!")

        # PRINT BTN NAME
        print(f'Button "{btnName}" pressed!')


    def task_done_clicked(self):
        btn = self.sender()
        btn.setStyleSheet(f"""
                    border: 2px solid #3399ff;
                    border-radius: 5px;
                    background-color: rgba(0, 48, 20, 255);
                    font: 600 16pt "JetBrains Mono";
                """)
        self.start_glow_effect(self.ui.current_task_container_3, "green")
        self.agent.task_done_human[0] = True
        
        
    def task_cancel_clicked(self):
        btn = self.sender()
        btn.setStyleSheet(f"""
                    border: 2px solid #3399ff;
                    border-radius: 5px;
                    background-color: rgba(108, 04, 04, 255);
                    font: 600 16pt "JetBrains Mono";
                """)
        self.start_glow_effect(self.ui.current_task_container_3, "red")

    def show_button(self, button, color):
        if color == "green":
            button.setStyleSheet("""
                QPushButton {
                    border: 2px solid #3399ff;
                    border-radius: 5px;
                    background-color: rgba(0, 168, 120, 255);
                    font: 600 16pt "JetBrains Mono";
                }
            """)
        elif color == "red":
            button.setStyleSheet("""
                QPushButton {
                    border: 2px solid #3399ff;
                    border-radius: 5px;
                    background-color: rgba(208, 04, 04, 255);
                    font: 600 16pt "JetBrains Mono";
                }
            """)
        button.show()
    # RESIZE EVENTS
    # ///////////////////////////////////////////////////////////////
    def resizeEvent(self, event):
        # Update Size Grips
        UIFunctions.resize_grips(self)

    # MOUSE CLICK EVENTS
    # ///////////////////////////////////////////////////////////////
    def mousePressEvent(self, event):
        # SET DRAG POS WINDOW
        self.dragPos = event.globalPos()

        # PRINT MOUSE EVENTS
        if event.buttons() == Qt.LeftButton:
            print('Mouse click: LEFT CLICK')
        if event.buttons() == Qt.RightButton:
            print('Mouse click: RIGHT CLICK')
    


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Add this to allow Ctrl+C to work
    from PySide6.QtCore import QTimer
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(100)

    app.setWindowIcon(QIcon("icon.ico"))
    window = MainWindow()
    sys.exit(app.exec())
