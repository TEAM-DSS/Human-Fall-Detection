import os
import cv2
import math
import torch
import numpy as np
from tqdm import tqdm
from torchvision import transforms
from utils.datasets import letterbox
from utils.general import non_max_suppression_kpt
from utils.plots import output_to_keypoint
import matplotlib.pyplot as plt
import tkinter as tk
from tkinter import filedialog
from concurrent.futures import ThreadPoolExecutor


RED_COLOR = (0, 0, 255)
FONT = cv2.FONT_HERSHEY_SIMPLEX

results_folder = 'results'
if not os.path.exists(results_folder):
    os.makedirs(results_folder)

def select_video_file():
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename()
    return file_path

def fall_detection(poses):
    '''
        지정한 낙상 조건에 부합하는지를 결정한다.
        넘어진 것이 확인되었다면 True와 함께 좌표를 반환한다.
    '''
    for pose in poses:
        xmin, ymin = (pose[2] - pose[4] / 2), (pose[3] - pose[5] / 2)
        xmax, ymax = (pose[2] + pose[4] / 2), (pose[3] + pose[5] / 2)
        left_shoulder_y = pose[23]
        left_shoulder_x = pose[22]
        right_shoulder_y = pose[26]
        left_body_y = pose[41]
        left_body_x = pose[40]
        right_body_y = pose[44]
        len_factor = math.sqrt(((left_shoulder_y - left_body_y) ** 2 + (left_shoulder_x - left_body_x) ** 2))
        left_foot_y = pose[53]
        right_foot_y = pose[56]
        dx = int(xmax) - int(xmin)
        dy = int(ymax) - int(ymin)
        difference = dy - dx
        if left_shoulder_y > left_foot_y - len_factor and left_body_y > left_foot_y - (
                len_factor / 2) and left_shoulder_y > left_body_y - (len_factor / 2) or (
                right_shoulder_y > right_foot_y - len_factor and right_body_y > right_foot_y - (
                len_factor / 2) and right_shoulder_y > right_body_y - (len_factor / 2)) \
                or difference < 0:
            '''
                어깨가 발보다 아래에 있고 몸이 발보다 아래에 있고 어깨가 몸보다 아래에 있거나
                세로보다 가로가 더 긴 경우 (보통 사람은 서있을 때 세로가 더 길다)
            '''
            return True, (xmin, ymin, xmax, ymax) #넘어진 상태 (좌표와 함께 RETURN)
    return False, None #넘어지지 않은 상태


def falling_alarm(image, bbox):
    '''
        바운딩 박스를 이미지에 그려주고, 텍스트를 입력해준다.(Person Fell down)
    '''
    x_min, y_min, x_max, y_max = bbox
    cv2.rectangle(image, (int(x_min), int(y_min)), (int(x_max), int(y_max)), color=RED_COLOR,
                  thickness=5, lineType=cv2.LINE_AA)
    cv2.putText(image, 'Person Fell down', (11, 100), FONT, 1, RED_COLOR, thickness=3, lineType=cv2.LINE_AA)


def get_pose_model():
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print("device: ", device)
    weigths = torch.load('yolov7-w6-pose.pt', map_location=device)
    model = weigths['model'].float().eval()
    if torch.cuda.is_available():
        model = model.half().to(device)
    return model, device


def get_pose(image, model, device):
    image = letterbox(image, 960, stride=64, auto=True)[0]
    image = transforms.ToTensor()(image)
    image = torch.tensor([image.numpy()])

    if torch.cuda.is_available():
        image = image.half().to(device)

    with torch.no_grad():
        output, _ = model(image)

    output = non_max_suppression_kpt(output, 0.25, 0.65, nc=model.yaml['nc'], nkpt=model.yaml['nkpt'],
                                     kpt_label=True)
    
    with torch.no_grad():
        output = output_to_keypoint(output)
    return image, output


def prepare_image(image):
    _image = image[0].permute(1, 2, 0) * 255 # BGR to RGB
    _image = _image.cpu().numpy().astype(np.uint8).copy()
    return _image


def prepare_vid_out(video_path, vid_cap):
    vid_write_image = letterbox(vid_cap.read()[1], 960, stride=64, auto=True)[0]
    resize_height, resize_width = vid_write_image.shape[:2]
    '''
        video 가져오는 방법 수정 필요
    '''
    out_video_name = f"{os.path.splitext(os.path.basename(video_path))[0]}_keypoint.mp4"
    out_video_path = os.path.join(results_folder, out_video_name)
    out = cv2.VideoWriter(out_video_path, cv2.VideoWriter_fourcc(*'mp4v'), 30, (resize_width, resize_height))
    return out

def process_frame(frame, model, device):
    image, output = get_pose(frame, model, device)
    _image = prepare_image(image)
    is_fall, bbox = fall_detection(output)
    if is_fall:
        falling_alarm(_image, bbox)
    return _image

def process_video(video_path):
    vid_cap = cv2.VideoCapture(video_path)

    if not vid_cap.isOpened():
        print('Error while trying to read video. Please check path again')
        return

    model, device = get_pose_model()
    vid_out = prepare_vid_out(video_path, vid_cap)

    success, frame = vid_cap.read()
    frames = []
    while success:
        frames.append(frame)
        success, frame = vid_cap.read()

    with ThreadPoolExecutor() as executor:
        processed_frames = list(tqdm(executor.map(lambda f: process_frame(f, model, device), frames), total=len(frames)))

    for _image in processed_frames:
        vid_out.write(_image)

    vid_out.release()

if __name__ == '__main__':
    video_path = select_video_file()
    process_video(video_path)
    '''
    for video in os.listdir(videos_path):
        video_path = os.path.join(videos_path, video)
        process_video(video_path)
    '''