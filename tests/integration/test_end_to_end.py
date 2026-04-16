"""
End-to-end integration test for GLA.

Pipeline: mini_gl_app → LD_PRELOAD shim → engine → REST API → queries

Requirements:
- Built artifacts: libgla_gl.so, _gla_core.so, mini_gl_app
- X11 display (or Xvfb for headless)
- Python deps: requests, pytest

Run: PYTHONPATH=src/python:bazel-bin/src/bindings pytest tests/integration/test_end_to_end.py -v
"""
import subprocess
import time
import os
import sys
import signal
import pytest

# Paths to built artifacts (relative to repo root)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHIM_LIB = os.path.join(REPO_ROOT, "bazel-bin/src/shims/gl/libgla_gl.so")
GL_APP = os.path.join(REPO_ROOT, "bazel-bin/tests/integration/mini_gl_app")
SOCKET_PATH = f"/tmp/gla_test_{os.getpid()}.sock"
SHM_NAME = f"/gla_test_{os.getpid()}"
API_PORT = 18090 + (os.getpid() % 1000)  # avoid port conflicts
TOKEN = "e2e-test-token"
BASE_URL = f"http://127.0.0.1:{API_PORT}/api/v1"


@pytest.fixture(scope="module")
def gla_server():
    """Start GLA engine + API server."""
    import requests  # import here to fail fast if missing

    # Ensure artifacts exist
    assert os.path.exists(SHIM_LIB), f"Shim not built: {SHIM_LIB}"
    assert os.path.exists(GL_APP), f"GL app not built: {GL_APP}"

    # Start launcher
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{REPO_ROOT}/src/python:{REPO_ROOT}/bazel-bin/src/bindings"

    launcher = subprocess.Popen(
        [sys.executable, "-m", "gla.launcher",
         "--socket", SOCKET_PATH,
         "--shm", SHM_NAME,
         "--port", str(API_PORT),
         "--token", TOKEN],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready
    for _ in range(30):
        time.sleep(0.5)
        try:
            r = requests.get(f"{BASE_URL}/control/status",
                             headers={"Authorization": f"Bearer {TOKEN}"},
                             timeout=1)
            if r.status_code == 200:
                break
        except requests.ConnectionError:
            continue
    else:
        launcher.kill()
        stdout, stderr = launcher.communicate()
        pytest.fail(
            f"Server failed to start.\nstdout: {stdout.decode()}\nstderr: {stderr.decode()}"
        )

    yield launcher

    # Cleanup
    launcher.send_signal(signal.SIGTERM)
    try:
        launcher.wait(timeout=5)
    except subprocess.TimeoutExpired:
        launcher.kill()
    # Clean up socket file
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)


@pytest.fixture(scope="module")
def captured_frames(gla_server):
    """Run mini_gl_app with the shim and wait for capture."""
    env = os.environ.copy()
    env["LD_PRELOAD"] = SHIM_LIB
    env["GLA_SOCKET_PATH"] = SOCKET_PATH
    env["GLA_SHM_NAME"] = SHM_NAME

    # Need DISPLAY for GLX
    if "DISPLAY" not in env:
        pytest.skip("No DISPLAY set — need X11 or Xvfb")

    result = subprocess.run(
        [GL_APP],
        env=env,
        timeout=15,
        capture_output=True,
    )
    assert result.returncode == 0, (
        f"GL app failed (rc={result.returncode}):\n"
        f"stdout: {result.stdout.decode()}\n"
        f"stderr: {result.stderr.decode()}"
    )

    # Give engine time to process
    time.sleep(1)
    return True


def auth_headers():
    return {"Authorization": f"Bearer {TOKEN}"}


class TestFrameCapture:
    """Verify frames were captured from mini_gl_app."""

    def test_frame_overview(self, captured_frames):
        """Frame should be captured with correct viewport dimensions.

        Note: The M1/M2 shim captures framebuffer pixels only — draw call
        metadata serialization is not yet implemented in the shim. Therefore
        draw_call_count is expected to be 0 at this milestone.
        """
        import requests
        r = requests.get(f"{BASE_URL}/frames/current/overview", headers=auth_headers())
        assert r.status_code == 200, f"Unexpected status: {r.status_code}, body: {r.text}"
        data = r.json()
        # framebuffer dimensions must match the 400x300 viewport in mini_gl_app
        assert data["framebuffer_width"] == 400
        assert data["framebuffer_height"] == 300
        # draw_call_count: the shim does not serialize draw call metadata yet
        assert data["draw_call_count"] == 0  # TODO: update when shim serializes draw calls

    def test_draw_calls(self, captured_frames):
        """Draw call list endpoint returns 200 with an empty list.

        The shim captures framebuffer data only; draw call metadata is not
        yet serialized into the SHM frame. The endpoint must still return a
        valid (empty) response.
        """
        import requests
        # Get latest frame
        r = requests.get(f"{BASE_URL}/frames/current/overview", headers=auth_headers())
        assert r.status_code == 200
        frame_id = r.json()["frame_id"]

        # List draw calls — response uses "items" key (see routes_drawcalls.py)
        r = requests.get(f"{BASE_URL}/frames/{frame_id}/drawcalls", headers=auth_headers())
        assert r.status_code == 200, f"Unexpected status: {r.status_code}, body: {r.text}"
        data = r.json()
        # items is an empty list since draw call serialization is not yet done
        assert isinstance(data["items"], list)
        assert data["total"] == 0  # matches draw_call_count from overview

    def test_pixel_center_is_red(self, captured_frames):
        """Center of screen should be red (triangle)."""
        import requests
        r = requests.get(f"{BASE_URL}/frames/current/overview", headers=auth_headers())
        assert r.status_code == 200
        frame_id = r.json()["frame_id"]

        r = requests.get(
            f"{BASE_URL}/frames/{frame_id}/pixel/200/150", headers=auth_headers()
        )
        assert r.status_code == 200, f"Unexpected status: {r.status_code}, body: {r.text}"
        pixel = r.json()
        assert pixel["r"] == 255  # red
        assert pixel["g"] == 0
        assert pixel["b"] == 0

    def test_pixel_corner_is_blue(self, captured_frames):
        """Corner should be blue (background)."""
        import requests
        r = requests.get(f"{BASE_URL}/frames/current/overview", headers=auth_headers())
        assert r.status_code == 200
        frame_id = r.json()["frame_id"]

        r = requests.get(
            f"{BASE_URL}/frames/{frame_id}/pixel/0/0", headers=auth_headers()
        )
        assert r.status_code == 200, f"Unexpected status: {r.status_code}, body: {r.text}"
        pixel = r.json()
        assert pixel["r"] == 0
        assert pixel["g"] == 0
        assert pixel["b"] == 255  # blue


class TestAuth:
    """Verify auth middleware works."""

    def test_no_auth_returns_401(self, gla_server):
        import requests
        r = requests.get(f"{BASE_URL}/frames/current/overview")
        assert r.status_code == 401

    def test_wrong_token_returns_401(self, gla_server):
        import requests
        r = requests.get(
            f"{BASE_URL}/frames/current/overview",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert r.status_code == 401
