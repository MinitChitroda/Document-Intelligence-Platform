import cv2
import numpy as np


def deskew(image: np.ndarray) -> np.ndarray:
    """
    Detects and corrects skew in a grayscale image using image moments.
    If the detected skew angle is within a safe range, applies rotation.
    Returns the corrected image (or original if no significant skew found).
    """
    # Find all non-zero pixel coordinates
    coords = np.column_stack(np.where(image > 0))
    if len(coords) < 10:
        return image  # Not enough pixels to determine skew

    angle = cv2.minAreaRect(coords)[-1]

    # minAreaRect returns angles in [-90, 0); map to [-45, 45] range
    if angle < -45:
        angle = 90 + angle

    # Only correct if skew is meaningful (>0.5 deg) and safe (<20 deg)
    if abs(angle) < 0.5 or abs(angle) > 20:
        return image

    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        image, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE
    )
    return rotated


def preprocess_image(img: np.ndarray) -> np.ndarray:
    """
    Enhanced preprocessing for photographed documents (e.g. receipts):
    1. Grayscale conversion
    2. Deskew
    3. Denoising
    4. Contrast Enhancement (CLAHE)
    5. Adaptive Thresholding
    """
    # Step 1: Grayscale conversion
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    # Step 2: Deskew
    gray = deskew(gray)
    
    # Step 3: Denoising
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    
    # Step 4: Contrast Enhancement using CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    gray = clahe.apply(gray)
    
    # Step 5: Adaptive Thresholding (or Otsu)
    # Using Otsu's thresholding to handle uneven lighting better than global threshold
    _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    return gray
