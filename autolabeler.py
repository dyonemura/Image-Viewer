import torch
import clip
from PIL import Image

device = "cuda" if torch.cuda.is_available() else "cpu"
_model = None
_preprocess = None

def _load_clip():
    """Lazy-load the CLIP model and preprocessing function. Uses global variables to cache them after the first load."""
    global _model, _preprocess
    if _model is not None:
        return
    _model, _preprocess = clip.load("ViT-B/32", device=device)

def initialize_clip_labels(text_labels):
    """Tokenizes the list of text labels for CLIP and moves them to the appropriate device. Caches the result for efficiency."""
    return clip.tokenize(text_labels).to(device)

def get_clip_label(image_path, text_labels, text_tokens=None):
    """Given an image path and a list of text labels, returns the label with the highest CLIP similarity score."""
    _load_clip()
    image = _preprocess(Image.open(image_path)).unsqueeze(0).to(device)

    with torch.no_grad():
        logits_per_image, _ = _model(image, text_tokens)
        probs = logits_per_image.softmax(dim=-1)
    
    ind = probs[0].argmax().item()
    return text_labels[ind], probs[0][ind].item()