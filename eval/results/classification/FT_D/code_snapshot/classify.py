"""
classify.py: pass each bean crop through YOLO11n to get a label of cocoa type.
Wraps the YOLO11n classifier. No HTTP/tray/SNI logic here, just crop as input and label as output.
"""
import cv2
import numpy as np

try:
    from . import config #runs if this file is imported as a module
except ImportError:
    import config #runs if this file is run as __main__


def load_model(weights_path):
    """
    Load the classifier model and verify its class names before anything else runs.

    The check is necessary. Ultralytics indexes probabilities by the model's own class order, 
    so if a retrained model ever done with a different order, the model will silently points at the wrong class. 
    Nothing crashes and the numbers still look plausible. Raises because a label mismatch invalidates every result.
    """
    from ultralytics import YOLO

    model = YOLO(weights_path)
    names = tuple(model.names[i] for i in sorted(model.names))

    if names != config.CLASS_NAMES:
        raise ValueError(
            f"kelas model tidak cocok.\n"
            f"model     : {names}\n"
            f"diharapkan: {config.CLASS_NAMES}\n"
        )

    return model


def prepare_crop(bgr, pad_mode=None, mask=None, g_gain=None):
    """
    Turn a bean crop image to a square image that the classifier can accept.

    Why pad instead of crop directly: Ultralytics resizes to the short side and then centre crops. A bean crop is taller than it is wide, 
    so the centre crop removes the ends of the bean. Padding to square first means the whole bean survives the resize. 
    The pad colour is black to match the training background, which is pure [0, 0, 0].

    mask : When supplied and enabled in config, everything outside the bean is set to black. A rectangular crop of an elliptical bean 
    carries paper in the corners: measured at 28.6% to 37.6% of each crop over 16 real beans, against black in the same positions in every training image.
    segment.py does not return contours yet, so this stays silent until it does.

    g_gain : optional gain on the green channel. The training images (SANTOS) carry a green cast, G sits at 74 to 79 across all four
    classes while R spans 13 points. Scaling G up on a field photo moves it toward the training distribution. Untested, off by default.
    """
    pad_mode = config.PAD_MODE if pad_mode is None else pad_mode
    g_gain = config.GREEN_CAST_G_GAIN if g_gain is None else g_gain

    img = bgr.copy()

    if mask is not None and config.MASK_BACKGROUND_IN_CROP:
        if mask.shape[:2] != img.shape[:2]: #ensure the mask and real images are the same size, otherwise the mask will be applied incorrectly
            raise ValueError(
                f"ukuran mask {mask.shape[:2]} tidak cocok dengan crop "
                f"{img.shape[:2]}")
        img[~mask.astype(bool)] = 0 #set every background pixel to 0 (black)

    #add green gain to push a field photo toward the training distribution
    if g_gain != 1.0:
        img = img.astype(np.float32)
        img[:, :, 1] *= g_gain
        img = np.clip(img, 0, 255).astype(np.uint8)

    if pad_mode == "none":
        return img

    if pad_mode != "black":
        raise ValueError(f"pad_mode tidak dikenal: {pad_mode!r}")

    #count the top and left padding needed to make the crop square, then create a new square image full of black and paste the cropped bean into it.
    h, w = img.shape[:2]
    side = max(h, w)
    top = (side - h) // 2
    left = (side - w) // 2

    square = np.zeros((side, side, 3), np.uint8) #creating a new black image
    square[top:top + h, left:left + w] = img #paste the original crop into the new black image
    return square


def classify_beans(model, crops, batch_size=None):
    """
    crops: list of BGR arrays, already passed through prepare_crop.
    Returns a list of dicts, one per crop, each holding the winning label, its probability, and the full probability keyed by class name.
    """
    if not crops:
        return []

    batch_size = config.CLASSIFY_BATCH if batch_size is None else batch_size
    out = []

    for start in range(0, len(crops), batch_size): #process crops in batches.
        batch = crops[start:start + batch_size]
        for r in model.predict(batch, imgsz=config.CLASSIFY_IMGSZ, verbose=False): #run the classifier on every image on the batch. "r" will be a result/information produced by the model for each image in the batch. 
            data = r.probs.data.tolist() #list of probabilities for each class
            probs = {r.names[i]: float(p) for i, p in enumerate(data)} #making dictionary of class names and their probabilities
            top = int(r.probs.top1) #extract the index of the winning class
            out.append({
                "label": r.names[top], #r.names is a list of class names, and top is the index of the winning class. 
                "conf": float(data[top]),
                "probs": probs,
            })

    return out


def classify_tray(model, beans):
    """
    Intermediary function that takes the output of segment.detect_beans, processes it through prepare_crop and classify_beans.
    beans: list of dicts from detect_beans, each with a "crop" key and optionally a "mask" key
    Returns the same list of result dicts as classify_beans.
    """
    crops = [prepare_crop(b["crop"], mask=b.get("mask")) for b in beans]
    return classify_beans(model, crops)


if __name__ == "__main__":
    import sys
    import pathlib

    weights = sys.argv[1] if len(sys.argv) > 1 else "weights/best.pt" #if user does not provide a model's path, use default "weights/best.pt"
    crop_dir = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "crops") #for the directory of crops, if user does not provide a path, use default "crops"

    #all files in the crop_dir with .jpg, .jpeg, or .png extensions will be sorted alphabeticallyinto a list
    files = sorted(p for p in crop_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")) 
    #fail fast if no crops found, because the rest of the script will run and produce a confusing error message.
    if not files:
        sys.exit(f"tidak ada gambar crop di {crop_dir}")

    model = load_model(weights)
    print(f"model : {weights}")
    print(f"kelas : {tuple(model.names[i] for i in sorted(model.names))}")
    print(f"crop  : {len(files)} file dari {crop_dir}")
    #crops on disk carry no mask, so the masking step cannot run here even though it is enabled in config
    print(f"pad   : {config.PAD_MODE}   mask: tidak diterapkan (crop dari berkas tidak menyimpan mask)   g_gain: {config.GREEN_CAST_G_GAIN}")
    print("catatan: runner ini untuk inspeksi manual, hasilnya bisa berbeda dari aplikasi karena masking tidak aktif")
    print()

    #read the imges and prepare them for classification. 
    crops = [prepare_crop(cv2.imread(str(p))) for p in files] 
    hasil = classify_beans(model, crops)

    #print each images lable, confidence, and slaty percentage
    for p, h in zip(files, hasil):
        print(f" {p.name:<28} {h['label']:<16} {h['conf']:.3f}"
              f"   P(fermented)={h['probs']['fermented']:.4f}")

    labels = [h["label"] for h in hasil]
    p_fermented = [h["probs"]["fermented"] for h in hasil]

    #print lable, lable counts, and percentage 
    print()
    for c in config.CLASS_NAMES:
        n = labels.count(c)
        print(f"  {c:<18} {n:3d}  ({100 * n / len(labels):5.1f}%)")

    #these metrics help determine whether the model transfers well to real beans.
    print()
    print(f"P(fermented) pada semua crop: max = {max(p_fermented):.4f};  "
          f"rata-rata = {sum(p_fermented) / len(p_fermented):.4f};")