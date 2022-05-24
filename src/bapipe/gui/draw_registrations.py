import napari
import numpy as np
import cv2


def registration_viewer(
    videos=[], edge_detection=True, edge_threshold1=20, edge_threshold2=20
):
    viewer = napari.Viewer()

    frames = []
    for video in videos:
        cap = cv2.VideoCapture(str(video))
        cap.set(cv2.CAP_PROP_POS_FRAMES, 60 * 30)
        ret, frame = cap.read()
        frame = np.flip(frame, 2)
        frames.append(frame)

    shapes = np.array([frame.shape for frame in frames])
    h, w, c = np.max(shapes, axis=0)

    edges = []
    adj_frames = []
    for frame in frames:
        adj_frame = np.zeros(shape=(h, w, c), dtype=np.uint8)
        oh, ow, oc = frame.shape
        adj_frame[:oh, :ow, :oc] = frame

        if edge_detection:
            blurred = cv2.GaussianBlur(adj_frame, (5, 5), 0)
            edge = cv2.Canny(
                image=blurred, threshold1=edge_threshold1, threshold2=edge_threshold2
            )
            edge_frame = np.zeros(shape=(*edge.shape, 4), dtype=float)
            edge_frame[np.nonzero(edge)] = [0, 0, 0, 1]
            edges.append(edge_frame)

        adj_frames.append(adj_frame)

    adj_frames = np.array(adj_frames)

    image_layer = viewer.add_image(adj_frames)
    if edge_detection:
        edge_layer = viewer.add_image(np.array(edges), opacity=0.5, name="edges")

    registration_layer = viewer.add_shapes(
        name="registration",
        face_color=np.array([1.0, 0.0, 0.0, 0]),
        edge_color=np.array([1.0, 0.0, 0.0, 1.0]),
        edge_width=3,
        ndim=3,
    )
    # viewer.add_points(name='registration', ndim=3)
    napari.run()
