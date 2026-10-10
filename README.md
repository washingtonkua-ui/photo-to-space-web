# Photo to Space：照片转空间模型

上传一张照片，通过 Apple SHARP 生成高斯泼溅模型，并在浏览器中移动视角查看。

项目在使用者自己的电脑运行，照片和生成的模型保存在本机。

## 1. 安装 Apple SHARP

按照官方仓库的安装说明安装：
https://github.com/apple-aiml-research/ml-sharp

安装完成后，在安装 SHARP 的 Python 环境中运行：

```bash
sharp predict --help
```

出现帮助说明后，继续下面的步骤。

## 2. 下载本项目

在 GitHub 仓库页面点击 Code → Download ZIP，然后解压。

也可以使用 Git：

```bash
git clone https://github.com/washingtonkua-ui/photo-to-space.git
cd photo-to-space
```

如果下载的是 ZIP，请在终端进入解压后的项目文件夹。

## 3. 安装项目依赖

激活安装了 SHARP 的 Python 环境。
如果环境名称是 sharp：

```bash
conda activate sharp
```

在项目根目录执行：

```bash
python -m pip install -r requirements.txt
```

## 4. 启动项目

```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

保持终端运行，在浏览器打开：

http://127.0.0.1:8000/

## 5. 使用方法

1. 选择一张 JPG 或 PNG 照片，大小不超过 20 MB。
2. 点击“生成空间模型”。
3. 等待生成和加载完成。
4. 在查看区域拖动鼠标调整视角，滚轮缩放。
5. 点击下载链接保存 .ply 模型。

## 注意事项

- 首次生成需要联网下载 SHARP 模型权重。
- 网页查看器需要联网加载。
- 照片保存在 uploads/，生成模型和日志保存在 outputs/。
- 一次处理一个生成任务，其他任务排队等待。
- 重启后端会清空任务记录，但不会删除已保存的文件。
- 单张照片生成的空间适合小幅改变视角，大角度观看可能出现缺失或变形。
- 在运行终端按 Control + C 停止服务。