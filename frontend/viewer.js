const status = document.querySelector("#status");
const generateButton = document.querySelector("#generate");

const downloadLink = document.querySelector("#download");
const logLink = document.querySelector("#logs");
const viewerElement = document.querySelector("#viewer");



let viewer = null;
let busy = false;

function setBusy(value) {
  busy = value;
  generateButton.disabled = value;
}

function showStatus(message) {
  status.textContent = message;
}

async function requestJSON(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();

  if (!response.ok) {
    const detail = data.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : JSON.stringify(detail || data)
    );
  }

  return data;
}

function showTaskLinks(job) {
  if (job.log_url) {
    logLink.href = job.log_url;
    logLink.hidden = false;
  }

  if (job.model_url) {
    downloadLink.href = job.model_url;
    downloadLink.download = "scene.ply";
    downloadLink.hidden = false;
  }
}

async function loadModel(url) {
  showStatus("模型已生成，正在加载空间查看器……");

  // 延迟加载查看器：网络加载失败时，仍能显示错误。
  const GaussianSplats3D = await import(
    "@mkkellogg/gaussian-splats-3d"
  );

  if (viewer) {
    await viewer.dispose();
    viewer = null;
  }

  viewerElement.replaceChildren();

  viewer = new GaussianSplats3D.Viewer({
    rootElement: viewerElement,

    // 先采用朝前观看的相机。
    // 实际构图需要根据你的模型再微调。
    cameraUp: [0, -1, 0],
    initialCameraPosition: [0, 0, 0],
    initialCameraLookAt: [0, 0, 3],

    // 本地后端未配置跨源隔离头，关闭共享内存。
    sharedMemoryForWorkers: false,

    // 先采用较保守的排序配置。
    gpuAcceleratedSort: false,
    sphericalHarmonicsDegree: 0
  });

  await viewer.addSplatScene(url, {
    // 接口地址没有 .ply 后缀，需要显式说明格式。
    format: GaussianSplats3D.SceneFormat.Ply,
    splatAlphaRemovalThreshold: 5,
    showLoadingUI: true
  });

  viewer.start();
  showStatus("加载完成！可以拖动鼠标、滚轮缩放。");
}

async function waitForModel(jobId) {
  while (true) {
    const job = await requestJSON(`/api/jobs/${jobId}`);
    showTaskLinks(job);

    if (job.status === "completed") {
      await loadModel(job.model_url);
      return;
    }

    if (job.status === "failed") {
      throw new Error(job.message);
    }

    showStatus(
      job.status === "queued"
        ? "照片已上传，等待生成……"
        : "SHARP 正在生成模型，请稍候……"
    );

    await new Promise(resolve => setTimeout(resolve, 3000));
  }
}

document.querySelector("#upload-form").addEventListener(
  "submit",
  async event => {
    event.preventDefault();
    if (busy) return;

    const photo = document.querySelector("#photo").files[0];
    if (!photo) return;

    if (photo.size > 20 * 1024 * 1024) {
      showStatus("请选择不超过 20 MB 的照片。");
      return;
    }

    setBusy(true);
    downloadLink.hidden = true;
    logLink.hidden = true;
    showStatus("正在上传照片……");

    try {
      const formData = new FormData();
      formData.append("file", photo);

      const job = await requestJSON("/api/upload", {
        method: "POST",
        body: formData
      });

      showTaskLinks(job);
      await waitForModel(job.job_id);
    } catch (error) {
      showStatus(`操作失败：${error.message}`);
    } finally {
      setBusy(false);
    }
  }
);

