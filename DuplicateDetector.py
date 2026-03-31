# Standard library
from hashlib import md5

# Third‑party libraries
import cv2
import numpy as np
from PIL import Image, ImageOps
from imagehash import phash
import torch
import torch.nn.functional as F
from torchvision import models, transforms

class DuplicateDetectorMain:
    def __init__(self):
        self.resnet_model = None
        self.transform = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.embedding_cache = {}
        self.orb_cache = {}
        self._orb = cv2.ORB_create(3000)

    def _load_resnet(self):
        if self.resnet_model is not None:
            return
        model = models.resnet50(weights=models.ResNet50_Weights.DEFAULT)
        self.resnet_model = torch.nn.Sequential(*list(model.children())[:-1])
        self.resnet_model.eval()
        self.resnet_model.to(self.device)
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                std=[0.229, 0.224, 0.225])
        ])

    # Helper functions to load images in different formats
    def load_pil(self, img):
        """Always returns a PIL image."""
        if isinstance(img, str):
            return Image.open(img).convert("RGB")
        return img.convert("RGB")

    def load_cv2(self, img):
        """Always returns a grayscale OpenCV image. Handles both file paths and PIL images."""
        if isinstance(img, str):
            return cv2.imread(img, cv2.IMREAD_GRAYSCALE)
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)

    # Only works for file paths, bytes must be identical
    def md5_hash(self, img):
        """Calculate MD5 hash of a file to check for exact file duplicates. No image processing."""
        with open(img, "rb") as f:
            h = md5()
            while chunk := f.read(65536):
                h.update(chunk)
            return h.hexdigest()

    def _phash(self, img):
        """Calculate perceptual hash (pHash) of an image for quick similarity checks. Handles minor edits."""
        return phash(self.load_pil(img))
    
    def _get_orb_descriptors(self, img):
        if isinstance(img, str) and img in self.orb_cache:
            return self.orb_cache[img]
        
        image = self.load_cv2(img)
        if image is None:
            return None
        
        _, des = self._orb.detectAndCompute(image, None)
        
        if isinstance(img, str):
            self.orb_cache[img] = des
        return des
    
    def orb_matches(self, img1, img2):
        """Calculate the number of ORB feature matches between two images. Handles crops and rotations."""
        des1 = self._get_orb_descriptors(img1)
        des2 = self._get_orb_descriptors(img2)

        if des1 is None or des2 is None:
            return 0

        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        return len(bf.match(des1, des2))

    # Functions to get ResNet embeddings and compare them with cosine similarity, including rotations and flips to handle edits
    def get_embedding(self, img):
        if isinstance(img, str) and img in self.embedding_cache:
            return self.embedding_cache[img]
        
        self._load_resnet()
        pil = self.load_pil(img)
        tensor = self.transform(pil).unsqueeze(0).to(self.device)
        with torch.no_grad():
            emb = self.resnet_model(tensor).squeeze()
        emb = F.normalize(emb, dim=0)
        
        if isinstance(img, str):
            self.embedding_cache[img] = emb
        return emb

    def best_embedding_similarity(self, img1, img2):
        """Uses cosine similarity of ResNet embeddings to determine duplicate images"""
        emb1 = self.get_embedding(img1)
        pil2 = self.load_pil(img2)

        variants = [
            var.rotate(angle, expand=True)
            for var in [pil2, ImageOps.mirror(pil2)]
            for angle in [0, 90, 180, 270]
        ]

        self._load_resnet()
        tensors = torch.stack([self.transform(v) for v in variants]).to(self.device)
        with torch.no_grad():
            embs = self.resnet_model(tensors).squeeze(-1).squeeze(-1)
        embs = F.normalize(embs, dim=1)

        sims = F.cosine_similarity(emb1.unsqueeze(0), embs)
        return sims.max().item()

    def duplicate_check(self, img1, img2,
                        phash_thresh=8,
                        phash_definite_miss=40,
                        orb_thresh=750,
                        cos_thresh=0.88,
                        cos_definite_miss=0.4):
        """Function that combines multiple methods to detect duplicates."""

        # MD5
        m1, m2 = self.md5_hash(img1), self.md5_hash(img2)
        if m1 == m2:
            return True, "md5 exact match"

        # pHash
        diff = self._phash(img1) - self._phash(img2)
        if diff <= phash_thresh:
            return True, f"phash ({diff})"
        if diff >= phash_definite_miss:
            return False, f"phash definite miss ({diff})"

        # ORB
        matches = self.orb_matches(img1, img2)
        if matches >= orb_thresh:
            return True, f"orb ({matches} matches)"

        # ResNet embeddings
        best_cos = self.best_embedding_similarity(img1, img2)
        if best_cos >= cos_thresh:
            return True, f"cosine ({best_cos:.3f})"
        if best_cos <= cos_definite_miss:
            return False, f"cosine definite miss ({best_cos:.3f})"

        return False, f"no match (cos={best_cos:.3f}, orb={matches})"
    
    def find_duplicates(self, image_files, current_index):
        current_image = image_files[current_index]
        duplicates = []
        for i, img in enumerate(image_files):
            if i != current_index:
                is_dupe, reason = self.duplicate_check(current_image, img)
                if is_dupe:
                    duplicates.append((img, reason))
        return current_image, duplicates