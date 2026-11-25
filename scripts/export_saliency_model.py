"""Convert the pretrained UNISAL saliency model (Droste et al., ECCV 2020; Apache-2.0) to two small ONNX files.

  git clone --depth 1 https://github.com/rdroste/unisal.git .saliency/unisal
  .saliency/venv/bin/python scripts/export_saliency_model.py

Writes .saliency/unisal_image.onnx (still images, SALICON domain, any size that is a multiple of 32) and
.saliency/unisal_video.onnx (one video frame at 224x384, DHF1K domain, with the recurrent state passed in and
out so the worker can run a whole clip frame by frame). Both output a probability map that sums to 1.
The worker only needs onnxruntime + numpy, not PyTorch.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT / ".saliency" / "unisal"
OUT = ROOT / ".saliency"

# import unisal.model without the package __init__ (which pulls in the training code and its extra deps)
pkg = types.ModuleType("unisal")
pkg.__path__ = [str(REPO / "unisal")]
sys.modules["unisal"] = pkg
from unisal import model as umodel  # noqa: E402


def load():
    m = umodel.UNISAL(cnn_cfg={"pretrained": False}, verbose=0)
    state = torch.load(REPO / "training_runs/pretrained_unisal/weights_best.pth", map_location="cpu", weights_only=True)
    m.load_state_dict(state)
    return m.eval()


class ImageNet(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, x):                       # x: [1, 3, H, W], ImageNet-normalised RGB
        y = self.m(x.unsqueeze(1), source="SALICON", static=True)   # log-probabilities [1, 1, 1, H, W]
        return y[:, 0, 0].exp()                  # [1, H, W]


class VideoStep(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, x, h):                    # x: [1, 3, 224, 384]; h: [1, 256, 7, 12] (zeros at the start)
        y, hidden = self.m(x.unsqueeze(1), h0=[h], return_hidden=True, source="DHF1K", static=False)
        return y[:, 0, 0].exp(), hidden[0]


def main():
    m = load()
    torch.manual_seed(0)
    xi = torch.randn(1, 3, 288, 384)
    with torch.no_grad():
        ref_i = ImageNet(m)(xi)
    torch.onnx.export(ImageNet(m), (xi,), OUT / "unisal_image.onnx", input_names=["image"], output_names=["saliency"],
                      dynamic_axes={"image": {2: "h", 3: "w"}, "saliency": {1: "h", 2: "w"}}, opset_version=17,
                      dynamo=False)

    xv = torch.randn(1, 3, 224, 384)
    h0 = torch.zeros(1, 256, 7, 12)
    with torch.no_grad():
        ref_v, ref_h = VideoStep(m)(xv, h0)
    torch.onnx.export(VideoStep(m), (xv, h0), OUT / "unisal_video.onnx", input_names=["frame", "state"],
                      output_names=["saliency", "next_state"], opset_version=17, dynamo=False)

    import onnxruntime as ort
    si = ort.InferenceSession(str(OUT / "unisal_image.onnx"), providers=["CPUExecutionProvider"])
    oi = si.run(None, {"image": xi.numpy()})[0]
    sv = ort.InferenceSession(str(OUT / "unisal_video.onnx"), providers=["CPUExecutionProvider"])
    ov, oh = sv.run(None, {"frame": xv.numpy(), "state": h0.numpy()})
    print("image max abs diff", float(np.abs(oi - ref_i.numpy()).max()), "sum", float(oi.sum()))
    print("video max abs diff", float(np.abs(ov - ref_v.numpy()).max()), float(np.abs(oh - ref_h.numpy()).max()))
    for f in ("unisal_image.onnx", "unisal_video.onnx"):
        print(f, round((OUT / f).stat().st_size / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
