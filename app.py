import gradio as gr
from paths import *
import numpy as np
from vision_tower import DINOv2_MLP
from transformers import AutoImageProcessor
import torch
import os
from PIL import Image

import torch.nn.functional as F
from utils import *

from huggingface_hub import hf_hub_download
ckpt_path = hf_hub_download(repo_id="Viglong/OriNet", filename="croplargeEX2/dino_weight.pt", repo_type="model", cache_dir='./', resume_download=True)
print(ckpt_path)

save_path = './'
device = 'cuda' if torch.cuda.is_available() else 'cpu'
dino = DINOv2_MLP(
                    dino_mode   = 'large',
                    in_dim      = 1024,
                    out_dim     = 360+180+180+2,
                    evaluate    = True,
                    mask_dino   = False,
                    frozen_back = False
                ).to(device)

dino.eval()
print('model create')
dino.load_state_dict(torch.load(ckpt_path, map_location='cpu'))
print('weight loaded')
val_preprocess   = AutoImageProcessor.from_pretrained(DINO_LARGE, cache_dir='./')


def get_3angle(image):
    
    # image = Image.open(image_path).convert('RGB')
    image_inputs = val_preprocess(images = image)
    image_inputs['pixel_values'] = torch.from_numpy(np.array(image_inputs['pixel_values'])).to(device)
    with torch.no_grad():
        dino_pred = dino(image_inputs)

    gaus_ax_pred   = torch.argmax(dino_pred[:, 0:360], dim=-1)
    gaus_pl_pred   = torch.argmax(dino_pred[:, 360:360+180], dim=-1)
    gaus_ro_pred   = torch.argmax(dino_pred[:, 360+180:360+180+180], dim=-1)
    confidence     = F.softmax(dino_pred[:, -2:], dim=-1)[0][0]
    angles = torch.zeros(4)
    angles[0]  = gaus_ax_pred
    angles[1]  = gaus_pl_pred - 90
    angles[2]  = gaus_ro_pred - 90
    angles[3]  = confidence
    return angles

def get_3angle_infer_aug(origin_img, rm_bkg_img):
    
    # image = Image.open(image_path).convert('RGB')
    image = get_crop_images(origin_img, num=3) + get_crop_images(rm_bkg_img, num=3)
    image_inputs = val_preprocess(images = image)
    image_inputs['pixel_values'] = torch.from_numpy(np.array(image_inputs['pixel_values'])).to(device)
    with torch.no_grad():
        dino_pred = dino(image_inputs)

    gaus_ax_pred   = torch.argmax(dino_pred[:, 0:360], dim=-1).to(torch.float32)
    gaus_pl_pred   = torch.argmax(dino_pred[:, 360:360+180], dim=-1).to(torch.float32)
    gaus_ro_pred   = torch.argmax(dino_pred[:, 360+180:360+180+60], dim=-1).to(torch.float32)
    
    gaus_ax_pred   = remove_outliers_and_average_circular(gaus_ax_pred)
    gaus_pl_pred   = remove_outliers_and_average(gaus_pl_pred)
    gaus_ro_pred   = remove_outliers_and_average(gaus_ro_pred)
    
    confidence     = torch.mean(F.softmax(dino_pred[:, -2:], dim=-1), dim=0)[0]
    angles = torch.zeros(4)
    angles[0]  = gaus_ax_pred
    angles[1]  = gaus_pl_pred - 90
    angles[2]  = gaus_ro_pred - 30
    angles[3]  = confidence
    return angles

def infer_func(img, do_rm_bkg, do_infer_aug):
    origin_img = Image.fromarray(img)
    if do_infer_aug:
        rm_bkg_img = background_preprocess(origin_img, True)
        angles = get_3angle_infer_aug(origin_img, rm_bkg_img)
    else:
        rm_bkg_img = background_preprocess(origin_img, do_rm_bkg)
        angles = get_3angle(rm_bkg_img)
    
    phi   = np.radians(angles[0])
    theta = np.radians(angles[1])
    gamma = angles[2]
    
    
    render_axis = render_3D_axis(phi, theta, gamma)
    res_img = overlay_images_with_scaling(render_axis, rm_bkg_img)
    
    # axis_model = "axis.obj"
    return [res_img, round(float(angles[0]), 2), round(float(angles[1]), 2), round(float(angles[2]), 2), round(float(angles[3]), 2)]

server = gr.Interface(
    flagging_mode='never',
    fn=infer_func, 
    inputs=[
        gr.Image(height=512, width=512, label="upload your image"),
        gr.Checkbox(label="Remove Background", value=True),
        gr.Checkbox(label="Inference time augmentation", value=False)
    ], 
    outputs=[
        gr.Image(height=512, width=512, label="result image"),
        # gr.Model3D(clear_color=[0.0, 0.0, 0.0, 0.0],  label="3D Model"),
        gr.Textbox(lines=1, label='Azimuth(0~360°)'),
        gr.Textbox(lines=1, label='Polar(-90~90°)'),
        gr.Textbox(lines=1, label='Rotation(-90~90°)'),
        gr.Textbox(lines=1, label='Confidence(0~1)')
    ]
)

server.launch()
