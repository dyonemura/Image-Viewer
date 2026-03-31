class ImageState:
    def __init__(self):
        self.current_index = 0
        self.current_rotation = 0
        self.current_filter = None
        self.original_image = None
        self.image_files = []
        self.stack_redo = []
        self.stack_undo = []
        
class AppSettings:
    def __init__(self):
        self.confirm_deletes = True
        self.fast_delete = False
        self.labels = []