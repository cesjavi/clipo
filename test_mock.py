import unittest
from unittest.mock import MagicMock, patch
import sys

# Mock modules before importing window_context to simulate Windows environment
sys.modules['win32gui'] = MagicMock()
sys.modules['win32process'] = MagicMock()
sys.modules['pywinauto'] = MagicMock()
sys.modules['pywinauto.keyboard'] = MagicMock()
sys.modules['faster_whisper'] = MagicMock()
sys.modules['sounddevice'] = MagicMock()

# Now import the module to test
import window_context
import text_cleaner
import voice_input
import automation_commands

class TestWindowContext(unittest.TestCase):

    def setUp(self):
        # Reloading might be needed if side effects persist, but here it should be fine
        pass

    @patch('window_context.psutil')
    def test_get_active_window_info(self, mock_psutil):
        # We need to access the mocked modules that were imported into window_context
        # Since we mocked sys.modules, window_context.win32gui IS the mock we created
        # But we need to configure it.

        mock_win32gui = window_context.win32gui
        mock_win32process = window_context.win32process

        # Setup returns
        mock_win32gui.GetForegroundWindow.return_value = 12345
        mock_win32gui.GetWindowText.return_value = "Test Window"
        mock_win32process.GetWindowThreadProcessId.return_value = (0, 999)

        mock_process = MagicMock()
        mock_process.name.return_value = "notepad.exe"
        mock_psutil.Process.return_value = mock_process

        # Test
        info = window_context.get_active_window_info()

        self.assertIsNotNone(info)
        self.assertEqual(info['hwnd'], 12345)
        self.assertEqual(info['title'], "Test Window")
        self.assertEqual(info['pid'], 999)
        self.assertEqual(info['process_name'], "notepad.exe")

    def test_extract_text_uia(self):
        # Configure the mocked Application
        mock_Application = window_context.Application

        mock_app = MagicMock()
        mock_Application.return_value.connect.return_value = mock_app

        mock_window = MagicMock()
        mock_app.window.return_value = mock_window
        mock_wrapper = MagicMock()
        mock_window.wrapper_object.return_value = mock_wrapper

        # Create mock descendants
        child1 = MagicMock()
        child1.is_visible.return_value = True
        child1.window_text.return_value = "Hello"
        child1.legacy_properties.return_value = {}
        child1.friendly_class_name.return_value = "Button"

        child2 = MagicMock()
        child2.is_visible.return_value = True
        child2.window_text.return_value = "World"
        child2.legacy_properties.return_value = {'Value': 'World'}
        child2.friendly_class_name.return_value = "Edit"

        child3 = MagicMock() # Hidden
        child3.is_visible.return_value = False

        child4 = MagicMock() # Pane with no text
        child4.is_visible.return_value = True
        child4.window_text.return_value = "Pane"
        child4.friendly_class_name.return_value = "Pane"

        mock_wrapper.descendants.return_value = [child1, child2, child3, child4]

        # Test
        text = window_context.extract_text_uia(12345)

        self.assertIn("Hello", text)
        self.assertIn("World", text)
        self.assertNotIn("Pane", text) # Should be filtered

        lines = text.splitlines()
        self.assertEqual(len(lines), 2)

    def test_list_open_windows(self):
        mock_win32gui = window_context.win32gui
        mock_win32process = window_context.win32process

        # Configure EnumWindows to call the callback immediately with some mock hwnds
        def side_effect(callback, ctx):
            callback(100, ctx)
            callback(200, ctx)

        mock_win32gui.EnumWindows.side_effect = side_effect

        # Configure helper functions
        # Window 1: Visible, has title, has process
        mock_win32gui.IsWindowVisible.side_effect = lambda h: True
        mock_win32gui.GetWindowText.side_effect = lambda h: "Win 1" if h == 100 else "Win 2"
        mock_win32process.GetWindowThreadProcessId.return_value = (0, 999)

        # Test
        windows = window_context.list_open_windows()

        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0]['hwnd'], 100)
        self.assertEqual(windows[0]['title'], "Win 1")
        self.assertEqual(windows[1]['hwnd'], 200)

    def test_send_command_to_window(self):
        mock_Application = window_context.Application
        mock_send_keys = window_context.send_keys
        mock_Application.reset_mock()
        mock_send_keys.reset_mock()

        mock_app = MagicMock()
        mock_window = MagicMock()
        mock_Application.return_value.connect.return_value = mock_app
        mock_app.window.return_value = mock_window

        sent = window_context.send_command_to_window(12345, "dir", press_enter=True)

        self.assertEqual(sent, "dir")
        mock_Application.return_value.connect.assert_called_once_with(handle=12345, timeout=5)
        mock_app.window.assert_called_once_with(handle=12345)
        mock_window.set_focus.assert_called_once()
        mock_send_keys.assert_any_call("dir", with_spaces=True, pause=0.01)
        mock_send_keys.assert_any_call("{ENTER}", pause=0.01)

    def test_send_keys_to_window(self):
        mock_send_keys = window_context.send_keys
        mock_send_keys.reset_mock()

        sent = window_context.send_keys_to_window("^w")

        self.assertEqual(sent, "^w")
        mock_send_keys.assert_called_once_with("^w", pause=0.01)

    def test_send_text_to_window(self):
        mock_send_keys = window_context.send_keys
        mock_send_keys.reset_mock()

        sent = window_context.send_text_to_window("hola")

        self.assertEqual(sent, "hola")
        mock_send_keys.assert_called_once_with("hola", with_spaces=True, pause=0.01)


class TestVoiceInput(unittest.TestCase):
    def test_recognize_once(self):
        mock_sd = voice_input.sd
        mock_model_class = voice_input.WhisperModel

        mock_sd.reset_mock()
        mock_model_class.reset_mock()
        voice_input._MODEL = None

        mock_sd.rec.return_value = voice_input.np.array([[0.1], [0.2], [0.1]], dtype="float32")

        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "abrir bloc de notas"
        mock_model.transcribe.return_value = ([mock_segment], MagicMock())
        mock_model_class.return_value = mock_model

        text = voice_input.recognize_once(timeout_seconds=1)

        self.assertEqual(text, "abrir bloc de notas")
        mock_sd.rec.assert_called_once()
        mock_sd.wait.assert_called_once()
        mock_model_class.assert_called_once_with("tiny", compute_type="int8")
        mock_model.transcribe.assert_called_once()


class TestAutomationCommands(unittest.TestCase):
    def test_parse_browser_tab_next(self):
        window_info = {"process_name": "chrome.exe", "title": "Docs"}

        parsed = automation_commands.parse_command("tab siguiente", window_info)

        self.assertEqual(parsed["type"], "shortcut")
        self.assertEqual(parsed["keys"], "^{TAB}")

    def test_parse_youtube_pause(self):
        window_info = {"process_name": "chrome.exe", "title": "YouTube - video"}

        parsed = automation_commands.parse_command("youtube pause", window_info)

        self.assertEqual(parsed["type"], "shortcut")
        self.assertEqual(parsed["keys"], "k")

    def test_parse_youtube_next_song(self):
        window_info = {"process_name": "chrome.exe", "title": "YouTube - mix"}

        parsed = automation_commands.parse_command("siguiente canción", window_info)

        self.assertEqual(parsed["type"], "shortcut")
        self.assertEqual(parsed["keys"], "n")

    def test_parse_message_for_whatsapp(self):
        window_info = {"process_name": "WhatsApp.exe", "title": "WhatsApp"}

        parsed = automation_commands.parse_command("mensaje hola equipo", window_info)

        self.assertEqual(parsed["type"], "text")
        self.assertEqual(parsed["text"], "hola equipo")
        self.assertTrue(parsed["press_enter"])

    def test_parse_message_for_discord(self):
        window_info = {"process_name": "Discord.exe", "title": "Discord"}

        parsed = automation_commands.parse_command("discord hola canal", window_info)

        self.assertEqual(parsed["type"], "text")
        self.assertEqual(parsed["text"], "hola canal")

    def test_parse_spotify_next_song(self):
        window_info = {"process_name": "spotify.exe", "title": "Spotify"}

        parsed = automation_commands.parse_command("siguiente canción", window_info)

        self.assertEqual(parsed["type"], "shortcut")
        self.assertEqual(parsed["keys"], "^{RIGHT}")

    def test_parse_teams_mute(self):
        window_info = {"process_name": "teams.exe", "title": "Teams"}

        parsed = automation_commands.parse_command("silenciar", window_info)

        self.assertEqual(parsed["type"], "shortcut")
        self.assertEqual(parsed["keys"], "^+m")

    def test_parse_switch_to_browser(self):
        window_info = {"process_name": "notepad.exe", "title": "Notas"}
        available = [
            {"hwnd": 10, "process_name": "chrome.exe", "title": "Gmail - Chrome"},
            {"hwnd": 20, "process_name": "discord.exe", "title": "Discord"},
        ]

        parsed = automation_commands.parse_command("cambiar a navegador", window_info, available)

        self.assertEqual(parsed["type"], "switch_window")
        self.assertEqual(parsed["target_hwnd"], 10)

    def test_parse_tab_by_number(self):
        window_info = {"process_name": "chrome.exe", "title": "Docs"}

        parsed = automation_commands.parse_command("pestaña 3", window_info)

        self.assertEqual(parsed["type"], "shortcut")
        self.assertEqual(parsed["keys"], "^3")

    def test_parse_tab_by_name_in_chromium(self):
        window_info = {"process_name": "chrome.exe", "title": "Docs"}

        parsed = automation_commands.parse_command("pestaña sofia", window_info)

        self.assertEqual(parsed["type"], "search_target")
        self.assertEqual(parsed["search_keys"], "^+a")
        self.assertEqual(parsed["target"], "sofia")

    def test_parse_chat_by_name_in_teams(self):
        window_info = {"process_name": "teams.exe", "title": "Teams"}

        parsed = automation_commands.parse_command("pestaña sofia", window_info)

        self.assertEqual(parsed["type"], "search_target")
        self.assertEqual(parsed["search_keys"], "^e")
        self.assertEqual(parsed["target"], "sofia")

    def test_parse_direct_message_to_contact(self):
        window_info = {"process_name": "discord.exe", "title": "Discord"}

        parsed = automation_commands.parse_command("mensaje a sofia hola como va", window_info)

        self.assertEqual(parsed["type"], "search_and_send")
        self.assertEqual(parsed["search_keys"], "^k")
        self.assertEqual(parsed["target"], "sofia")
        self.assertEqual(parsed["text"], "hola como va")

    def test_parse_write_to_specific_chat(self):
        window_info = {"process_name": "teams.exe", "title": "Teams"}

        parsed = automation_commands.parse_command(
            "escribir en el chat de Alfonso Nesprias lo siguiente hola coma como va",
            window_info,
        )

        self.assertEqual(parsed["type"], "search_and_send")
        self.assertEqual(parsed["search_keys"], "^e")
        self.assertEqual(parsed["target"], "alfonso nesprias")
        self.assertEqual(parsed["text"], "hola, como va")

    def test_parse_write_to_current_chat(self):
        window_info = {"process_name": "teams.exe", "title": "Teams"}

        parsed = automation_commands.parse_command(
            "escribir en el chat lo siguiente prueba dos puntos ok",
            window_info,
        )

        self.assertEqual(parsed["type"], "text")
        self.assertEqual(parsed["text"], "prueba: ok")

    def test_execute_parsed_command_for_message(self):
        automation = {
            "focus": MagicMock(),
            "send_keys": MagicMock(),
            "send_text": MagicMock(),
            "switch_window": MagicMock(),
            "wait": MagicMock(),
        }
        window_info = {"hwnd": 55, "process_name": "teams.exe", "title": "Teams"}
        parsed = {"type": "text", "text": "hola", "press_enter": True, "description": "Mensaje: hola"}

        description = automation_commands.execute_parsed_command(window_info, parsed, automation)

        self.assertEqual(description, "Mensaje: hola")
        automation["focus"].assert_called_once_with(55)
        automation["send_text"].assert_called_once_with("hola")
        automation["send_keys"].assert_called_once_with("{ENTER}")

    def test_execute_switch_window(self):
        automation = {
            "focus": MagicMock(),
            "send_keys": MagicMock(),
            "send_text": MagicMock(),
            "switch_window": MagicMock(),
            "wait": MagicMock(),
        }
        window_info = {"hwnd": 55, "process_name": "teams.exe", "title": "Teams"}
        parsed = {"type": "switch_window", "target_hwnd": 99, "description": "Cambiar a Gmail - Chrome"}

        description = automation_commands.execute_parsed_command(window_info, parsed, automation)

        self.assertEqual(description, "Cambiar a Gmail - Chrome")
        automation["switch_window"].assert_called_once_with(99)
        automation["focus"].assert_not_called()

    def test_execute_search_target(self):
        automation = {
            "focus": MagicMock(),
            "send_keys": MagicMock(),
            "send_text": MagicMock(),
            "switch_window": MagicMock(),
            "wait": MagicMock(),
        }
        window_info = {"hwnd": 77, "process_name": "chrome.exe", "title": "Chrome"}
        parsed = {"type": "search_target", "search_keys": "^+a", "target": "sofia", "description": "Buscar pestaña sofia"}

        description = automation_commands.execute_parsed_command(window_info, parsed, automation)

        self.assertEqual(description, "Buscar pestaña sofia")
        automation["focus"].assert_called_once_with(77)
        automation["send_keys"].assert_any_call("^+a")
        automation["send_keys"].assert_any_call("{ENTER}")
        automation["send_text"].assert_called_once_with("sofia")

    def test_execute_search_and_send(self):
        automation = {
            "focus": MagicMock(),
            "send_keys": MagicMock(),
            "send_text": MagicMock(),
            "switch_window": MagicMock(),
            "wait": MagicMock(),
        }
        window_info = {"hwnd": 88, "process_name": "discord.exe", "title": "Discord"}
        parsed = {
            "type": "search_and_send",
            "search_keys": "^k",
            "target": "sofia",
            "text": "hola",
            "description": "Abrir sofia y enviar mensaje",
        }

        description = automation_commands.execute_parsed_command(window_info, parsed, automation)

        self.assertEqual(description, "Abrir sofia y enviar mensaje")
        automation["focus"].assert_called_once_with(88)
        self.assertEqual(automation["send_text"].call_count, 2)
        automation["send_text"].assert_any_call("sofia")
        automation["send_text"].assert_any_call("hola")

class TestTextCleaner(unittest.TestCase):
    def test_build_context(self):
        window_info = {
            "process_name": "notepad.exe",
            "title": "Test Window",
            "pid": 999
        }
        raw_text = "Hello\n   \nWorld\nDuplicate\nDuplicate\n!"

        context = text_cleaner.build_context(window_info, raw_text)

        self.assertIn("Process: notepad.exe", context)
        self.assertIn("Title: Test Window", context)
        self.assertIn("Hello", context)
        self.assertIn("World", context)

        # "Duplicate" should appear only once
        self.assertEqual(context.count("Duplicate"), 1)

        # "!" (single symbol) should be removed by heuristic
        # We need to verify that it is NOT in the cleaned text lines
        # But "-" is in the header, which is a symbol.
        # Heuristic checks each line.

        cleaned_part = context.split("-" * 50)[1]
        self.assertNotIn("!", cleaned_part)

        # Check if header separator exists
        self.assertIn("-" * 50, context)

if __name__ == '__main__':
    unittest.main()
