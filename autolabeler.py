import torch
import clip
from PIL import Image

class CLIPLabeler:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = None
        self.preprocess = None

    def _load_clip(self):
        """Lazy-load the CLIP model and preprocessing function. Uses global variables to cache them after the first load."""
        if self.model is not None:
            return
        self.model, self.preprocess = clip.load("ViT-B/32", device=self.device)

    def initialize_clip_labels(self, text_labels):
        """Tokenizes the list of text labels for CLIP and moves them to the appropriate device. Caches the result for efficiency."""
        return clip.tokenize(text_labels).to(self.device)

    def get_clip_label(self, image_path, text_labels, text_tokens=None):
        """Given an image path and a list of text labels, returns the label with the highest CLIP similarity score."""
        self._load_clip()
        image = self.preprocess(Image.open(image_path)).unsqueeze(0).to(self.device)

        with torch.no_grad():
            logits_per_image, _ = self.model(image, text_tokens)
            probs = logits_per_image.softmax(dim=-1)
        
        ind = probs[0].argmax().item()
        return text_labels[ind], probs[0][ind].item()