"""
Tray photo of cocoa beans will be processed into list of individual bean crops.
Deterministic, no training process and no bounding box annotations.
"""
import cv2
import numpy as np

try:
    from . import config
except ImportError:
    import config


def _paper_roi(bgr, min_frac=config.PAPER_MIN_FRAME_FRACTION):
    """
    Find the largest bright area (the background sheet) and return its mask.
    Return None if no convincing candidate is found, so the caller falls back to the previous behavior (full frame).
    """
    v = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[:, :, 2] #convert bgr to hsv and get the V value 
    v = cv2.GaussianBlur(v, config.PAPER_BLUR_KERNEL, 0) #blur the image to reduce small pixel noise and improve thresholding
    _, bright = cv2.threshold(v, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU) #otsu: algorithm used to separate bright areas (paper) from darker areas (background)

    #close operation to fill small holes in the bright areas (paper) caused by beans on top of it
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, config.PAPER_CLOSE_KERNEL) 
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, kern, iterations=config.PAPER_CLOSE_ITERATIONS) 

    cnts, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE) #search for outlines of the bright areas (paper) in the image
    #if no contours found, return None
    if not cnts:
        return None
    
    #for each contour found, find the one with the largest area (the paper)
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < min_frac * bgr.shape[0] * bgr.shape[1]: #if the area of the largest contour is less than 15% of the total image area, return None
        return None

    roi = np.zeros(v.shape, np.uint8) #create a blank image with the same shape as v
    cv2.drawContours(roi, [cv2.convexHull(c)], -1, 255, -1) #draw the largest contour (the paper) on the blank image as a filled white shape
    roi = cv2.erode(roi, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, config.PAPER_ERODE_KERNEL), #erode the edges of the paper mask slightly to avoid including the paper's edge in the foreground mask
                    iterations=config.PAPER_ERODE_ITERATIONS)
    return roi #return the final paper mask to be used for foreground detection


def _foreground_mask(bgr, roi=None):
    """
    Create new black and white image, but this time white = seeds and black = paper.

    We do not use V alone because pale type of beans can have similar brightness to the paper and would disappear without warning. 
    Lab is used because hue/chromatic components are more stable than brightness, and Lab distance is roughly proportional to perceived color difference.
    """
    #use LAB color space to measure color difference between the background and the beans. The image is first blurred to reduce noise and improve color distance measurement.
    lab = cv2.cvtColor(cv2.GaussianBlur(bgr, config.MASK_BLUR_KERNEL, 0), cv2.COLOR_BGR2LAB)
    lab = lab.astype(np.float32)

    #search for the median color of paper (ROI)
    if roi is not None and cv2.countNonZero(roi) > config.MASK_MIN_ROI_PIXELS: #if there is more than 1000 of white pixels then calculate the median color of that paper
        ref = np.median(lab[roi > 0], axis=0)
    else: #calculate the median color of the entire image, assuming that the paper is the dominant color in the image
        ref = np.median(lab.reshape(-1, 3), axis=0)

    #compares each pixel’s color to "ref" and measures how different it is. Pixels close to the background are treated as paper, while pixels far from the background are treated as cocoa beans.
    d = np.sqrt((lab[..., 0] - ref[0]) ** 2
                + config.MASK_CHROMA_WEIGHT * (lab[..., 1] - ref[1]) ** 2
                + config.MASK_CHROMA_WEIGHT * (lab[..., 2] - ref[2]) ** 2)
    d = np.clip(d, 0, 255).astype(np.uint8)

    #sample is a collection of color distance values from pixels known to be paper, used to determine the threshold for distinguishing beans from the background
    sample = d[roi > 0] if roi is not None else d.ravel() 

    #otsu is not the correct way because otsu balances 2 classes, but foreground here is multi modal classes.
    #dark beans: 140 from background, pale beans: 80 from background. Otsu gets pulled toward dark beans and pale beans silently disappear.
    
    #Hence we use median + k * MAD from the background. Robust to beans partially covering it). k = 7 from sweeping 6 test
    #From the 6 tests (safe range k = 5 - 10): too small then background texture read as objects, too large then pale beans vanish.
    bg = float(np.median(sample))
    mad = float(np.median(np.abs(sample - bg)))
    t = bg + config.MASK_MAD_K * max(mad, config.MASK_MAD_FLOOR)

    mask = np.uint8(d > t) * 255
    if roi is not None:
        mask = cv2.bitwise_and(mask, roi)

    return mask


def _clean(mask, k=config.CLEAN_OPEN_KERNEL):
    """
    Mask from _foreground_mask() could still be noisy and has holes. Clean with two steps, Small open (remove debris specks) and fill holes inside beans via contour fill.
    Contour fill closes internal holes without growing the outer edge.

    We dont use morph close because it will weld two touching beans into one contour before they can be split. 
    That error is silent, two beans get counted as one, and the percentage will be inaccurate.
    """
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kern, iterations=1)

    #find outer outline of each bean, then fill in every pixel that's inside that outline
    #any hole inside a bean (from light reflection) gets ignored since only the OUTER outline is used to redraw (this fills holes without ever touching or merging separate beans)
    filled = np.zeros_like(mask)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(filled, cnts, -1, 255, thickness=-1)
    return filled


def _split_one(cluster, min_area, frac):
    """
    Watershed on one cluster (cluster means two or more cocoa beans touching each other). The watershed algorithm is used to separate touching beans into individual beans.
    Why per-cluster and not all at once: the distance transform is normalized to dist.max(). If all clusters are processed together, 
    a cluster containing 4 beans has a much higher peak than a cluster containing 2 beans, causing the global threshold to remove all seeds from the smaller cluster.
    """
    #each pixel is given a value which is distance to the nearest edge. The center point of the bean = the highest value (this is what is meant by the mountain peak analogy in watershed
    dist = cv2.distanceTransform(cluster, cv2.DIST_L2, config.SPLIT_DIST_MASK)
    if dist.max() <= 0:
        return cluster

    #take only the highest peaks as starting points for each individual bean. frac=0.45: only pixels with a value at least 45% of the highest peak in this cluster
    _, seeds = cv2.threshold(dist, frac * dist.max(), 255, 0)
    seeds = seeds.astype(np.uint8)

    #count how many separate seed groups there are. if there is only 1 group (n=2, because the background is counted as 1), then there is only 1 peak, no splitting is needed
    n, markers = cv2.connectedComponents(seeds)
    if n <= 2:
        return cluster

    #standard watershed OpenCV setup: sure_bg = area that's not a bean, unknown = gray area that has not yet been determined to belong to which seed
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, config.SPLIT_BG_KERNEL)
    sure_bg = cv2.dilate(cluster, kern, iterations=config.SPLIT_BG_ITERATIONS)
    unknown = cv2.subtract(sure_bg, seeds)

    markers = markers + 1
    markers[unknown == 255] = 0
    #watershed requires a 3 channel image, so it's converted even though it remains grayscale in content.
    markers = cv2.watershed(cv2.cvtColor(cluster, cv2.COLOR_GRAY2BGR), markers)

    #collect each separated bean result into one mask again
    out = np.zeros_like(cluster)
    for lab in range(2, markers.max() + 1):
        comp = np.uint8(markers == lab) * 255
        #watershed can sometimes spill over slightly outside the original cluster shape, so it is clipped back using and with the original cluster
        comp = cv2.bitwise_and(comp, cluster)
        #components that are too small are considered failed splits, not valid beans
        if cv2.countNonZero(comp) >= min_area:
            out = cv2.bitwise_or(out, comp)
    #if all components end up being discarded, it is safer to return the original cluster (fail-safe) rather than an empty mask
    return out if cv2.countNonZero(out) > 0 else cluster


def _split_touching(big, min_area, med, fracs=config.SPLIT_SEED_FRACTIONS):
    """
    Split each cluster one at a time. For clusters with many beans, the seed threshold is lowered step by step until the number of resulting pieces makes sense (estimated from the cluster size)
    This is a patch, not a real fix. The real fix is spacing beans apart when photographing.
    """
    out = np.zeros_like(big)
    #find each separate touching cluster in the big mask
    cnts, _ = cv2.findContours(big, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in cnts:
        #isolate just this one cluster onto its own blank canvas
        one = np.zeros_like(big)
        cv2.drawContours(one, [c], -1, 255, -1)

        #rough guess : how many beans should be in here, based on this cluster's area vs the size of one average bean (med)
        expect = max(2, int(round(cv2.contourArea(c) / med)))

        #try watershed at increasingly aggressive thresholds until the split count matches expectation, or we run out of tries
        best = one
        for f in fracs:
            got = _split_one(one, min_area, f)
            k, _ = cv2.findContours(got, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            best = got
            if len(k) >= expect:
                break
        #add this cluster's split result to the output
        out = cv2.bitwise_or(out, best)
    return out


def detect_beans(bgr, target_w=config.TARGET_WIDTH, pad=config.CROP_PAD, debug=False):
    """
    Returns: (out, flagged, warn, frag, dropped_n, edge_n[, vis, mask])
    out is list[dict(crop, bbox, area, ar)]
    """
    #1. normalize the scale so absolute area thresholds work across photos taken at different resolutions
    h, w = bgr.shape[:2]
    if w != target_w:
        s = target_w / w
        bgr = cv2.resize(bgr, (target_w, int(h * s)), interpolation=cv2.INTER_AREA)

    #2. call the function to get a bean vs background mask
    roi = _paper_roi(bgr)
    mask = _clean(_foreground_mask(bgr, roi))

    #3. calibrate area thresholds based on each photo's own data
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return []
    areas = np.array([cv2.contourArea(c) for c in cnts])

    #Estimate bean area using an area weighted median. This prevents many tiny noise contours from pulling the estimate down.
    #Area weighted median finds the value where cumulative area crosses 50% of the total. Dust contributes <1% of total area, so it can't shift the result, whether there are 2 beans or 100.
    srt = np.sort(areas)
    cum = np.cumsum(srt)
    if cum[-1] <= 0:
        return []
    med = float(srt[min(int(np.searchsorted(cum, cum[-1] / 2.0)), len(srt) - 1)])
    if med <= 0:
        return []

    lo = config.AREA_MIN_FACTOR * med  #below lo will be treated as debris, shadow, fragment
    split_at = config.AREA_SPLIT_FACTOR * med #above split_at will be treated as a candidate for touching beans
    hi = config.AREA_MAX_FACTOR * med  #accept ceiling after splitting

    #4. contours that are too large may contain multiple touching beans. we use 1.4x the estimated bean area because touching beans overlap, so their combined area is usually less than 2x one bean.
    if (areas > split_at).any():
        big = np.zeros_like(mask)
        for c, a in zip(cnts, areas):
            if a > split_at:
                cv2.drawContours(big, [c], -1, 255, -1)
        split = _split_touching(big, int(lo), med)
        mask = cv2.bitwise_or(cv2.bitwise_and(mask, cv2.bitwise_not(big)), split)
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    #5. geometry filter and crop
    H, W = mask.shape
    out, flagged = [], []
    dropped_area = 0.0
    dropped_n = 0
    edge_n = 0
    for c in cnts:
        a = cv2.contourArea(c)
        x, y, bw, bh = cv2.boundingRect(c)

        #drop anything touching the frame edge (surfaces outside the sheet like tables could slip through if sheet detection failed and a bean cut off by the photo edge will be treated as invalid bean.)
        if x <= 1 or y <= 1 or x + bw >= W - 1 or y + bh >= H - 1:
            edge_n += 1
            continue

        if a > hi:
            #a blob that cannot be split is flagged instead of silently discarded. So the user can separate the beans and take another photo.
            flagged.append({"bbox": (x, y, bw, bh),
                            "area": float(a),
                            "est_beans": int(round(a / med))})
            continue
        if a < lo:
            dropped_area += a
            #ignore tiny dust, only count plausible bean fragments
            if a >= config.FRAGMENT_MIN_FACTOR * med:
                dropped_n += 1
            continue
        ar = max(bw, bh) / max(1, min(bw, bh))
        if ar > config.MAX_ASPECT_RATIO: #too elongated (shadow)
            continue
        if a / (bw * bh) < config.MIN_SOLIDITY: #object doesnt fill enough of its bounding box.
            continue
        #crop tightly around the bean, then add black padding during classification to match the training images (SANTOS).
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(W, x + bw + pad), min(H, y + bh + pad)
        out.append({
            "crop": bgr[y0:y1, x0:x1].copy(),
            "bbox": (x0, y0, x1 - x0, y1 - y0),
            "area": float(a),
            "ar": float(ar),
        })

    #6. safeguard against losing beans when the threshold is wrong because too many small fragments may be broken bean pieces, not debris. We use fragment count relative to bean count to detect this.
    kept_area = sum(b["area"] for b in out) + sum(f["area"] for f in flagged)
    frag = dropped_area / max(1.0, kept_area + dropped_area)
    ratio = dropped_n / max(1, len(out))
    warn = ratio > config.WARN_FRAGMENT_RATIO or frag > config.WARN_FRAGMENT_AREA

    if debug:
        vis = bgr.copy()
        for f in flagged:
            x, y, bw, bh = f["bbox"]
            cv2.rectangle(vis, (x, y), (x + bw, y + bh), (0, 0, 255), 3)
            cv2.putText(vis, f"?x{f['est_beans']}", (x, y - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)
        for i, d in enumerate(out):
            x, y, bw, bh = d["bbox"]
            cv2.rectangle(vis, (x, y), (x + bw, y + bh), (0, 200, 0), 2)
            cv2.putText(vis, str(i), (x, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 220), 1, cv2.LINE_AA)
        return out, flagged, warn, frag, dropped_n, edge_n, vis, mask
    return out, flagged, warn, frag, dropped_n, edge_n


if __name__ == "__main__":
    import sys, os

    #manual test runner, not part of the pipeline
    path = sys.argv[1] if len(sys.argv) > 1 else "tests/images/tray_real_01.jpg"
    img = cv2.imread(path)
    if img is None:
        sys.exit(f"Gagal baca gambar: {path}")

    beans, flagged, warn, frag, frag_n, edge_n, vis, mask = detect_beans(img, debug=True)

    print("file             :", path)
    print("biji terdeteksi  :", len(beans))
    if flagged:
        print("gumpalan ditandai:", len(flagged),
              f"(perkiraan {sum(f['est_beans'] for f in flagged)} biji di dalamnya)")
        print("Pisahkan bijinya lalu foto ulang")
    else:
        print("gumpalan ditandai: 0")

    print(f"serpihan dibuang : {frag_n} potong ({100 * frag:.1f}% luas)")
    print(f"kena tepi frame  : {edge_n} objek")
    if warn:
        print("Curiga banyak serpihan, kemungkinan ada biji yang pecah dan tidak terhitung. cek _mask.jpg sebelum percaya angkanya")

    #dump visuals for manual inspection: vis = boxes overlaid, mask = raw binary mask, crops/ = per-bean images
    stem = os.path.splitext(os.path.basename(path))[0]
    cv2.imwrite(f"{stem}_vis.jpg", vis)
    cv2.imwrite(f"{stem}_mask.jpg", mask)
    os.makedirs("crops", exist_ok=True)
    for i, b in enumerate(beans):
        cv2.imwrite(f"crops/{stem}_{i:03d}.jpg", b["crop"])

    print()
    print(f"output: {stem}_vis.jpg, {stem}_mask.jpg, crops/") #where the files can be found