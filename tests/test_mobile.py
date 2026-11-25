import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
FIRST_RESPONSE = "I walk after lunch to clear my head."
RETRY_RESPONSE = "A short walk after lunch helps me build momentum for the afternoon."


def start_server(data_dir, port, log):
    return subprocess.Popen(
        [sys.executable, str(ROOT / "tests/mobile_server.py"), "--port", str(port)],
        cwd=ROOT,
        env={
            **os.environ,
            "SPEAK_DATA_DIR": str(data_dir),
            "SPEAK_LOCAL_DATA_DIR": str(data_dir),
            "SPEAK_USER": "local",
        },
        stdout=log,
        stderr=subprocess.STDOUT,
    )


class MobileSpeakTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        playwright = cls.enterClassContext(sync_playwright())
        cls.browser = playwright.chromium.launch(
            executable_path=os.environ.get("SPEAK_E2E_CHROMIUM"),
            args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
        )
        cls.addClassCleanup(cls.browser.close)
        cls.device = playwright.devices["iPhone 13"].copy()
        cls.device.pop("default_browser_type", None)

    def setUp(self):
        temporary = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.context = self.browser.new_context(**self.device, permissions=["microphone"])
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.page.set_default_timeout(5_000)

        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        log_path = temporary / "server.log"
        with log_path.open("wb") as log:
            self.server = start_server(temporary / "data", port, log)
        self.addCleanup(self.stop_server)
        self.origin = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline and self.server.poll() is None:
            try:
                with urlopen(self.origin, timeout=0.25):
                    break
            except (URLError, TimeoutError):
                time.sleep(0.05)
        else:
            self.fail(f"Speak did not start.\n{log_path.read_text()}")
        self.page.goto(self.origin)

    def stop_server(self):
        self.server.terminate()
        try:
            self.server.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.server.kill()
            self.server.wait(timeout=3)

    def button(self, name):
        return self.page.get_by_role("button", name=name, exact=True)

    def type_response(self, response):
        field = self.page.get_by_role("textbox", name="Your response")
        if not field.is_visible():
            self.button("Type response").click()
        field.fill(response)
        self.button("Save and get feedback").click()

    def expect_audio(self, button, kind):
        with self.page.expect_response(
            lambda response: "/api/audio?" in response.url and f"kind={kind}" in response.url
        ) as requested:
            self.button(button).click()
        response = requested.value
        self.assertIn(response.status, [200, 206])
        self.assertTrue(response.headers.get("content-type", "").startswith("audio/"))
        self.page.wait_for_function(
            "selector => document.querySelector(selector)?.duration > 0",
            arg=f'audio[aria-label="{button}"]',
        )

    def test_english_mission_typed_feedback_retry_and_history(self):
        expect(self.page.get_by_role("heading", name="Speak", exact=True)).to_be_visible()
        expect(self.page.get_by_text("Describe a small habit you have kept.")).to_be_visible()
        expect(self.page.get_by_text("build momentum", exact=True)).to_be_visible()
        self.assertTrue(self.page.evaluate("document.documentElement.scrollWidth <= innerWidth"))

        self.type_response(FIRST_RESPONSE)
        expect(self.page.get_by_role("heading", name="Round 1 feedback")).to_be_visible()
        expect(self.page.get_by_text("I take a quick walk after lunch to reset my focus.")).to_be_visible()
        self.button("Retry round").click()
        self.type_response(RETRY_RESPONSE)
        expect(self.page.get_by_role("heading", name="Round 2 feedback")).to_be_visible()
        expect(self.page.get_by_text("You carried the first round into a stronger retry.")).to_be_visible()

        self.page.reload()
        self.button("History").click()
        self.page.get_by_role("button", name="Round 1", exact=False).click()
        expect(self.page.get_by_text(FIRST_RESPONSE, exact=True)).to_be_visible()
        self.page.get_by_role("button", name="Round 2", exact=False).click()
        expect(self.page.get_by_text(RETRY_RESPONSE, exact=True)).to_be_visible()

    def test_japanese_model_and_polished_audio(self):
        self.button("Japanese").click()
        expect(self.page.get_by_text("What do you do in the morning?")).to_be_visible()
        self.expect_audio("Play model", "model")

        self.type_response("朝はコーヒーを飲みます。")
        expect(self.page.get_by_text("The particle を fits here.")).to_be_visible()
        self.expect_audio("Play polished version", "polished")

    def test_microphone_recording_upload_and_transcript(self):
        self.button("Record").click()
        stop = self.button("Stop and save")
        expect(stop).to_be_enabled()
        # The service rejects recordings under its minimum speaking time.
        self.page.wait_for_timeout(2_000)
        stop.click()
        expect(self.page.get_by_text("The microphone recording reached the coach.", exact=True)).to_be_visible()
        expect(self.page.get_by_text("Practice saved to your history.")).to_be_visible()
        self.expect_audio("Play your recording", "recording")

        self.page.reload()
        self.button("History").click()
        self.page.get_by_role("button", name="Round 1", exact=False).click()
        expect(self.page.get_by_text("The microphone recording reached the coach.", exact=True)).to_be_visible()

    def test_recording_is_retained_when_save_fails(self):
        self.page.route("**/api/review?*", lambda route: route.fulfill(
            status=503, json={"error": "Transcription is temporarily unavailable."},
        ), times=1)
        self.button("Record").click()
        self.page.wait_for_timeout(2_000)
        self.button("Stop and save").click()

        expect(self.page.get_by_role("status").filter(
            has_text="Transcription is temporarily unavailable."),
        ).to_be_visible()
        expect(self.page.get_by_label("Preview your recording")).to_be_visible()
        self.button("Save and get feedback").click()
        expect(self.page.get_by_text("Practice saved to your history.")).to_be_visible()
