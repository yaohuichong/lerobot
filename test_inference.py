import cv2
import torch

from lerobot.policies.act.modeling_act import ACTPolicy

policy = ACTPolicy.from_pretrained("/home/nvidia/scooping_model/pretrained_model")
policy = policy.to("cuda")
policy.eval()

cap0 = cv2.VideoCapture(0)
cap2 = cv2.VideoCapture(2)

for i in range(10):
    ret0, frame0 = cap0.read()
    ret2, frame2 = cap2.read()

    def preprocess(frame):
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = torch.from_numpy(frame).permute(2, 0, 1).float() / 255.0
        return frame.unsqueeze(0).cuda()

    observation = {
        "observation.state": torch.zeros(1, 6).cuda(),
        "observation.images.handeye": preprocess(frame0),
        "observation.images.front": preprocess(frame2),
    }

    with torch.no_grad():
        action = policy.select_action(observation)

    print(f"frame {i + 1}: {action.cpu().numpy()}")

cap0.release()
cap2.release()
