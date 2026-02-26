import unittest
from unittest.mock import MagicMock, patch
import sys

# Mock modules before importing window_context to simulate Windows environment
sys.modules['win32gui'] = MagicMock()
sys.modules['win32process'] = MagicMock()
sys.modules['pywinauto'] = MagicMock()

# Now import the module to test
import window_context
import text_cleaner

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
