import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import time
import json
import urllib.request
from pathlib import Path

from PySide6.QtGui import QImage


class StreamingManager:
	def __init__(self) -> None:
		self.server_process: subprocess.Popen | None = None
		self.ffmpeg_process: subprocess.Popen | None = None
		self.bin_dir = Path(__file__).resolve().parent / "bin"
		self.bin_dir.mkdir(parents=True, exist_ok=True)
		self.mediamtx_path = self.bin_dir / "mediamtx"
		self.publish_url = "rtmp://127.0.0.1/live/stream"

	def get_rtmp_publish_url(self) -> str:
		return self.publish_url

	def start_server(self) -> None:
		if self.server_process is not None and self.server_process.poll() is None:
			return
		if not self.mediamtx_path.exists():
			self._download_mediamtx()
		# 启动 MediaMTX 默认配置
		self.server_process = subprocess.Popen(
			[str(self.mediamtx_path)],
			stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT,
		)
		# 简单等待端口就绪
		self._wait_for_rtmp_ready(timeout_seconds=5)

	def stop_server(self) -> None:
		if self.server_process is not None:
			try:
				self.server_process.terminate()
				self.server_process.wait(timeout=3)
			except Exception:
				try:
					self.server_process.kill()
				except Exception:
					pass
			finally:
				self.server_process = None

	def start_stream(self, width: int, height: int, fps: int) -> bool:
		if self.ffmpeg_process is not None and self.ffmpeg_process.poll() is None:
			return True
		ffmpeg_path = shutil.which("ffmpeg")
		if ffmpeg_path is None:
			return False
		cmd = [
			ffmpeg_path,
			"-y",
			"-f",
			"rawvideo",
			"-pixel_format",
			"rgb24",
			"-video_size",
			f"{width}x{height}",
			"-framerate",
			str(fps),
			"-i",
			"-",
			"-an",
			"-c:v",
			"libx264",
			"-preset",
			"veryfast",
			"-tune",
			"zerolatency",
			"-pix_fmt",
			"yuv420p",
			"-f",
			"flv",
			self.publish_url,
		]
		self.ffmpeg_process = subprocess.Popen(
			cmd,
			stdin=subprocess.PIPE,
			stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT,
			bufsize=0,
		)
		return True

	def stop_stream(self) -> None:
		if self.ffmpeg_process is not None:
			try:
				if self.ffmpeg_process.stdin:
					self.ffmpeg_process.stdin.close()
				self.ffmpeg_process.terminate()
				self.ffmpeg_process.wait(timeout=3)
			except Exception:
				try:
					self.ffmpeg_process.kill()
				except Exception:
					pass
			finally:
				self.ffmpeg_process = None

	def write_frame(self, image: QImage) -> None:
		if self.ffmpeg_process is None or self.ffmpeg_process.poll() is not None:
			return
		img = image
		if img.format() != QImage.Format_RGB888:
			img = img.convertToFormat(QImage.Format_RGB888)
		ptr = img.bits()
		ptr.setsize(img.byteCount())
		data = bytes(ptr)
		try:
			if self.ffmpeg_process.stdin:
				self.ffmpeg_process.stdin.write(data)
		except BrokenPipeError:
			self.stop_stream()

	def _wait_for_rtmp_ready(self, timeout_seconds: int = 5) -> None:
		# 简单等待几百毫秒让进程启动
		start = time.time()
		while time.time() - start < timeout_seconds:
			time.sleep(0.2)
			if self.server_process is None or self.server_process.poll() is not None:
				raise RuntimeError("RTMP 服务启动失败")
		return

	def _download_mediamtx(self) -> None:
		machine = platform.machine().lower()
		arch = "amd64"
		if machine in {"x86_64", "amd64"}:
			arch = "amd64"
		elif machine in {"aarch64", "arm64"}:
			arch = "arm64"
		else:
			raise RuntimeError(f"暂不支持当前架构: {machine}")

		# 通过 GitHub API 获取 latest 版本的正确资产名
		api_url = "https://api.github.com/repos/bluenviron/mediamtx/releases/latest"
		with urllib.request.urlopen(api_url) as resp:
			release = json.loads(resp.read().decode("utf-8"))
		assets = release.get("assets", [])
		asset_url = None
		for asset in assets:
			name = asset.get("name", "")
			if name.endswith(f"linux_{arch}.tar.gz"):
				asset_url = asset.get("browser_download_url")
				break
		if not asset_url:
			raise RuntimeError("未找到适配架构的 MediaMTX 发行包")

		tmp_dir = tempfile.mkdtemp()
		archive_path = Path(tmp_dir) / "mediamtx.tar.gz"
		try:
			urllib.request.urlretrieve(asset_url, archive_path)
			with tarfile.open(archive_path, "r:gz") as tar:
				tar.extractall(path=self.bin_dir)
			# 提取后目录内包含 mediamtx 可执行文件
			candidate = None
			for p in self.bin_dir.rglob("mediamtx"):
				if p.is_file() and os.access(p, os.X_OK):
					candidate = p
					break
			if candidate is None:
				raise RuntimeError("解压后未找到 mediamtx 可执行文件")
			shutil.move(str(candidate), str(self.mediamtx_path))
			self.mediamtx_path.chmod(0o755)
		finally:
			shutil.rmtree(tmp_dir, ignore_errors=True)

