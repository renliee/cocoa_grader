"""
grade.py: every bean label will be counted per fermentation class and reported as counts and percentages.
"""

try:
    from . import config
except ImportError:
    import config

LABEL_ID = {
    "fermented": "Well fermented",
    "poorly_fermented": "Poorly fermented",
}
DISCLAIMER = (
    "Use these results to support quality assessment, "
    "not as a substitute for standards-based testing. Other quality parameters "
    "(mold, insect damage, foreign matter, and germination) are not assessed.")
 
def count_labels(labels):
    """Count beans per class. Unknown labels will be raise (just for safeguard)."""
    counts = {c: 0 for c in config.CLASS_NAMES}
    for i, lab in enumerate(labels):
        if lab not in counts:
            raise ValueError(f"unknown label at index {i}: {lab!r}")
        counts[lab] += 1
    return counts


def percentages(counts, n):
    """
    Round the first class and give the remainder to the second, so the pair always sums to 100.
    Rounding both on their own can land on 99 or 101, which looks like a bug.
    """
    first, second = config.CLASS_NAMES
    p = round(100 * counts[first] / n)
    return {first: p, second: 100 - p}


def grade(labels, n_unreadable=0, n_photos=1): 
    """
    labels: labels from classify.py, List of each successfully read bean
    n_unreadable: beans detected but not classified, from segment.py (flagged, dropped_n, and edge_n)
    n_photos: display only, it never enters the arithmetic
    Returns a dict, not a string. Formatting is in format_report().
    """
    n = len(labels)
    if n == 0:
        raise ValueError(f"No usable beans among {n_unreadable} detected candidates")
    
    counts = count_labels(labels)
    persen = percentages(counts, n)
 
    catatan = []
    if n < config.MIN_SAMPLE_FULL:
        catatan.append(f"The sample contains {n} beans, below the cut-test reference of {config.MIN_SAMPLE_FULL}. Percentages are indicative.")
    if n_unreadable:
        catatan.append(f"{n_unreadable} detected candidates were excluded from the counts above.")

    return {
        "n_terbaca": n,
        "n_foto": n_photos,
        "n_tidak_terbaca": n_unreadable,
        "jumlah": counts,
        "persen": persen,
        "catatan": catatan,
        "disclaimer": DISCLAIMER,
    }


def format_report(h): #h is the dict returned by grade()
    """Converting dict from grade() to text. Seperated because we want to test grade() without checking the exact string format."""

    #out is a list of strings, joined with newlines at the end
    out = [f"{h['n_terbaca']} beans analyzed ({h['n_foto']} photos)", ""]

    w = max(len(v) for v in LABEL_ID.values()) + 2 #count the longest lable and add it with number 2.
    for c in config.CLASS_NAMES:
        out.append(f"{LABEL_ID[c]:<{w}}{h['jumlah'][c]:>3}   ({h['persen'][c]}%)") #count first, the percentage only means something next to it at this n

    out.append("")
    out += h["catatan"]
    out.append(h["disclaimer"])
    return "\n".join(out)
