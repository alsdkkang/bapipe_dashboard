"""Utility functions for visualizing or manipulating data"""
import numpy as np
import ffmpeg
import cv2
import matplotlib.pyplot as plt

from skimage import draw
from skimage.transform import resize

def create_video_grid(video_set, scale=0.5, override_config={}):
    """Aggregate a VideoSet into a single summary image"""
    columns = int(np.sqrt(len(video_set)))
    rows = int(np.ceil(len(video_set) / columns))
    
    frames = [video.get_frame(900, override_config=override_config) for video in video_set]
    max_h, max_w, _ = np.max(np.array([frame.shape for frame in frames]), axis=0)
    nw, nh = int(max_w * scale), int(max_h * scale)
    frames = [resize(frame, (nh, nw)) for frame in frames]
    img = np.zeros((nh*rows,nw*columns,3))
    
    frame_iter = iter(frames)
    for i in range(rows):
        for j in range(columns):
            img[i*nh:(i+1)*nh, j*nw:(j+1)*nw] = next(frame_iter)
            
    return img 

def draw_dataframe_points(frame, df, frame_index, bodyparts=[], hist=5, alpha_degrade=0.6):
    """Draw x,y coordinates from a dataframe onto an image"""
    h,w,_ = frame.shape
    alpha = 1.0
    
    if not len(bodyparts):
        bodyparts = (
            df
            .columns
            .get_level_values('bodyparts')
            .unique())
        
    colormap = plt.cm.ScalarMappable(cmap='rainbow')
    colors = colormap.to_rgba(np.linspace(0, 1, len(bodyparts)))[:,:3]
    colors = (colors * 255).astype(np.uint8)
    
    for k in range(hist):
        if frame_index - k < 0: 
            return 
        
        row = df.iloc[frame_index - k]
        for idx, bp in enumerate(bodyparts):
            rr, cc = draw.disk((row.loc[bp].y, row.loc[bp].x), radius=3, shape=(h,w))
            frame[rr, cc] = (1-alpha)*frame[rr,cc] + alpha*colors[idx]
            
        alpha = alpha * alpha_degrade
            
            
def draw_text(img, lines,
              font=cv2.FONT_HERSHEY_PLAIN,
              pos=(0, 0),
              font_scale=1,
              font_thickness=1,
              text_color=(0, 255, 0),
              text_color_bg=(0, 0, 0),
              padding=3
          ):
    """Draw text onto an image"""
    dx, dy = pos
    max_width, max_height = 0, 0
    for text in lines:
        text_size, _ = cv2.getTextSize(text, font, font_scale, font_thickness)
        text_w, text_h = text_size
        max_width = max(text_w, max_width)
        max_height = max(text_h, max_height)
        
    n_lines = len(lines)
    
    width = max_width + padding * 2
    height = max_height * n_lines + padding * (n_lines + 1)
    cv2.rectangle(img, pos, (dx+width, dy+height), text_color_bg, -1)
    
    for i, text in enumerate(lines):
        y = dy + (max_height + padding) * (i+1) - 1 + font_scale
        cv2.putText(img, text, (dx + padding, y), font, font_scale, text_color, font_thickness)

class VideoWriter:
    """Convenient method for creating videos"""
    def __init__(self, video, output_file):
        self.output_file = str(output_file)
        frame = video.get_frame(0)
        self.cap = video.get_cap()
        self.h, self.w, _ = frame.shape
        self.read_bytes = self.w * self.h * 3
        self.image_shape = [self.h, self.w, 3]
        
    def __enter__(self):
        self.write_pipe = (
            ffmpeg
            .input('pipe:', format='rawvideo', pix_fmt='rgb24', s='{}x{}'.format(self.w, self.h))
            .output(self.output_file, pix_fmt='yuv420p')
            .overwrite_output()
            .run_async(pipe_stdin=True, quiet=True)
        )
    
        return self
    
    def write(self, frame):
        self.write_pipe.stdin.write((frame).astype(np.uint8).tobytes())
    
    def __exit__(self, type, value, traceback):
        self.write_pipe.stdin.close()
        self.write_pipe.wait()
        
    def __len__(self):
        return self.frames