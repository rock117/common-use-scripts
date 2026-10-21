import torch

ckpt = torch.load("temp/signing/signing_workflow_minimal/yolo11n_distill_20260921.pt", map_location="cpu", weights_only=False)
for i, name in ckpt["model"].names.items():
    print(i, name)
