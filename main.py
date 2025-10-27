import os
import sys
import random
import time
from dataclasses import dataclass

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QImage, QPainter, QPixmap, QAction
from PySide6.QtWidgets import (
	QApplication,
	QMainWindow,
	QWidget,
	QVBoxLayout,
	QHBoxLayout,
	QPushButton,
	QComboBox,
	QFileDialog,
	QListWidget,
	QLabel,
	QMessageBox,
	QStatusBar,
)

from streaming import StreamingManager


CANVAS_WIDTH = 1280
CANVAS_HEIGHT = 720
TARGET_FPS = 30


@dataclass
class Pig:
	pixmap: QPixmap
	x: float
	y: float
	velocity_x: float
	velocity_y: float
	width: int
	height: int

	def update_position(self, delta_seconds: float) -> None:
		self.x += self.velocity_x * delta_seconds
		self.y += self.velocity_y * delta_seconds


class CanvasWidget(QWidget):
	def __init__(self, parent=None) -> None:
		super().__init__(parent)
		self.setMinimumSize(QSize(CANVAS_WIDTH, CANVAS_HEIGHT))
		self.setMaximumSize(QSize(CANVAS_WIDTH, CANVAS_HEIGHT))
		self.setFixedSize(QSize(CANVAS_WIDTH, CANVAS_HEIGHT))

		self.background_pixmap: QPixmap | None = None
		self.scaled_background: QPixmap | None = None
		self.pig_pixmaps: list[QPixmap] = []
		self.pigs: list[Pig] = []

		self.direction: str = "左到右"  # 默认方向
		self.spawning_enabled: bool = False

		self.last_frame_image: QImage | None = None

		self.last_update_time = time.time()
		self.render_timer = QTimer(self)
		self.render_timer.timeout.connect(self._on_render)
		self.render_timer.start(int(1000 / TARGET_FPS))

		self.spawn_timer = QTimer(self)
		self.spawn_timer.timeout.connect(self._spawn_random_pig)
		self._schedule_next_spawn()

	def set_background_image(self, path: str) -> None:
		pm = QPixmap(path)
		if pm.isNull():
			raise ValueError("无法加载背景图像")
		self.background_pixmap = pm
		self._rescale_background()
		self.update()

	def add_pig_sprite(self, path: str) -> None:
		pm = QPixmap(path)
		if pm.isNull():
			raise ValueError("无法加载猪只贴图")
		self.pig_pixmaps.append(pm)

	def clear_pigs(self) -> None:
		self.pigs.clear()
		self.update()

	def set_direction(self, direction: str) -> None:
		self.direction = direction

	def set_spawning(self, enabled: bool) -> None:
		self.spawning_enabled = enabled
		if enabled:
			self._schedule_next_spawn()

	def _schedule_next_spawn(self) -> None:
		if not self.spawning_enabled:
			self.spawn_timer.stop()
			return
		interval_ms = random.randint(500, 1200)
		self.spawn_timer.start(interval_ms)

	def _spawn_random_pig(self) -> None:
		if not self.spawning_enabled:
			return
		if not self.pig_pixmaps:
			return

		# 选择贴图
		base_pm = random.choice(self.pig_pixmaps)
		# 可选随机缩放：保持清晰
		scale_factor = random.uniform(0.6, 1.2)
		w = max(16, int(base_pm.width() * scale_factor))
		h = max(16, int(base_pm.height() * scale_factor))
		pm = base_pm.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

		# 速度：像素/秒
		speed_px_per_s = random.uniform(120.0, 320.0)
		vx, vy = 0.0, 0.0
		x, y = 0.0, 0.0

		if self.direction == "上到下":
			vx, vy = 0.0, speed_px_per_s
			x = random.uniform(0, CANVAS_WIDTH - pm.width())
			y = -pm.height() - 4
		elif self.direction == "下到上":
			vx, vy = 0.0, -speed_px_per_s
			x = random.uniform(0, CANVAS_WIDTH - pm.width())
			y = CANVAS_HEIGHT + 4
		elif self.direction == "左到右":
			vx, vy = speed_px_per_s, 0.0
			x = -pm.width() - 4
			y = random.uniform(0, CANVAS_HEIGHT - pm.height())
		elif self.direction == "右到左":
			vx, vy = -speed_px_per_s, 0.0
			x = CANVAS_WIDTH + 4
			y = random.uniform(0, CANVAS_HEIGHT - pm.height())
		else:
			vx, vy = speed_px_per_s, 0.0
			x = -pm.width() - 4
			y = random.uniform(0, CANVAS_HEIGHT - pm.height())

		pig = Pig(pixmap=pm, x=x, y=y, velocity_x=vx, velocity_y=vy, width=pm.width(), height=pm.height())
		self.pigs.append(pig)
		self._schedule_next_spawn()

	def _rescale_background(self) -> None:
		if self.background_pixmap is None:
			self.scaled_background = None
			return
		self.scaled_background = self.background_pixmap.scaled(
			CANVAS_WIDTH,
			CANVAS_HEIGHT,
			Qt.KeepAspectRatioByExpanding,
			Qt.SmoothTransformation,
		)

	def resizeEvent(self, event) -> None:  # noqa: N802
		self._rescale_background()
		super().resizeEvent(event)

	def _on_render(self) -> None:
		now = time.time()
		delta = now - self.last_update_time
		self.last_update_time = now

		# 更新位置
		if delta > 0:
			for pig in list(self.pigs):
				pig.update_position(delta)

		# 移除超出边界的
			self._remove_offscreen_pigs()

		# 生成帧图像
		frame = QImage(CANVAS_WIDTH, CANVAS_HEIGHT, QImage.Format_RGB888)
		painter = QPainter(frame)
		painter.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT, Qt.black)
		if self.scaled_background is not None and not self.scaled_background.isNull():
			# 居中绘制裁剪后的背景
			bg = self.scaled_background
			x = (CANVAS_WIDTH - bg.width()) // 2
			y = (CANVAS_HEIGHT - bg.height()) // 2
			painter.drawPixmap(x, y, bg)
		# 画猪
		for pig in self.pigs:
			painter.drawPixmap(int(pig.x), int(pig.y), pig.width, pig.height, pig.pixmap)
		painter.end()

		self.last_frame_image = frame
		self.update()

	def _remove_offscreen_pigs(self) -> None:
		margin = 40
		kept: list[Pig] = []
		for pig in self.pigs:
			if (
				pig.x + pig.width < -margin
				or pig.x > CANVAS_WIDTH + margin
				or pig.y + pig.height < -margin
				or pig.y > CANVAS_HEIGHT + margin
			):
				continue
			kept.append(pig)
		self.pigs = kept

	def paintEvent(self, event) -> None:  # noqa: N802
		painter = QPainter(self)
		if self.last_frame_image is not None:
			painter.drawImage(0, 0, self.last_frame_image)
		else:
			painter.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT, Qt.black)
		painter.end()


class MainWindow(QMainWindow):
	def __init__(self) -> None:
		super().__init__()
		self.setWindowTitle("通道猪只点数视频生成器")
		self.canvas = CanvasWidget(self)

		# 控件
		self.btn_bg = QPushButton("上传背景图")
		self.btn_sprite = QPushButton("上传猪贴图(可多选)")
		self.btn_clear = QPushButton("清空猪只")
		self.combo_dir = QComboBox()
		self.combo_dir.addItems(["上到下", "下到上", "左到右", "右到左"])
		self.combo_dir.setCurrentText("左到右")
		self.btn_spawn_toggle = QPushButton("开始出猪")
		self.btn_stream_toggle = QPushButton("开启推送")
		self.sprite_list = QListWidget()
		self.label_url = QLabel("RTMP: rtmp://127.0.0.1/live/stream")

		# 布局
		controls_top = QHBoxLayout()
		controls_top.addWidget(self.btn_bg)
		controls_top.addWidget(self.btn_sprite)
		controls_top.addWidget(self.btn_clear)
		controls_top.addStretch(1)

		controls_mid = QHBoxLayout()
		controls_mid.addWidget(QLabel("方向:"))
		controls_mid.addWidget(self.combo_dir)
		controls_mid.addStretch(1)
		controls_mid.addWidget(self.btn_spawn_toggle)
		controls_mid.addWidget(self.btn_stream_toggle)

		right_panel = QVBoxLayout()
		right_panel.addWidget(QLabel("已加载贴图:"))
		right_panel.addWidget(self.sprite_list)
		right_panel.addWidget(self.label_url)

		main_layout = QHBoxLayout()
		left_col = QVBoxLayout()
		left_col.addLayout(controls_top)
		left_col.addWidget(self.canvas)
		left_col.addLayout(controls_mid)
		main_layout.addLayout(left_col, 3)
		main_layout.addLayout(right_panel, 1)

		central = QWidget()
		central.setLayout(main_layout)
		self.setCentralWidget(central)
		self.setStatusBar(QStatusBar(self))

		# 事件
		self.btn_bg.clicked.connect(self._on_choose_bg)
		self.btn_sprite.clicked.connect(self._on_choose_sprites)
		self.btn_clear.clicked.connect(self.canvas.clear_pigs)
		self.combo_dir.currentTextChanged.connect(self.canvas.set_direction)
		self.btn_spawn_toggle.clicked.connect(self._toggle_spawn)
		self.btn_stream_toggle.clicked.connect(self._toggle_streaming)

		# 推流管理
		self.streaming_manager = StreamingManager()
		self.streaming_enabled = False

		# 将渲染帧定时送入推流
		self.stream_timer = QTimer(self)
		self.stream_timer.timeout.connect(self._on_stream_tick)

		# 菜单快捷
		self._build_menu()

	def _build_menu(self) -> None:
		file_menu = self.menuBar().addMenu("文件")
		action_quit = QAction("退出", self)
		action_quit.triggered.connect(self.close)
		file_menu.addAction(action_quit)

	def _on_choose_bg(self) -> None:
		path, _ = QFileDialog.getOpenFileName(self, "选择背景图", os.getcwd(), "Images (*.png *.jpg *.jpeg *.bmp)")
		if not path:
			return
		try:
			self.canvas.set_background_image(path)
			self.statusBar().showMessage(f"已设置背景: {os.path.basename(path)}", 3000)
		except Exception as exc:  # noqa: BLE001
			QMessageBox.critical(self, "错误", f"加载背景失败: {exc}")

	def _on_choose_sprites(self) -> None:
		paths, _ = QFileDialog.getOpenFileNames(self, "选择猪贴图(可多选)", os.getcwd(), "Images (*.png *.jpg *.jpeg *.bmp)")
		if not paths:
			return
		added = 0
		for p in paths:
			try:
				self.canvas.add_pig_sprite(p)
				self.sprite_list.addItem(os.path.basename(p))
				added += 1
			except Exception:
				pass
		self.statusBar().showMessage(f"已添加贴图 {added} 张", 3000)

	def _toggle_spawn(self) -> None:
		enabled = not self.canvas.spawning_enabled
		self.canvas.set_spawning(enabled)
		self.btn_spawn_toggle.setText("停止出猪" if enabled else "开始出猪")
		self.statusBar().showMessage("开始出猪" if enabled else "停止出猪", 2000)

	def _toggle_streaming(self) -> None:
		if not self.streaming_enabled:
			# 启动 RTMP 服务 与 ffmpeg 推流
			try:
				self.streaming_manager.start_server()
				rtmp_url = self.streaming_manager.get_rtmp_publish_url()
				self.label_url.setText(f"RTMP: {rtmp_url}")
				success = self.streaming_manager.start_stream(
					width=CANVAS_WIDTH,
					height=CANVAS_HEIGHT,
					fps=TARGET_FPS,
				)
				if not success:
					QMessageBox.critical(self, "错误", "启动推流失败，请检查 ffmpeg 是否安装")
					return
				self.streaming_enabled = True
				self.btn_stream_toggle.setText("停止推送")
				self.stream_timer.start(int(1000 / TARGET_FPS))
				self.statusBar().showMessage("推流已启动", 3000)
			except Exception as exc:  # noqa: BLE001
				QMessageBox.critical(self, "错误", f"启动 RTMP 服务失败: {exc}")
				return
		else:
			self.stream_timer.stop()
			self.streaming_manager.stop_stream()
			self.streaming_manager.stop_server()
			self.streaming_enabled = False
			self.btn_stream_toggle.setText("开启推送")
			self.statusBar().showMessage("推流已停止", 3000)

	def _on_stream_tick(self) -> None:
		if not self.streaming_enabled:
			return
		frame = self.canvas.last_frame_image
		if frame is None:
			return
		self.streaming_manager.write_frame(frame)

	def closeEvent(self, event) -> None:  # noqa: N802
		# 清理进程
		try:
			self.stream_timer.stop()
			self.canvas.set_spawning(False)
			self.streaming_manager.stop_stream()
			self.streaming_manager.stop_server()
		except Exception:
			pass
		return super().closeEvent(event)


def main() -> None:
	app = QApplication(sys.argv)
	window = MainWindow()
	window.show()
	sys.exit(app.exec())


if __name__ == "__main__":
	main()

