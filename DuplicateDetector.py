import hashlib
import numpy as np
import torch
import torch.nn.functional as F
import imagehash
import cv2
from PIL import Image, ImageOps
from torchvision import models, transforms

# Resnet Model Used For Image Recognition
resnet_model = models.resnet50(weights=models.ResNet50_Weights.DEFAULT)
resnet_model = torch.nn.Sequential(*list(resnet_model.children())[:-1])
resnet_model.eval()

# Transform images to match ResNet input requirements
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225])
])

# Helper functions to load images in different formats
def load_pil(img):
    """Always returns a PIL image."""
    if isinstance(img, str):
        return Image.open(img).convert("RGB")
    return img.convert("RGB")

def load_cv2(img):
    """Always returns a grayscale numpy array."""
    if isinstance(img, str):
        return cv2.imread(img, cv2.IMREAD_GRAYSCALE)
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)

# Only works for file paths, bytes must be identical
def md5_hash(img):
    """Calculate MD5 hash of a file to check for exact file duplicates. No image processing."""
    if not isinstance(img, str):
        return None
    with open(img, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def phash(img):
    """Calculate perceptual hash (pHash) of an image for quick similarity checks. Handles minor edits."""
    return imagehash.phash(load_pil(img))

def orb_matches(img1, img2):
    """Calculate the number of ORB feature matches between two images. Handles crops and rotations."""
    image_1 = load_cv2(img1)
    image_2 = load_cv2(img2)

    if image_1 is None or image_2 is None:
        return 0

    orb = cv2.ORB_create(3000)
    _, des1 = orb.detectAndCompute(image_1, None)
    _, des2 = orb.detectAndCompute(image_2, None)

    if des1 is None or des2 is None:
        return 0

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(des1, des2)
    return len(matches)

# Functions to get ResNet embeddings and compare them with cosine similarity, including rotations and flips to handle edits
def get_embedding(img):
    pil = load_pil(img)
    tensor = transform(pil).unsqueeze(0)
    with torch.no_grad():
        emb = resnet_model(tensor).squeeze()
    return F.normalize(emb, dim=0)

def best_embedding_similarity(img1, img2):
    """Uses cosine similarity of ResNet embeddings to determine duplicate images"""
    emb1 = get_embedding(img1)
    pil2 = load_pil(img2)
    best = 0
    
    # Checks all 4 rotations and mirror vaiants to handle edits like mirroring and rotation
    variants = [pil2, ImageOps.mirror(pil2)]
    for var in variants:
        for angle in [0, 90, 180, 270]:
            emb2 = get_embedding(var.rotate(angle))
            cos = F.cosine_similarity(emb1.unsqueeze(0), emb2.unsqueeze(0)).item()
            best = max(best, cos)
    return best

def duplicate_check(img1, img2,
                    phash_thresh=8,
                    phash_definite_miss=40,  # skip expensive tiers if very different
                    orb_thresh=700,
                    cos_thresh=0.88,
                    cos_definite_miss=0.4):
    """Function that combines multiple methods to detect duplicates"""

    # MD5
    m1, m2 = md5_hash(img1), md5_hash(img2)
    if m1 and m2 and m1 == m2:
        return True, "md5 exact match"

    # pHash
    h1, h2 = phash(img1), phash(img2)
    diff = h1 - h2
    if diff <= phash_thresh:
        return True, f"phash ({diff})"
    if diff >= phash_definite_miss:
        return False, f"phash definite miss ({diff})"

    # ORB
    matches = orb_matches(img1, img2)
    if matches >= orb_thresh:
        return True, f"orb ({matches} matches)"

    # ResNet embeddings
    best_cos = best_embedding_similarity(img1, img2)
    if best_cos >= cos_thresh:
        return True, f"cosine ({best_cos:.3f})"
    
    if best_cos <= cos_definite_miss:
        return False, f"cosine definite miss ({best_cos:.3f})"

    return False, f"no match (cos={best_cos:.3f}, orb={matches})"