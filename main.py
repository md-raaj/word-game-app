import json
import os
import hashlib
import threading
import base64
import wave
import tempfile
import time
import urllib.request
import urllib.parse

from kivy.app import App
from kivy.core.window import Window
from kivy.core.audio import SoundLoader
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.image import AsyncImage
from kivy.graphics import Color, RoundedRectangle, Line
from kivy.clock import Clock
import websocket
import requests


HAS_AUDIO_RECORD = True


Window.clearcolor = (0.96, 0.97, 0.99, 1)

SERVER_HTTP_URL = "https://render-word-game-server.onrender.com"
SERVER_WS_URL = "wss://render-word-game-server.onrender.com"
SESSION_FILE = "session.json"

def get_device_google_accounts():
    try:
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        AccountManager = autoclass('android.accounts.AccountManager')
        activity = PythonActivity.mActivity
        manager = AccountManager.get(activity)
        accounts = manager.getAccountsByType("com.google")
        return [acc.name for acc in accounts]
    except Exception:
        return ["user.main@gmail.com", "gaming.profile@gmail.com"]

def verify_user_before_join(email, username):
    try:
        # সার্ভারে পাঠানো হচ্ছে ইউজার ব্যান কি না চেক করার জন্য
        response = requests.get(f"{SERVER_HTTP_URL}/check-user-status/{email}", timeout=10)
        data = response.json()
        
        if not data.get("allowed", True):
            # যদি ব্যান করা থাকে, গেমের ভেতর ঢুকতে দেবে না
            # print("Access Denied: Your account is banned!")
            # return False
            return "banned"
        return "allowed"
        # print("Access Granted!")
        # return True
    except Exception as e:
        print("Server connection error:", e)
        # return "False"
        return "timeout"     # সার্ভার স্লো বা টাইমআউট হলে

class CardLayout(BoxLayout):
    def __init__(self, bg_color=(1, 1, 1, 1), border_color=None, **kwargs):
        super().__init__(**kwargs)
        self.bg_color = bg_color
        self.border_color = border_color
        self.draw_canvas()
        self.bind(pos=self.draw_canvas, size=self.draw_canvas)

    def draw_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.bg_color)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[16,])
            if self.border_color:
                Color(*self.border_color)
                Line(rounded_rectangle=(self.pos[0], self.pos[1], self.size[0], self.size[1], 16), width=2.5)

class StyledButton(Button):
    def __init__(self, bg_color=(0.14, 0.38, 0.92, 1), **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_color = (0, 0, 0, 0)
        self.color = (1, 1, 1, 1)
        self.bold = True
        self.bg_color = bg_color
        
        with self.canvas.before:
            Color(*self.bg_color)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[12,])
        self.bind(pos=self._update_rect, size=self._update_rect)

    def set_bg(self, color):
        self.bg_color = color
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.bg_color)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[12,])

    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

class PlayerCardWidget(CardLayout):
    def __init__(self, player_id, username, avatar_url, app_instance, **kwargs):
        super().__init__(orientation='vertical', padding=4, spacing=2, **kwargs)
        self.player_id = str(player_id)
        self.username = username
        self.avatar_url = avatar_url
        self.app_instance = app_instance
        self.full_chat_text = ""

        self.avatar_box = BoxLayout(size_hint_y=0.42, padding=[0, 2, 0, 2])
        self.avatar_img = AsyncImage(source=avatar_url)
        self.sticker_lbl = Label(text="", font_size=28)
        self.avatar_box.add_widget(self.avatar_img)
        self.add_widget(self.avatar_box)

        self.name_lbl = Label(
            text=f"[b]{username[:8]}[/b]\n[color=888888]Online[/color]",
            font_size=10, markup=True, halign='center', color=(0.1, 0.1, 0.2, 1), size_hint_y=0.23
        )
        self.add_widget(self.name_lbl)

        self.chat_lbl = Label(
            text="",
            font_size=11,
            bold=True,
            markup=True,
            halign='center',
            valign='middle',
            color=(0.0, 0.2, 0.8, 1),
            size_hint_y=0.35
        )
        self.chat_lbl.bind(size=self.chat_lbl.setter('text_size'))
        self.add_widget(self.chat_lbl)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if self.full_chat_text:
                self.app_instance.show_full_message_popup(self.username, self.full_chat_text)
                return True
        return super().on_touch_down(touch)

    def set_status(self, text, bg_color, border_color=None):
        self.bg_color = bg_color
        self.border_color = border_color
        self.draw_canvas()
        self.name_lbl.text = f"[b]{self.username[:8]}[/b]\n{text}"

    def set_chat(self, text):
        self.full_chat_text = text
        if text:
            display_text = text if len(text) <= 35 else text[:32] + "..."
            self.chat_lbl.text = f"[color=0033CC]💬 {display_text}[/color]\n[size=8][color=666666](Tap to read)[/color][/size]"
        else:
            self.chat_lbl.text = ""

    def set_emoji(self, emoji_icon):
        self.avatar_box.clear_widgets()
        if emoji_icon:
            self.sticker_lbl.text = emoji_icon
            self.avatar_box.add_widget(self.sticker_lbl)
        else:
            self.avatar_box.add_widget(self.avatar_img)


class WordGameApp(App):

    def __init__(self, **kwargs): # **kwargs যোগ করা ভালো
        super().__init__(**kwargs) # এই লাইনটি মিসিং ছিল, যার কারণে এরর দিয়েছে
        self.loading_popup = None

    def show_loading(self, message="Loading, please wait..."):
        if self.loading_popup:
            return
        content = BoxLayout(orientation='vertical', padding=20, spacing=15)
        content.add_widget(Label(text=message, markup=True, halign='center'))
        
        # পপআপ তৈরি (ব্যাকগ্রাউন্ড ট্রান্সপারেন্ট বা ডার্ক রাখতে পারেন)
        self.loading_popup = Popup(
            title="", 
            content=content, 
            size_hint=(0.6, 0.25), 
            auto_dismiss=False,
            background="",
            background_color=(0, 0, 0, 0.8) # হালকা ডার্ক ওভারলে
        )
        self.loading_popup.open()

    def hide_loading(self):
        if self.loading_popup:
            self.loading_popup.dismiss()
            self.loading_popup = None
    def build(self):
        self.user = None
        self.room_id = None
        self.player_id = None
        self.ws = None
        self.players = []
        self.current_turn_id = None
        self.all_game_words = []
        
        self.player_cards = {}
        self.active_chats = {}     
        self.chat_timers = {}
        self.emoji_timers = {}
        self.bounce_states = {}
        self.talking_players = set()
        self.talking_events = {}

        self.is_recording = False
        self.audio_frames = []

        self.root = BoxLayout(orientation='vertical', padding=10, spacing=8)
        
        if not self.load_session():
            self.show_login_screen()
            
        return self.root

    def save_session(self, user_data):
        with open(SESSION_FILE, "w") as f:
            json.dump(user_data, f)

    def load_session(self):
        if os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, "r") as f:
                    self.user = json.load(f)
                    self.show_lobby_screen()
                    return True
            except Exception:
                return False
        return False

    # def clear_session(self):
    #     if os.path.exists(SESSION_FILE):
    #         os.remove(SESSION_FILE)
    #     self.user = None
    #     self.show_login_screen()


    def clear_session(self):
        self.show_loading("Switching account...")
        
        def do_switch(dt):
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
            self.user = None
            self.hide_loading()
            self.show_login_screen()
            
        # সামান্য বিরতি দিয়ে লোডিং বন্ধ করে লগইন স্ক্রিন আনবে
        Clock.schedule_once(do_switch, 0.5)

    def generate_profile_data(self, email):
        raw_name = email.split('@')[0].replace('.', ' ').replace('_', ' ')
        display_name = raw_name.title()
        email_hash = hashlib.md5(email.strip().lower().encode('utf-8')).hexdigest()
        avatar_url = f"https://www.gravatar.com/avatar/{email_hash}?d=identicon&s=300"
        return display_name, avatar_url

    def show_login_screen(self):
        self.root.clear_widgets()
        card = CardLayout(orientation='vertical', padding=25, spacing=15, size_hint=(1, 0.75))

        title = Label(text="Word Chain", font_size=36, bold=True, color=(0.1, 0.1, 0.2, 1), size_hint_y=0.3)
        subtitle = Label(text="Login with Google Account", font_size=14, color=(0.5, 0.5, 0.6, 1), halign='center', size_hint_y=0.2)
        btn_mail_login = StyledButton(text="Select Google Account", size_hint_y=0.25, bg_color=(0.14, 0.38, 0.92, 1))
        btn_mail_login.bind(on_press=self.open_account_picker)

        card.add_widget(title)
        card.add_widget(subtitle)
        card.add_widget(btn_mail_login)
        self.root.add_widget(card)

    def open_account_picker(self, instance):
        accounts = get_device_google_accounts()
        content = BoxLayout(orientation='vertical', spacing=10, padding=10)
        popup_label = Label(text="Choose an Account", font_size=18, bold=True, color=(0.1, 0.1, 0.2, 1), size_hint_y=0.15)
        content.add_widget(popup_label)

        scroll = ScrollView(size_hint=(1, 0.85))
        acc_list_box = BoxLayout(orientation='vertical', spacing=8, size_hint_y=None)
        acc_list_box.bind(minimum_height=acc_list_box.setter('height'))

        for email in accounts:
            btn = StyledButton(text=email, size_hint_y=None, height=45, bg_color=(0.92, 0.94, 0.98, 1))
            btn.color = (0.1, 0.1, 0.2, 1)
            btn.bind(on_press=lambda btn_obj, acc=email: self.select_account(acc))
            acc_list_box.add_widget(btn)

        scroll.add_widget(acc_list_box)
        content.add_widget(scroll)

        self.popup = Popup(title="", content=content, size_hint=(0.88, 0.55), background="", background_color=(1, 1, 1, 1))
        self.popup.open()

    # def select_account(self, email):
    #     if hasattr(self, 'popup'):
    #         self.popup.dismiss()

    #     username, avatar_url = self.generate_profile_data(email)
        
    #     # সার্ভার থেকে ইউজার ব্যান কি না চেক করা হচ্ছে
    #     if not verify_user_before_join(email, username):
    #         content = BoxLayout(orientation='vertical', padding=15, spacing=10)
    #         content.add_widget(Label(text="[b][color=FF0000]Access Denied![/color][/b]\nYour account is banned.", markup=True, halign='center'))
    #         btn_ok = StyledButton(text="OK", size_hint_y=0.4, bg_color=(0.8, 0.2, 0.2, 1))
    #         popup = Popup(title="", content=content, size_hint=(0.7, 0.3), background="", background_color=(1, 1, 1, 1))
    #         btn_ok.bind(on_press=popup.dismiss)
    #         content.add_widget(btn_ok)
    #         popup.open()
    #         return

    #     self.user = {"email": email, "username": username, "avatar_url": avatar_url}
    #     self.save_session(self.user)
    #     self.show_lobby_screen()

    # def select_account(self, email):
    #     if hasattr(self, 'popup'):
    #         self.popup.dismiss()

    #     # ১. অ্যাকাউন্ট সিলেক্ট করার সাথে সাথেই লোডিং স্ক্রিন দেখান
    #     self.show_loading("Logging in, please wait...")

    #     def background_task():
    #         try:
    #             username, avatar_url = self.generate_profile_data(email)
                
    #             # সার্ভারে ইউজার ব্যান কি না চেক করা হচ্ছে
    #             if not verify_user_before_join(email, username):
    #                 # যদি ব্যান করা থাকে, লোডিং বন্ধ করে পপআপ দেখান
    #                 Clock.schedule_once(lambda dt: self.hide_loading(), 0)
    #                 Clock.schedule_once(lambda dt: self.show_banned_popup(), 0)
    #                 return

    #             # সফল হলে সেশন সেভ করে লবি স্ক্রিনে যান
    #             self.user = {"email": email, "username": username, "avatar_url": avatar_url}
    #             self.save_session(self.user)
                
    #             Clock.schedule_once(lambda dt: self.finish_login_success(), 0)
    #         except Exception as e:
    #             print("Login error:", e)
    #             Clock.schedule_once(lambda dt: self.hide_loading(), 0)

    #     threading.Thread(target=background_task, daemon=True).start()


    def select_account(self, email):
        if hasattr(self, 'popup'):
            self.popup.dismiss()

        self.show_loading("Logging in, please wait...")

        def background_task():
            try:
                username, avatar_url = self.generate_profile_data(email)
                
                status = verify_user_before_join(email, username)
                
                if status == "banned":
                    Clock.schedule_once(lambda dt: self.hide_loading(), 0)
                    Clock.schedule_once(lambda dt: self.show_banned_popup(), 0)
                    return
                elif status == "timeout":
                    Clock.schedule_once(lambda dt: self.hide_loading(), 0)
                    Clock.schedule_once(lambda dt: setattr(self.error_label, 'text', "Server waking up, try again!"), 0)
                    # অথবা চাইলে এখানেও আলাদা পপআপ দেখাতে পারেন
                    return

                # সফল হলে
                self.user = {"email": email, "username": username, "avatar_url": avatar_url}
                self.save_session(self.user)
                Clock.schedule_once(lambda dt: self.finish_login_success(), 0)
                
            except Exception as e:
                print("Login error:", e)
                Clock.schedule_once(lambda dt: self.hide_loading(), 0)

        threading.Thread(target=background_task, daemon=True).start()


    def finish_login_success(self):
        self.hide_loading()
        self.show_lobby_screen()

    def show_banned_popup(self):
        content = BoxLayout(orientation='vertical', padding=15, spacing=10)
        content.add_widget(Label(text="[b][color=FF0000]Access Denied![/color][/b]\nYour account is banned.", markup=True, halign='center'))
        btn_ok = StyledButton(text="OK", size_hint_y=0.4, bg_color=(0.8, 0.2, 0.2, 1))
        popup = Popup(title="", content=content, size_hint=(0.7, 0.3), background="", background_color=(1, 1, 1, 1))
        btn_ok.bind(on_press=popup.dismiss)
        content.add_widget(btn_ok)
        popup.open()

    def show_lobby_screen(self):
        self.root.clear_widgets()

        profile_card = CardLayout(orientation='horizontal', padding=15, spacing=15, size_hint=(1, 0.22))
        avatar = AsyncImage(source=self.user['avatar_url'], size_hint=(0.28, 1))
        
        info_box = BoxLayout(orientation='vertical', spacing=3)
        name_label = Label(text=self.user['username'], font_size=20, bold=True, color=(0.1, 0.1, 0.2, 1), halign='left')
        name_label.bind(size=name_label.setter('text_size'))
        email_label = Label(text=self.user['email'], font_size=12, color=(0.5, 0.5, 0.6, 1), halign='left')
        email_label.bind(size=email_label.setter('text_size'))
        
        info_box.add_widget(name_label)
        info_box.add_widget(email_label)

        profile_card.add_widget(avatar)
        profile_card.add_widget(info_box)

        action_card = CardLayout(orientation='vertical', padding=20, spacing=12, size_hint=(1, 0.63))
        room_title = Label(text="Multiplayer Lobby", font_size=18, bold=True, color=(0.2, 0.2, 0.3, 1), size_hint_y=0.15)
        
        self.room_input = TextInput(
            hint_text="ENTER 4-DIGIT CODE", 
            multiline=False, size_hint_y=0.22, halign='center', font_size=20,
            padding=[10, 10, 10, 10], background_color=(0.95, 0.96, 0.98, 1)
        )
        self.error_label = Label(text="", size_hint_y=0.1, color=(0.9, 0.2, 0.2, 1), font_size=13)
        
        btn_join = StyledButton(text="Join Room", size_hint_y=0.22, bg_color=(0.14, 0.38, 0.92, 1))
        btn_join.bind(on_press=self.join_room)

        btn_create = StyledButton(text="+ Create New Room", size_hint_y=0.22, bg_color=(0.09, 0.63, 0.36, 1))
        btn_create.bind(on_press=self.open_create_room_modal)

        action_card.add_widget(room_title)
        action_card.add_widget(self.room_input)
        action_card.add_widget(self.error_label)
        action_card.add_widget(btn_join)
        action_card.add_widget(btn_create)

        btn_logout = StyledButton(text="Switch Account", size_hint=(1, 0.12), bg_color=(0.8, 0.2, 0.2, 1))
        btn_logout.bind(on_press=lambda x: self.clear_session())

        self.root.add_widget(profile_card)
        self.root.add_widget(action_card)
        self.root.add_widget(btn_logout)

    def open_create_room_modal(self, instance):
        content = BoxLayout(orientation='vertical', spacing=15, padding=15)
        lbl = Label(text="Select Player Capacity", font_size=18, bold=True, color=(0.1, 0.1, 0.2, 1))
        content.add_widget(lbl)

        btn_box = BoxLayout(spacing=10)
        for count in [2, 3, 4]:
            btn = StyledButton(text=f"{count} Players", bg_color=(0.14, 0.38, 0.92, 1))
            btn.bind(on_press=lambda b, c=count: self.create_room(c))
            btn_box.add_widget(btn)

        content.add_widget(btn_box)
        self.room_modal = Popup(title="", content=content, size_hint=(0.85, 0.35), background="", background_color=(1, 1, 1, 1))
        self.room_modal.open()

    # def create_room(self, max_players):
    #     if hasattr(self, 'room_modal'):
    #         self.room_modal.dismiss()

    #     try:
    #         response = urllib.request.urlopen(f"{SERVER_HTTP_URL}/create-room?max_players={max_players}")
    #         data = json.loads(response.read().decode())
    #         if data.get("status") == "success":
    #             self.start_game(data.get("room_id"))
    #     except Exception:
    #         self.error_label.text = "Server offline!"

    def create_room(self, max_players):
        if hasattr(self, 'room_modal'):
            self.room_modal.dismiss()
        
        # লোডিং স্ক্রিন চালু করুন
        self.show_loading("Creating room...")

        def background_task():
            try:
                response = urllib.request.urlopen(f"{SERVER_HTTP_URL}/create-room?max_players={max_players}", timeout=10)
                data = json.loads(response.read().decode())
                if data.get("status") == "success":
                    Clock.schedule_once(lambda dt: self.finish_create_room(data.get("room_id")), 0)
                else:
                    Clock.schedule_once(lambda dt: self.hide_loading(), 0)
            except Exception:
                Clock.schedule_once(lambda dt: self.hide_loading(), 0)
                Clock.schedule_once(lambda dt: setattr(self.error_label, 'text', "Server waking up, try again!"), 0)

        threading.Thread(target=background_task, daemon=True).start()

    def finish_create_room(self, room_id):
        self.hide_loading()
        self.start_game(room_id)

    # def join_room(self, instance):
    #     code = self.room_input.text.strip().upper()
    #     if not code:
    #         self.error_label.text = "Please enter room code!"
    #         return

    #     try:
    #         response = urllib.request.urlopen(f"{SERVER_HTTP_URL}/check-room/{code}")
    #         data = json.loads(response.read().decode())
    #         if data.get("valid"):
    #             self.start_game(code)
    #         else:
    #             self.error_label.text = f"Error: {data.get('message')}"
    #     except Exception:
    #         self.error_label.text = "Server connection error!"

    def join_room(self, instance):
        code = self.room_input.text.strip().upper()
        if not code:
            self.error_label.text = "Please enter room code!"
            return

        # লোডিং স্ক্রিন চালু করুন
        self.show_loading("Joining room...")

        def background_task():
            try:
                response = urllib.request.urlopen(f"{SERVER_HTTP_URL}/check-room/{code}", timeout=10)            
                data = json.loads(response.read().decode())
                if data.get("valid"):
                    Clock.schedule_once(lambda dt: self.finish_join_room(code), 0)
                else:
                    Clock.schedule_once(lambda dt: self.hide_loading(), 0)
                    Clock.schedule_once(lambda dt: setattr(self.error_label, 'text', f"Error: {data.get('message')}"), 0)
            except Exception:
                Clock.schedule_once(lambda dt: self.hide_loading(), 0)
                Clock.schedule_once(lambda dt: setattr(self.error_label, 'text', "Server waking up, try again!"), 0)

        threading.Thread(target=background_task, daemon=True).start()

    def finish_join_room(self, code):
        self.hide_loading()
        self.start_game(code)

    def start_game(self, room_code):
        self.room_id = room_code
        self.all_game_words = []
        self.root.clear_widgets()

        header_card = CardLayout(orientation='vertical', padding=10, spacing=4, size_hint=(1, 0.15), bg_color=(0.92, 0.94, 0.98, 1))
        
        top_row = BoxLayout(size_hint_y=0.4)
        lbl_room = Label(text=f"ROOM: {self.room_id}", color=(0.14, 0.38, 0.92, 1), bold=True, halign='left')
        
        btn_view_words = StyledButton(text="View All Words", size_hint_x=0.36, bg_color=(0.14, 0.38, 0.92, 1))
        btn_view_words.bind(on_press=self.show_all_words_popup)

        btn_leave = StyledButton(text="Leave", size_hint_x=0.22, bg_color=(0.9, 0.2, 0.2, 1))
        btn_leave.bind(on_press=self.leave_room)
        
        top_row.add_widget(lbl_room)
        top_row.add_widget(btn_view_words)
        top_row.add_widget(btn_leave)

        self.next_letter_label = Label(
            text="WAITING FOR PLAYERS...", 
            font_size=16, bold=True, markup=True,
            color=(0.1, 0.1, 0.2, 1), size_hint_y=0.6
        )

        header_card.add_widget(top_row)
        header_card.add_widget(self.next_letter_label)
        self.root.add_widget(header_card)

        self.players_container = CardLayout(orientation='horizontal', padding=6, spacing=6, size_hint=(1, 0.26))
        self.root.add_widget(self.players_container)

        self.word_card = CardLayout(orientation='vertical', padding=8, spacing=3, size_hint=(1, 0.18), bg_color=(0.14, 0.38, 0.92, 0.08), border_color=(0.14, 0.38, 0.92, 0.2))
        
        # Point 1: Updated initial text to "Type any word to begin!" instead of waiting message when player joins
        self.current_word_display = Label(
            text="[color=09A05B]Type any word to begin![/color]", 
            font_size=20, bold=True, markup=True, halign='center'
        )
        self.word_by_user_label = Label(text="", font_size=11, color=(0.4, 0.4, 0.5, 1), halign='center', markup=True)
        self.alert_label = Label(text="", size_hint_y=0.25, color=(0.9, 0.2, 0.2, 1), bold=True, markup=True)
        
        self.word_card.add_widget(self.current_word_display)
        self.word_card.add_widget(self.word_by_user_label)
        self.word_card.add_widget(self.alert_label)
        self.root.add_widget(self.word_card)

        chat_section = CardLayout(orientation='vertical', padding=4, spacing=2, size_hint=(1, 0.16), bg_color=(1, 1, 1, 1), border_color=(0.85, 0.88, 0.92, 1))
        chat_header_lbl = Label(text="[b]Chat History[/b]", font_size=11, markup=True, color=(0.14, 0.38, 0.92, 1), size_hint_y=None, height=18)
        chat_section.add_widget(chat_header_lbl)

        self.chat_scroll = ScrollView(size_hint=(1, 1))
        self.chat_history_box = BoxLayout(orientation='vertical', spacing=4, size_hint_y=None)
        self.chat_history_box.bind(minimum_height=self.chat_history_box.setter('height'))
        self.chat_scroll.add_widget(self.chat_history_box)
        chat_section.add_widget(self.chat_scroll)
        self.root.add_widget(chat_section)

        emoji_bar = CardLayout(orientation='horizontal', padding=4, spacing=4, size_hint=(1, 0.07))
        emojis = [("😂", "haha"), ("😡", "angry"), ("😭", "cry"), ("😄", "happy")]
        for emoji_icon, react_code in emojis:
            btn = StyledButton(text=emoji_icon, bg_color=(0.92, 0.94, 0.98, 1), font_size=18)
            btn.bind(on_press=lambda instance, r=react_code: self.send_reaction(r))
            emoji_bar.add_widget(btn)

        self.root.add_widget(emoji_bar)

        self.controls_card = CardLayout(orientation='vertical', padding=6, spacing=4, size_hint=(1, 0.18))

        self.word_box = BoxLayout(size_hint_y=0.33, spacing=6)
        self.word_input = TextInput(hint_text="Type English word...", multiline=False, padding=[6, 6, 6, 6], background_color=(0.95, 0.96, 0.98, 1))
        self.btn_send_word = StyledButton(text="SEND WORD", size_hint_x=0.35, bg_color=(0.09, 0.63, 0.36, 1))
        self.btn_send_word.bind(on_press=self.send_word)
        self.word_box.add_widget(self.word_input)
        self.word_box.add_widget(self.btn_send_word)

        self.chat_box = BoxLayout(size_hint_y=0.33, spacing=6)
        self.chat_input = TextInput(hint_text="Type Chat Message...", multiline=False, padding=[6, 6, 6, 6], background_color=(0.95, 0.96, 0.98, 1))
        self.btn_send_chat = StyledButton(text="CHAT", size_hint_x=0.35, bg_color=(0.14, 0.38, 0.92, 1))
        self.btn_send_chat.bind(on_press=self.send_chat)
        self.chat_box.add_widget(self.chat_input)
        self.chat_box.add_widget(self.btn_send_chat)

        self.voice_bar = BoxLayout(size_hint_y=0.33, spacing=6)
        self.btn_mic = StyledButton(text="Record Voice", size_hint_x=0.45, bg_color=(0.14, 0.38, 0.92, 1))
        self.btn_mic.bind(on_press=self.toggle_voice_recording)

        self.btn_voice_delete = StyledButton(text="Delete", size_hint_x=0.25, bg_color=(0.8, 0.2, 0.2, 1))
        self.btn_voice_delete.bind(on_press=self.cancel_recording)
        self.btn_voice_delete.opacity = 0
        self.btn_voice_delete.disabled = True

        self.btn_voice_send = StyledButton(text="Send", size_hint_x=0.30, bg_color=(0.09, 0.63, 0.36, 1))
        self.btn_voice_send.bind(on_press=self.send_recorded_voice)
        self.btn_voice_send.opacity = 0
        self.btn_voice_send.disabled = True

        self.voice_bar.add_widget(self.btn_mic)
        self.voice_bar.add_widget(self.btn_voice_delete)
        self.voice_bar.add_widget(self.btn_voice_send)

        self.controls_card.add_widget(self.word_box)
        self.controls_card.add_widget(self.chat_box)
        self.controls_card.add_widget(self.voice_bar)
        self.root.add_widget(self.controls_card)

        threading.Thread(target=self.connect_to_server, daemon=True).start()

    def append_chat_to_history_box(self, sender_name, message_text):
        chat_item_lbl = Label(
            text=f"[b]{sender_name}:[/b] {message_text}",
            font_size=12,
            markup=True,
            color=(0.1, 0.1, 0.2, 1),
            size_hint_y=None,
            height=24,
            halign='left',
            valign='middle'
        )
        chat_item_lbl.bind(size=chat_item_lbl.setter('text_size'))
        self.chat_history_box.add_widget(chat_item_lbl)
        Clock.schedule_once(lambda dt: setattr(self.chat_scroll, 'scroll_y', 0), 0.1)

    def show_all_words_popup(self, instance):
        content = BoxLayout(orientation='vertical', spacing=12, padding=15)
        
        title_lbl = Label(
            text="[b]All Submitted Words (A-Z)[/b]", 
            font_size=16, markup=True, color=(0.14, 0.38, 0.92, 1), size_hint_y=0.15
        )
        content.add_widget(title_lbl)

        scroll = ScrollView(size_hint=(1, 0.7))
        list_box = BoxLayout(orientation='vertical', spacing=6, size_hint_y=None)
        list_box.bind(minimum_height=list_box.setter('height'))

        if not self.all_game_words:
            empty_lbl = Label(text="No words played yet!", font_size=14, color=(0.6, 0.6, 0.6, 1), size_hint_y=None, height=40)
            list_box.add_widget(empty_lbl)
        else:
            sorted_words = sorted(list(set(self.all_game_words)))
            current_char = ""
            for word in sorted_words:
                first_letter = word[0].upper()
                if first_letter != current_char:
                    current_char = first_letter
                    header_lbl = Label(
                        text=f"[b]-- {current_char} --[/b]", 
                        font_size=14, markup=True, color=(0.09, 0.63, 0.36, 1), 
                        size_hint_y=None, height=30, halign='left'
                    )
                    header_lbl.bind(size=header_lbl.setter('text_size'))
                    list_box.add_widget(header_lbl)

                w_lbl = Label(
                    text=f"• {word}", 
                    font_size=14, color=(0.1, 0.1, 0.2, 1), 
                    size_hint_y=None, height=30, halign='left'
                )
                w_lbl.bind(size=w_lbl.setter('text_size'))
                list_box.add_widget(w_lbl)

        scroll.add_widget(list_box)
        content.add_widget(scroll)

        btn_close = StyledButton(text="Close", size_hint_y=0.15, bg_color=(0.8, 0.2, 0.2, 1))
        popup = Popup(
            title="", content=content, size_hint=(0.85, 0.6),
            background="", background_color=(1, 1, 1, 1)
        )
        btn_close.bind(on_press=popup.dismiss)
        content.add_widget(btn_close)
        popup.open()

    def show_full_message_popup(self, sender_name, message_text):
        content = BoxLayout(orientation='vertical', spacing=12, padding=15)
        title_lbl = Label(
            text=f"[b]{sender_name}'s Message[/b]", 
            font_size=16, markup=True, color=(0.14, 0.38, 0.92, 1), size_hint_y=0.2
        )
        content.add_widget(title_lbl)

        scroll = ScrollView(size_hint=(1, 0.65))
        msg_lbl = Label(
            text=message_text, font_size=15, color=(0.1, 0.1, 0.2, 1),
            halign='left', valign='top', size_hint_y=None
        )
        msg_lbl.bind(width=lambda s, w: setattr(s, 'text_size', (w, None)))
        msg_lbl.bind(texture_size=lambda s, size: setattr(s, 'height', size[1]))
        scroll.add_widget(msg_lbl)
        content.add_widget(scroll)

        btn_close = StyledButton(text="Close", size_hint_y=0.15, bg_color=(0.8, 0.2, 0.2, 1))
        popup = Popup(title="", content=content, size_hint=(0.85, 0.45), background="", background_color=(1, 1, 1, 1))
        btn_close.bind(on_press=popup.dismiss)
        content.add_widget(btn_close)
        popup.open()

    def play_reaction_sound(self, reaction):
        def _async_sound():
            for ext in ['mp3', 'wav']:
                sound_path = os.path.join("sounds", f"{reaction}.{ext}")
                if os.path.exists(sound_path):
                    sound = SoundLoader.load(sound_path)
                    if sound:
                        sound.play()
                        return
        threading.Thread(target=_async_sound, daemon=True).start()

    # def toggle_voice_recording(self, instance):
    #     if not HAS_AUDIO_RECORD:
    #         self.alert_label.text = "Install 'pyaudio' to use Voice Chat!"
    #         return

    #     if not self.is_recording:
    #         self.is_recording = True
    #         self.audio_frames = []
    #         self.btn_mic.text = "Recording..."
    #         self.btn_mic.set_bg((0.9, 0.2, 0.2, 1))
            
    #         self.btn_voice_delete.opacity = 1
    #         self.btn_voice_delete.disabled = False
    #         self.btn_voice_send.opacity = 1
    #         self.btn_voice_send.disabled = False

    #         threading.Thread(target=self._record_audio_thread, daemon=True).start()

    # def _record_audio_thread(self):
    #     try:
    #         p = pyaudio.PyAudio()
    #         stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
    #         while self.is_recording:
    #             data = stream.read(1024)
    #             self.audio_frames.append(data)
    #         stream.stop_stream()
    #         stream.close()
    #         p.terminate()
    #     except Exception:
    #         pass

    # def cancel_recording(self, instance):
    #     self.is_recording = False
    #     self.audio_frames = []
    #     self.btn_mic.text = "Record Voice"
    #     self.btn_mic.set_bg((0.14, 0.38, 0.92, 1))
        
    #     self.btn_voice_delete.opacity = 0
    #     self.btn_voice_delete.disabled = True
    #     self.btn_voice_send.opacity = 0
    #     self.btn_voice_send.disabled = True

    def toggle_voice_recording(self, instance):
        if not HAS_AUDIO_RECORD:
            self.alert_label.text = "Voice record not supported!"
            return

        if not self.is_recording:
            self.is_recording = True
            self.audio_frames = []
            self.btn_mic.text = "Recording..."
            self.btn_mic.set_bg((0.9, 0.2, 0.2, 1))
            
            self.btn_voice_delete.opacity = 1
            self.btn_voice_delete.disabled = False
            self.btn_voice_send.opacity = 1
            self.btn_voice_send.disabled = False

            threading.Thread(target=self._record_audio_thread, daemon=True).start()

    def _record_audio_thread(self):
        try:
            from jnius import autoclass
            AudioRecord = autoclass('android.media.AudioRecord')
            AudioSource = autoclass('android.media.MediaRecorder$AudioSource')
            AudioFormat = autoclass('android.media.MediaFormat')
            Encoding = autoclass('android.media.AudioFormat')
            
            sample_rate = 16000
            channel_config = 1 # CHANNEL_IN_MONO
            audio_format = 2 # ENCODING_PCM_16BIT
            
            min_buffer_size = AudioRecord.getMinBufferSize(sample_rate, channel_config, audio_format)
            buffer_size = max(min_buffer_size, 1024 * 2)

            recorder = AudioRecord(
                AudioSource.MIC,
                sample_rate,
                channel_config,
                audio_format,
                buffer_size
            )
            
            byte_buffer = autoclass('java.nio.ByteBuffer').allocateDirect(buffer_size)
            recorder.startRecording()
            
            while self.is_recording:
                try:
                    # Pyjnius দিয়ে জাভা বাফার থেকে সরাসরি অডিও রিড করা
                    result = recorder.read(byte_buffer, buffer_size)
                    if result > 0:
                        # বাইট অ্যারেতে রূপান্তর
                        ba = bytearray(result)
                        byte_buffer.position(0)
                        byte_buffer.get(ba, 0, result)
                        self.audio_frames.append(bytes(ba))
                except Exception:
                    break
                    
            recorder.stop()
            recorder.release()
        except Exception as e:
            print("PyJnius Audio Error:", e)

    def cancel_recording(self, instance):
        self.is_recording = False
        self.audio_frames = []
        self.btn_mic.text = "Record Voice"
        self.btn_mic.set_bg((0.14, 0.38, 0.92, 1))
        
        self.btn_voice_delete.opacity = 0
        self.btn_voice_delete.disabled = True
        self.btn_voice_send.opacity = 0
        self.btn_voice_send.disabled = True


    def send_recorded_voice(self, instance):
        self.is_recording = False
        captured_frames = list(self.audio_frames)
        self.cancel_recording(None)

        if not captured_frames:
            return

        def _async_send():
            temp_dir = tempfile.gettempdir()
            temp_filepath = os.path.abspath(os.path.join(temp_dir, f"send_{time.time_ns()}.wav"))
            try:
                wf = wave.open(temp_filepath, 'wb')
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b''.join(captured_frames))
                wf.close()

                with open(temp_filepath, "rb") as f:
                    b64_audio = base64.b64encode(f.read()).decode('utf-8')

                if self.ws:
                    payload = json.dumps({"type": "voice", "audio_data": b64_audio})
                    self.ws.send(payload)
                    
                    # Point 2: Trigger local feedback (chat & bouncing animation) for the sender as well
                    if self.player_id:
                        Clock.schedule_once(lambda dt: self.play_voice_b64_async(self.player_id, b64_audio))

            except Exception as e:
                print("Voice Send Error:", e)
            finally:
                if os.path.exists(temp_filepath):
                    try:
                        os.remove(temp_filepath)
                    except Exception:
                        pass

        threading.Thread(target=_async_send, daemon=True).start()

    def play_voice_b64_async(self, player_id, b64_data):
        pid = str(player_id)
        def _async_play():
            temp_dir = tempfile.gettempdir()
            temp_filepath = os.path.abspath(os.path.join(temp_dir, f"v_play_{time.time_ns()}.wav"))
            try:
                raw_bytes = base64.b64decode(b64_data)
                with open(temp_filepath, "wb") as f:
                    f.write(raw_bytes)

                Clock.schedule_once(lambda dt: self.display_player_chat(pid, "🎙️ Voice Message"))
                Clock.schedule_once(lambda dt: self.start_talking_animation(pid))

                sound = SoundLoader.load(temp_filepath)
                if sound:
                    sound.play()
                    time.sleep(2.5)

            except Exception as e:
                print("Voice Play Error:", e)
            finally:
                Clock.schedule_once(lambda dt: self.stop_talking_animation(pid))
                if os.path.exists(temp_filepath):
                    try:
                        os.remove(temp_filepath)
                    except Exception:
                        pass

        threading.Thread(target=_async_play, daemon=True).start()

    def start_talking_animation(self, player_id):
        pid = str(player_id)
        self.talking_players.add(pid)
        
        def toggle_bounce(dt):
            if pid in self.talking_players and pid in self.player_cards:
                self.bounce_states[pid] = not self.bounce_states.get(pid, False)
                card = self.player_cards[pid]
                card.avatar_box.padding = [0, 4 if self.bounce_states[pid] else 0, 0, 0 if self.bounce_states[pid] else 4]

        event = Clock.schedule_interval(toggle_bounce, 0.15)
        self.talking_events[pid] = event

    def stop_talking_animation(self, player_id):
        pid = str(player_id)
        if pid in self.talking_players:
            self.talking_players.remove(pid)
        if pid in self.talking_events:
            self.talking_events[pid].cancel()
            del self.talking_events[pid]
        if pid in self.player_cards:
            self.player_cards[pid].avatar_box.padding = [0, 2, 0, 2]

    def display_player_chat(self, player_id, text):
        pid = str(player_id)
        self.active_chats[pid] = text  

        if pid in self.player_cards:
            card = self.player_cards[pid]
            card.set_chat(text)

        duration = max(4.0, min(15.0, len(text) * 0.1 + 3.0))

        if pid in self.chat_timers:
            self.chat_timers[pid].cancel()

        def clear_chat(dt):
            self.active_chats.pop(pid, None)
            if pid in self.player_cards:
                self.player_cards[pid].set_chat("")
            self.chat_timers.pop(pid, None)

        self.chat_timers[pid] = Clock.schedule_once(clear_chat, duration)

    def display_player_emoji(self, player_id, reaction):
        pid = str(player_id)
        emoji_map = {"haha": "😂", "angry": "😡", "cry": "😭", "happy": "😄"}
        emoji_icon = emoji_map.get(reaction, "😂")

        if pid in self.player_cards:
            card = self.player_cards[pid]
            card.set_emoji(emoji_icon)

            if pid in self.emoji_timers:
                self.emoji_timers[pid].cancel()

            def clear_emoji(dt):
                if pid in self.player_cards:
                    self.player_cards[pid].set_emoji(None)
                self.emoji_timers.pop(pid, None)

            self.emoji_timers[pid] = Clock.schedule_once(clear_emoji, 2.5)

    def send_reaction(self, reaction_code):
        if self.ws:
            payload = json.dumps({"type": "reaction", "reaction": reaction_code})
            self.ws.send(payload)

    def leave_room(self, instance):
        if self.ws:
            self.ws.close()
        self.show_lobby_screen()

    def connect_to_server(self):
        encoded_user = urllib.parse.quote(self.user['username'])
        encoded_avatar = urllib.parse.quote(self.user['avatar_url'])
        encoded_email = urllib.parse.quote(self.user['email'])
        # ws_url = f"{SERVER_WS_URL}/ws/{self.room_id}/{encoded_user}?avatar_url={encoded_avatar}"
        ws_url = f"{SERVER_WS_URL}/ws/{self.room_id}/{encoded_user}?avatar_url={encoded_avatar}&email={encoded_email}"
        # ws_url = f"{SERVER_WS_URL}/ws/{self.room_id}/{encoded_user}/{self.user['email']}?avatar_url={encoded_avatar}"
        self.ws = websocket.WebSocketApp(
            ws_url,
            on_open=self.on_open,       # ১. কানেকশন ওপেন হলে এই ফাংশন কল হবে
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.ws.run_forever()

    def on_open(self, ws):
        # ২. ব্যাকগ্রাউন্ডে একটি লুপ চালু করা যা প্রতি ৩০ সেকেন্ড পর পর সার্ভারে ping পাঠাবে
        def send_ping():
            while True:
                time.sleep(30)
                try:
                    if self.ws and self.ws.sock and self.ws.sock.connected:
                        self.ws.send(json.dumps({"type": "ping"}))
                    else:
                        break
                except Exception:
                    break

        # থ্রেড স্টার্ট করা যাতে গেমের মূল কাজ থেমে না থাকে
        threading.Thread(target=send_ping, daemon=True).start()

    def on_message(self, ws, message):
        data = json.loads(message)
        msg_type = data.get("type")

        if msg_type == "init":
            self.player_id = str(data.get("player_id"))

        elif msg_type == "players_update":
            self.players = data.get("players", [])
            Clock.schedule_once(lambda dt: self.sync_player_cards())

        elif msg_type == "turn_update":
            self.current_turn_id = str(data.get("current_turn_id")) if data.get("current_turn_id") else None
            Clock.schedule_once(lambda dt: self.update_statuses())
            Clock.schedule_once(lambda dt: self.update_turn_ui())

        elif msg_type == "sync_history":
            self.all_game_words = data.get("used_words", [])
            last_word = data.get("last_word", "")
            last_letter = data.get("last_letter", "")
            chat_history = data.get("chat_history", [])

            active_online = [p for p in self.players if p.get("is_online")]
            if len(active_online) >= 2:
                Clock.schedule_once(lambda dt: setattr(self.alert_label, 'text', ''))
                if last_word:
                    next_text = f"NEXT LETTER: [size=28][color=FF3D00]{last_letter}[/color][/size]"
                    word_html = f"[color=09A05B]{last_word.upper()}[/color]"
                else:
                    next_text = f"GAME STARTED! SUBMIT FIRST WORD"
                    word_html = f"[color=09A05B]Type any word to begin![/color]"

                Clock.schedule_once(lambda dt: setattr(self.next_letter_label, 'text', next_text))
                Clock.schedule_once(lambda dt: setattr(self.current_word_display, 'text', word_html))

            def restore_chats(dt):
                self.chat_history_box.clear_widgets()
                for ch in chat_history:
                    self.append_chat_to_history_box(ch.get("username"), ch.get("message"))
            Clock.schedule_once(restore_chats)

        elif msg_type == "word_success":
            uname = data.get("username")
            word = data.get("word")
            last_letter = data.get("last_letter")
            
            if word and word not in self.all_game_words:
                self.all_game_words.append(word)

            next_text = f"NEXT LETTER: [size=28][color=FF3D00]{last_letter}[/color][/size]"
            Clock.schedule_once(lambda dt: setattr(self.next_letter_label, 'text', next_text))
            
            word_html = f"[color=09A05B]{word.upper()}[/color]"
            Clock.schedule_once(lambda dt: setattr(self.current_word_display, 'text', word_html))
            Clock.schedule_once(lambda dt: setattr(self.word_by_user_label, 'text', f"Submitted by: [b]{uname}[/b]"))
            Clock.schedule_once(lambda dt: setattr(self.alert_label, 'text', ''))

        elif msg_type == "chat":
            p_id = str(data.get("player_id"))
            uname = data.get("username", "User")
            msg = data.get("message")
            Clock.schedule_once(lambda dt: self.display_player_chat(p_id, msg))
            Clock.schedule_once(lambda dt: self.append_chat_to_history_box(uname, msg))

        elif msg_type == "voice_message":
            p_id = str(data.get("player_id"))
            b64_audio = data.get("audio_data")
            # Avoid duplicate local trigger if it's our own voice message
            if p_id != str(self.player_id):
                self.play_voice_b64_async(p_id, b64_audio)

        elif msg_type == "reaction":
            p_id = str(data.get("player_id"))
            react = data.get("reaction")
            Clock.schedule_once(lambda dt: self.display_player_emoji(p_id, react))
            self.play_reaction_sound(react)

        elif msg_type == "error":
            err_msg = data.get("message")
            Clock.schedule_once(lambda dt: setattr(self.alert_label, 'text', f"⚠️ {err_msg}"))

    def sync_player_cards(self):
        self.players_container.clear_widgets()
        self.player_cards.clear()

        for p in self.players:
            pid = str(p["player_id"])
            card = PlayerCardWidget(
                player_id=pid,
                username=p["username"],
                avatar_url=p["avatar_url"],
                app_instance=self
            )
            
            if pid in self.active_chats:
                card.set_chat(self.active_chats[pid])

            self.player_cards[pid] = card
            self.players_container.add_widget(card)

        self.update_statuses()

    def update_statuses(self):
        active_online = [p for p in self.players if p.get("is_online")]

        for p in self.players:
            pid = str(p["player_id"])
            if pid not in self.player_cards:
                continue

            card = self.player_cards[pid]
            is_turn = (pid == str(self.current_turn_id))
            is_online = p.get("is_online", False)

            if not is_online:
                card.set_status("[color=FF0000][b]Offline[/b][/color]", bg_color=(1, 0.9, 0.9, 1), border_color=(0.9, 0.2, 0.2, 1))
            elif is_turn and len(active_online) >= 2:
                card.set_status("[color=009900][b]★ TURN[/b][/color]", bg_color=(1, 0.98, 0.8, 1), border_color=(1, 0.75, 0, 1))
            else:
                card.set_status("[color=888888]Online[/color]", bg_color=(1, 1, 1, 1), border_color=None)

        if len(active_online) >= 2:
            Clock.schedule_once(lambda dt: setattr(self.alert_label, 'text', ''))
            if self.next_letter_label.text == "WAITING FOR PLAYERS...":
                if self.all_game_words:
                    last_w = self.all_game_words[-1]
                    last_l = last_w[-1].upper()
                    Clock.schedule_once(lambda dt: setattr(self.next_letter_label, 'text', f"NEXT LETTER: [size=28][color=FF3D00]{last_l}[/color][/size]"))
                else:
                    Clock.schedule_once(lambda dt: setattr(self.next_letter_label, 'text', f"GAME STARTED! SUBMIT FIRST WORD"))
        else:
            Clock.schedule_once(lambda dt: setattr(self.alert_label, 'text', "⚠️ Need at least 2 players to play!"))
            Clock.schedule_once(lambda dt: setattr(self.next_letter_label, 'text', "WAITING FOR PLAYERS..."))

    def update_turn_ui(self):
        active_online = [p for p in self.players if p.get("is_online")]
        is_my_turn = (str(self.current_turn_id) == str(self.player_id)) and len(active_online) >= 2

        if is_my_turn:
            self.word_input.background_color = (0.9, 1, 0.9, 1)
            self.btn_send_word.set_bg((0.09, 0.63, 0.36, 1))
        else:
            self.word_input.background_color = (0.95, 0.96, 0.98, 1)
            self.btn_send_word.set_bg((0.6, 0.6, 0.6, 1))

    def send_word(self, instance):
        active_online = [p for p in self.players if p.get("is_online")]
        if len(active_online) < 2:
            self.alert_label.text = "⚠️ Cannot play alone! Waiting for 2nd player..."
            return

        word = self.word_input.text.strip()
        if not word:
            self.alert_label.text = "⚠️ Please type a word!"
            return

        if word and self.ws:
            payload = json.dumps({"type": "word", "text": word})
            self.ws.send(payload)
            self.word_input.text = ""

    def send_chat(self, instance):
        msg = self.chat_input.text.strip()
        if msg and self.ws:
            payload = json.dumps({"type": "chat", "text": msg})
            self.ws.send(payload)
            self.chat_input.text = ""

    def on_error(self, ws, error):
        Clock.schedule_once(lambda dt: setattr(self.alert_label, 'text', "Server Connection Error!"))

    def on_close(self, ws, close_status_code, close_msg):
        pass

if __name__ == "__main__":
    WordGameApp().run()