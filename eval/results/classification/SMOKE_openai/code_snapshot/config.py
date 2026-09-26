"""
config.py: every constant used by the segment.py and classify.py pipeline.

Separated from segment.py because these numbers decide whether a bean gets
counted, split, or thrown away. Written inline they read as arbitrary, and a
reader cannot tell which ones were tested and which are guesses.

Each constant carries a validation tag (except CLASS_NAMES at the most bottom, which is a hard requirement based on the training labels):

1. SWEPT       : tested across several values and images, failure points known
2. REASONED    : derived from a property of the data or from a failure we actually observed, but never swept
3. UNVALIDATED : plausible guess, never tested
"""

#Resize every photo to this width first, so absolute area thresholds mean the same thing across phones with different resolutions.
#UNVALIDATED, never compared against 1200 or 2000.
TARGET_WIDTH = 1600

#A bright object below this fraction of the frame is not treated as the paper sheet, and the pipeline falls back to the full frame.
#UNVALIDATED. The shoot protocol asks for paper filling at least 75% of the frame, so 0.15 sits far below that.
PAPER_MIN_FRAME_FRACTION = 0.15

#Blur before going to Otsu so paper texture does not affect the bright region. Because Otsu works on a single pixel level, a small dot of paper texture can be enough to drag the threshold down.
#UNVALIDATED.
PAPER_BLUR_KERNEL = (7, 7)

#Closing kernel, deliberately large. Beans on the paper make holes in the bright region, and closing fills them so the sheet reads as one bright object.
#REASONED.
PAPER_CLOSE_KERNEL = (15, 15)
PAPER_CLOSE_ITERATIONS = 3

#The detected sheet is eroded inward so the printed paper edge is not read as an object. 
#REASONED. Keep small margin around the paper so it does not touch the image border.
PAPER_ERODE_KERNEL = (9, 9)
PAPER_ERODE_ITERATIONS = 2

#Blur before converting to Lab, to suppress sensor noise. UNVALIDATED.
MASK_BLUR_KERNEL = (5, 5)

#Give more weight to Lab's a/b channels because colour is more reliable than brightness.
#Brightness changes with shadows and lighting, while colour stays more stable. This helps separate pale beans from white paper.
#REASONED
MASK_CHROMA_WEIGHT = 2.0

#Minimum ROI (Region of interest) size needed to sample the background colour from the ROI. If the ROI is too small, use the whole image instead.
#UNVALIDATED.
MASK_MIN_ROI_PIXELS = 1000

#The value of 7 was tested on six photos and falls safely within the 5 untill 10 range. 
#Otsu's method wasn't used because it can only distinguish between two colors, whereas the photos contain three: the paper, dark seeds, and pale seeds. Otsu would incorrectly focus on the dark seeds, causing the pale ones to disappear.
#SWEPT.
MASK_MAD_K = 7.0

#Keep a minimum MAD so the threshold does not become too strict on uniform backgrounds.
#UNVALIDATED.
MASK_MAD_FLOOR = 1.5

#Removes small dust and noise at the beginning phasee. Small bean fragments may also be removed before counting.
#This means their area and number are not recorded.
#REASONED
CLEAN_OPEN_KERNEL = 5

#Distance transform mask size, used to find the center point of each bean before splitting touching clusters. UNVALIDATED, OpenCV default for DIST_L2.
SPLIT_DIST_MASK = 5

#List of seed thresholds, from strict to loose. Test them one by one until the number of separated seeds matches the estimate based on cluster area.
#UNVALIDATED. a reasonable sequence of descending values, but not yet benchmarked against other sequences.
SPLIT_SEED_FRACTIONS = (0.45, 0.38, 0.32, 0.26)

#Watershed runs per cluster, not on all clusters at once, because the distance transform peak is normalized within each cluster. 
#If clusters were processed together, a 4 bean cluster would have a much higher peak than a 2 bean cluster, and a single global threshold would erase every seed in the smaller cluster. 
#REASONED.

#Background dilation before watershed. UNVALIDATED.
SPLIT_BG_KERNEL = (3, 3)
SPLIT_BG_ITERATIONS = 3

#Object with area below this treated as dust, shadow, or a fragment of a bean. UNVALIDATED.
AREA_MIN_FACTOR = 0.45

#Above this treated as candidate cluster of touching beans, try to split.
#REASONED, deliberately not 2.0. Two touching beans overlap, so their combined contour is usually only 1.6 to 2.1 times a single bean. 
#A threshold of 2.0 lets a touching pair through as one bean.
AREA_SPLIT_FACTOR = 1.40

#Above this, blobs are reported unresolved rather than guessed. REASONED. 100+ local beans: max false flag was 1.70 area factor.
#Touching pairs overlap at 1.6 - 2.1x median, so area alone is insufficient; pairs must split or show pair like aspect.
AREA_MAX_FACTOR = 1.75

#Fragments smaller than 0.08 times the average seed area are discarded without any record, unlike larger fragments which are recorded as dropped_n. 
#UNVALIDATED
FRAGMENT_MIN_FACTOR = 0.08

#Longest side over shortest side. Above this, the contour is a shadow or a scratch, not a bean. UNVALIDATED.
MAX_ASPECT_RATIO = 3.2

#Contour area over bounding box area. Below this the shape is too hollow to be a bean. UNVALIDATED.
MIN_SOLIDITY = 0.45

#Padding around the bounding box when cropping so it doesnt get too tight. UNVALIDATED.
CROP_PAD = 4

#Fraction of dropped fragments per accepted bean. Above this, the run is suspect. UNVALIDATED. 
WARN_FRAGMENT_RATIO = 0.5

#Fraction of total detected area that was dropped. Above this, the run is also suspect. Weaker signal than WARN_FRAGMENT_RATIO because many small dropped fragments barely move this number, since fragments are very small compared to whole beans.
#Kept as a second check, not the main one. UNVALIDATED.
WARN_FRAGMENT_AREA = 0.05

#How a crop is padded to square before it reaches the classifier (YOLO wanted square crops).
#REASONED, with a measured basis: "none" lets the Ultralytics centre crop cut the ends off the bean, and predictions collapsed to violet at most. 
#Bean ends carry class signal, so the whole bean has to be saved. Black matches the training background exactly (Santos et al. 2023).
PAD_MODE = "black"

#Set pixels outside the bean contour to black. Real crops contained 28.6–37.6% paper in the corners, unlike the pure black background used in training.
#REASONED. Local gate: 121 beans across 8 photos. Mask alone improved fermented recall from 5/21 to 8/21; mask + gain 1.24 reached 15/21, supporting the change.
MASK_BACKGROUND_IN_CROP = True

# Enable colour correction using the paper around each bean.
PAPER_WB_ENABLED = False

# Target value for each paper colour channel.
PAPER_WB_TARGET = 200

# Minimum bright paper pixels needed for correction.
PAPER_WB_MIN_PIXELS = 50

# Lowest allowed paper correction gain.
PAPER_WB_GAIN_MIN = 0.5

# Highest allowed paper correction gain.
PAPER_WB_GAIN_MAX = 3.0

#Boost the green channel before inference so field photo gets closer to the training colours.
#REASONED. 1.24 is the inverse of 0.807, which is mean(R)/mean(G) over framed_and_centralized dataset (R 61.1, G 75.7). 
#Scaling G by 0.807 on the Santos test set dropped macro-F1 from 0.846 to 0.595, so the model leans on the green cast. 
#Kept because the local gate measured it, fermented recall 8/21 at gain 1.0, 15/21 at 1.24. 
GREEN_CAST_G_GAIN = 1.24

#Input size fed to the classifier. Must match the imgsz recorded in the training run's args.yaml. REASONED.
CLASSIFY_IMGSZ = 224

#how many crops go to the model per forward pass. UNVALIDATED, picked to keep memory predictable on a laptop CPU. Affects speed only, never results.
CLASSIFY_BATCH = 16

#Sample size the cut test is defined on. Below this, the app labels the percentage indicative rather than settled.
#REASONED, from the cut test sample size in SNI 2323:2008.
MIN_SAMPLE_FULL = 300

#class names the pipeline expects, there is no validation tag because this is a hard requirement. 
#the model must be trained with exactly these names, in this order (Alphabetically). "load_model" raises if this does not match model.names exactly.
CLASS_NAMES = ("fermented", "poorly_fermented")
