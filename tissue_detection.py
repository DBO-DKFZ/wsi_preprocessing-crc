import copy

import cv2
import matplotlib.pyplot as plt
import numpy as np


def tissue_detection(img, remove_top_border: bool = False):
    kernel_size = 3

    # remove alpha channel
    img = img[:, :, 0:3]

    if remove_top_border:
        top_border = int(len(img) / 5)
        # hack for removing border artifacts
        img[0:top_border, :, :] = [0, 0, 0]

    # remove black background pixel
    black_px = np.where((img[:, :, 0] <= 5) & (img[:, :, 1] <= 5) & (img[:, :, 2] <= 5))
    img[black_px] = [255, 255, 255]

    # apply median filter to remove artifacts created by transitions to background pixels
    median_filtered_img = cv2.medianBlur(img, 11)

    # convert to HSV color space
    hsv_image = cv2.cvtColor(median_filtered_img, cv2.COLOR_RGB2HSV)

    # get saturation channel
    saturation = hsv_image[:, :, 1]

    # Otsu's thresholding
    _, threshold_image = cv2.threshold(saturation, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # apply dilation to image to close spots inside mask regions
    kernel = np.ones(shape=(kernel_size, kernel_size))
    tissue_mask = cv2.dilate(threshold_image, kernel, iterations=1)
    # tissue_mask = cv2.erode(tissue_mask, kernel)

    return tissue_mask
