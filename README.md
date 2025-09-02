## 通道猪只点数测试视频流 GUI

功能：

- 背景图片上传作为画布背景
- 多张猪只贴图上传，随机生成并按方向移动
- 方向配置：上到下、下到上、左到右、右到左
- 本地启动 RTMP 服务（MediaMTX）并通过 ffmpeg 推送实时视频

### 运行

1) 安装依赖：

```bash
pip install -r requirements.txt
```

2) 运行应用：

```bash
python3 main.py
```

3) 推流：

- 点击“开启推送”按钮，将自动启动内置 RTMP 服务并借助本机 ffmpeg 推流到 `rtmp://127.0.0.1/live/stream`。
- 播放器可用 `vlc` 或 `ffplay` 测试播放：

```bash
ffplay -fflags nobuffer -flags low_delay -infbuf rtmp://127.0.0.1/live/stream
```

### 依赖说明

- 需要系统安装 `ffmpeg` 可执行程序（用于编码与推流）。如果缺失，请在 Linux 下安装：

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg
```

- 首次推流时会自动从官方发布页下载 `MediaMTX` 二进制用于本地 RTMP 服务（支持 `amd64` 和 `arm64`）。

### 提示

- 画布固定为 1280x720，帧率 30 FPS。
- 按“开始出猪”后会以 0.5-1.2 秒的随机间隔生成猪只，并以随机速度穿过画面。

# golang_push